import argparse
import os, json, math, random, time, zipfile, shutil
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForMaskedLM, get_linear_schedule_with_warmup
from torch.optim import AdamW
from tqdm.auto import tqdm

# =====================
# Runtime paths only
# =====================

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, required=True)
parser.add_argument("--bottom15-root", type=Path, required=True)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

# =====================
# Original training config
# =====================

SEED = args.seed
MODEL_NAME = "naver/splade-cocondenser-ensembledistil"

ROOT = args.bottom15_root
TRIPLET_PATH = ROOT / "training_triplets.csv"
PAIRS_PATH = ROOT / "synthetic_pairs_filtered.csv"

OUT_DIR = args.output_dir
CKPT_DIR = OUT_DIR / "checkpoints"
BEST_DIR = CKPT_DIR / "best"
LAST_DIR = CKPT_DIR / "last"
BEST_ZIP = Path(f"/kaggle/working/old35_seed{SEED}_best_checkpoint.zip")
LAST_ZIP = Path(f"/kaggle/working/old35_seed{SEED}_last_checkpoint.zip")
ALL_ZIP = Path(f"/kaggle/working/old35_seed{SEED}_training_outputs.zip")

MAX_LENGTH = 128
TEMPERATURE = 1.0
SPLADE_LAMBDA = 1e-4

EPOCHS = 3
BATCH_SIZE = 2
GRAD_ACCUM = 16
LR = 2e-5
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.10

VALID_FRACTION = 0.10
VALID_EVERY = 200
SAVE_EVERY = 200
PRINT_EVERY = 25

# Set this if you want a safer shorter run.
# For full faithful training, leave as None.
MAX_OPT_STEPS = None

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

OUT_DIR.mkdir(parents=True, exist_ok=True)
CKPT_DIR.mkdir(parents=True, exist_ok=True)

print("Device:", DEVICE)
print("Triplet path:", TRIPLET_PATH)
print("Pairs path:", PAIRS_PATH)

assert TRIPLET_PATH.exists(), f"Missing {TRIPLET_PATH}"
assert PAIRS_PATH.exists(), f"Missing {PAIRS_PATH}"

# =====================
# Load triplets
# =====================

triplets = pd.read_csv(TRIPLET_PATH)
pairs = pd.read_csv(PAIRS_PATH)

print("Triplet columns:", triplets.columns.tolist())
print("Triplets:", len(triplets))
print("Pairs:", len(pairs))
assert len(triplets) == 62515, (
    f"Expected the old run's 62,515 input triplets, got {len(triplets):,}"
)
assert len(pairs) == 7944, (
    f"Expected the old run's 7,944 retained pairs, got {len(pairs):,}"
)

# Build ID -> text maps from synthetic pairs.
review_text = dict(zip(pairs["review_id"].astype(str), pairs["generated_review"].astype(str)))
issue_text = {}

for _, r in pairs.iterrows():
    iid = str(r["issue_id"])
    title = "" if pd.isna(r.get("issue_title", "")) else str(r.get("issue_title", ""))
    body = "" if pd.isna(r.get("issue_body", "")) else str(r.get("issue_body", ""))
    labels = "" if pd.isna(r.get("issue_labels", "")) else str(r.get("issue_labels", ""))
    issue_text[iid] = f"{title}\n\n{body}\n\nLabels: {labels}".strip()

if {"query", "positive", "negative"}.issubset(triplets.columns):
    print("Text triplets detected.")
    df = triplets[["query", "positive", "negative"]].dropna().copy()
else:
    print("ID-style triplets detected; reconstructing text triplets...")
    rows = []
    skipped = 0

    for _, r in triplets.iterrows():
        qid = str(r["query_review_id"])
        pid = str(r["positive_issue_id"])
        nid = str(r["negative_issue_id"])

        q = review_text.get(qid)
        p = issue_text.get(pid)
        n = issue_text.get(nid)

        if q and p and n:
            rows.append({"query": q, "positive": p, "negative": n})
        else:
            skipped += 1

    df = pd.DataFrame(rows)
    print("Reconstructed triplets:", len(df))
    print("Skipped missing text triplets:", skipped)

assert len(df) > 0, "No usable triplets."
assert len(df) == 53375 and skipped == 9140, (
    "This is not the exact dataset reconstruction used by the 35% run: "
    f"reconstructed={len(df):,}, skipped={skipped:,}; expected "
    "53,375 reconstructed and 9,140 skipped."
)

# Deterministic split
df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
val_size = max(1, int(len(df) * VALID_FRACTION))
val_df = df.iloc[:val_size].reset_index(drop=True)
train_df = df.iloc[val_size:].reset_index(drop=True)

print("Train triplets:", len(train_df))
print("Validation triplets:", len(val_df))
assert len(train_df) == 48038 and len(val_df) == 5337, (
    f"Unexpected old-structure split sizes: train={len(train_df):,}, "
    f"validation={len(val_df):,}"
)

if args.dry_run:
    print(
        "DRY RUN PASSED: exact old-35 data reconstruction and triplet split "
        f"verified for seed {SEED}."
    )
    raise SystemExit(0)

# =====================
# Dataset
# =====================

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

class TripletDataset(Dataset):
    def __init__(self, frame):
        self.q = frame["query"].astype(str).tolist()
        self.p = frame["positive"].astype(str).tolist()
        self.n = frame["negative"].astype(str).tolist()

    def __len__(self):
        return len(self.q)

    def __getitem__(self, idx):
        return self.q[idx], self.p[idx], self.n[idx]

def collate(batch):
    q, p, n = zip(*batch)
    qt = tokenizer(list(q), padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    pt = tokenizer(list(p), padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    nt = tokenizer(list(n), padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    return qt, pt, nt

train_loader = DataLoader(
    TripletDataset(train_df),
    batch_size=BATCH_SIZE,
    shuffle=True,
    collate_fn=collate,
    num_workers=2,
    pin_memory=True,
)

val_loader = DataLoader(
    TripletDataset(val_df),
    batch_size=BATCH_SIZE,
    shuffle=False,
    collate_fn=collate,
    num_workers=2,
    pin_memory=True,
)

# =====================
# Model
# =====================

class SpladeEncoder(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.model = AutoModelForMaskedLM.from_pretrained(model_name)
        self.model.gradient_checkpointing_enable()
        if hasattr(self.model.config, "use_cache"):
            self.model.config.use_cache = False

    def forward(self, batch):
        batch = {k: v.to(DEVICE) for k, v in batch.items()}
        out = self.model(**batch)
        logits = out.logits
        attention = batch["attention_mask"].unsqueeze(-1)

        values = torch.log1p(torch.relu(logits)) * attention
        reps = torch.max(values, dim=1).values
        return reps

model = SpladeEncoder(MODEL_NAME).to(DEVICE)

optimizer = AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

steps_per_epoch = math.ceil(len(train_loader) / GRAD_ACCUM)
total_steps = steps_per_epoch * EPOCHS
if MAX_OPT_STEPS is not None:
    total_steps = min(total_steps, MAX_OPT_STEPS)

warmup_steps = int(total_steps * WARMUP_RATIO)

scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=warmup_steps,
    num_training_steps=total_steps,
)

print("Total optimizer steps:", total_steps)
print("Warmup steps:", warmup_steps)

# =====================
# Train/eval helpers
# =====================

def triplet_loss(q, p, n):
    pos = torch.sum(q * p, dim=1)
    neg = torch.sum(q * n, dim=1)
    logits = torch.stack([pos, neg], dim=1) / TEMPERATURE
    labels = torch.zeros(logits.size(0), dtype=torch.long, device=DEVICE)
    ce = F.cross_entropy(logits, labels)
    l1 = (q.mean() + p.mean() + n.mean()) / 3.0
    loss = ce + SPLADE_LAMBDA * l1
    return loss, ce.detach(), l1.detach()

@torch.no_grad()
def validate(max_batches=None):
    model.eval()
    losses, ces = [], []

    for i, (qt, pt, nt) in enumerate(val_loader):
        q = model(qt)
        p = model(pt)
        n = model(nt)

        loss, ce, l1 = triplet_loss(q, p, n)
        losses.append(float(loss.item()))
        ces.append(float(ce.item()))

        if max_batches is not None and i + 1 >= max_batches:
            break

    model.train()
    return float(np.mean(losses)), float(np.mean(ces))

def save_checkpoint(path, step, val_loss=None):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    model.model.save_pretrained(path)
    tokenizer.save_pretrained(path)

    state = {
        "step": step,
        "val_loss": val_loss,
        "model_name": MODEL_NAME,
        "max_length": MAX_LENGTH,
        "temperature": TEMPERATURE,
        "splade_lambda": SPLADE_LAMBDA,
        "lr": LR,
        "weight_decay": WEIGHT_DECAY,
        "batch_size": BATCH_SIZE,
        "grad_accum": GRAD_ACCUM,
        "epochs": EPOCHS,
        "seed": SEED,
    }

    with open(path / "training_state.json", "w") as f:
        json.dump(state, f, indent=2)

def zip_dir(src, dst):
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        dst.unlink()
    shutil.make_archive(str(dst).replace(".zip", ""), "zip", src)

# =====================
# Training loop
# =====================

best_val = float("inf")
global_step = 0
micro_step = 0
running_loss = []
running_ce = []
running_l1 = []

model.train()
optimizer.zero_grad(set_to_none=True)

start = time.time()
stop_training = False

for epoch in range(1, EPOCHS + 1):
    print(f"\nEpoch {epoch}/{EPOCHS}")

    for qt, pt, nt in train_loader:
        q = model(qt)
        p = model(pt)
        n = model(nt)

        loss, ce, l1 = triplet_loss(q, p, n)
        (loss / GRAD_ACCUM).backward()

        running_loss.append(float(loss.item()))
        running_ce.append(float(ce.item()))
        running_l1.append(float(l1.item()))

        micro_step += 1

        if micro_step % GRAD_ACCUM == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)

            global_step += 1

            if global_step % PRINT_EVERY == 0:
                elapsed_min = (time.time() - start) / 60
                rate = global_step / max(elapsed_min, 1e-9)
                eta = (total_steps - global_step) / max(rate, 1e-9)
                print(
                    f"step={global_step} "
                    f"train_loss={np.mean(running_loss[-PRINT_EVERY:]):.4f} "
                    f"ce={np.mean(running_ce[-PRINT_EVERY:]):.4f} "
                    f"l1={np.mean(running_l1[-PRINT_EVERY:]):.4f} "
                    f"elapsed_min={elapsed_min:.1f} eta_min={eta:.1f}"
                )

            if global_step % VALID_EVERY == 0:
                val_loss, val_ce = validate()
                print(f"VALID step={global_step} val_loss={val_loss:.4f} val_ce={val_ce:.4f}")

                save_checkpoint(LAST_DIR, global_step, val_loss)

                if val_loss < best_val:
                    best_val = val_loss
                    save_checkpoint(BEST_DIR, global_step, val_loss)
                    print(f"NEW BEST step={global_step} val_loss={val_loss:.4f}")

                # The original notebook recompressed ~1 GB of checkpoint
                # archives here every 200 steps. Deferring compression until
                # the end changes no weights, RNG state, validation result, or
                # checkpoint selection and protects the limited GPU quota.
                print("Checkpoint directories refreshed.")

            if global_step % SAVE_EVERY == 0:
                save_checkpoint(LAST_DIR, global_step, None)

            if global_step >= total_steps:
                stop_training = True
                break

    if stop_training:
        break

# Final save
val_loss, val_ce = validate()
print(f"FINAL VALID step={global_step} val_loss={val_loss:.4f} val_ce={val_ce:.4f}")

save_checkpoint(LAST_DIR, global_step, val_loss)
if val_loss < best_val:
    best_val = val_loss
    save_checkpoint(BEST_DIR, global_step, val_loss)
    print(f"NEW BEST FINAL step={global_step} val_loss={val_loss:.4f}")

zip_dir(BEST_DIR, BEST_ZIP)
zip_dir(LAST_DIR, LAST_ZIP)
zip_dir(OUT_DIR, ALL_ZIP)

print("\nDone.")
print("Best checkpoint:", BEST_DIR)
print("Best checkpoint zip:", BEST_ZIP)
print("Last checkpoint zip:", LAST_ZIP)
print("All outputs zip:", ALL_ZIP)
