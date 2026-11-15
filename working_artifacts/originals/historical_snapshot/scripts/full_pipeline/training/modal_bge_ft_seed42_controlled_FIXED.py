#!/usr/bin/env python3
"""
BGE-FT CONTROLLED SYNTHETIC-ADAPTATION EXPERIMENT ON MODAL
==========================================================

Question:
    Does the SAME filtered synthetic review->issue supervision that was used
    for SPLADE-SE improve a dense retriever (BGE-Base), or is the transfer
    problem largely supervision/domain-gap related?

Pre-registered first run:
    model:       BAAI/bge-base-en-v1.5
    seed:        42
    epochs:      3
    lr:          2e-5
    weight decay 0.01
    batch size:  32
    max length:  128
    temperature: 0.05
    split:       issue-disjoint, 10% dev within each training app
    objective:   InfoNCE over [batch positives + one rotating hard negative/query]
    selection:   highest pooled FULL-CORPUS synthetic-dev MRR
    query prefix: NONE, to match the existing BGE baseline setup

Important:
    - No DeepMatcher/BugRMSys/real external data is used in training or selection.
    - Do not tune hyperparameters after seeing external results.
    - This is ONE seed first. Only run more seeds if seed 42 produces a
      substantively useful external result.

Expected Modal Volume:
    splade-data

Expected Modal Volume layout:
    /vol/modal_splade_data.zip

The script extracts that existing archive into /tmp and then searches
recursively inside it for:
    bottom15_llm/
        synthetic_pairs_filtered.csv
        training_triplets.csv

    Signal-Android_Mistral_Ready.csv
    Anki-Android_Mistral_Ready.csv
    k-9_Mistral_Ready.csv
    brave_issues.csv

Expected filtered schema:
    synthetic_pairs_filtered.csv:
        review_id, generated_review, issue_id

    training_triplets.csv:
        query_review_id, positive_issue_id, negative_issue_id
"""

from __future__ import annotations

import ast
import gc
import hashlib
import json
import math
import os
import random
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import modal

# ============================================================
# MODAL
# ============================================================

APP_NAME = "bge-ft-synthetic-control"
VOLUME_NAME = "splade-data"
VOLUME_MOUNT = "/vol"

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.4,<3",
        "transformers>=4.50,<5",
        "pandas>=2.2,<3",
        "numpy>=2,<3",
        "scikit-learn>=1.5,<2",
        "safetensors>=0.4,<1",
    )
)

# ============================================================
# CONSTANTS
# ============================================================

MODEL_NAME = "BAAI/bge-base-en-v1.5"

EXPECTED_RETAINED_QUERIES = 7_944
EXPECTED_TRIPLETS = 62_515

SEED = 42
SPLIT_SEED = 42
DEV_FRACTION = 0.10

EPOCHS = 3
BATCH_SIZE = 32
LR = 2e-5
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.10
TEMPERATURE = 0.05
MAX_LENGTH = 128
NUM_WORKERS = 2

APP_SOURCES = {
    "signal": "Signal-Android_Mistral_Ready.csv",
    "ankidroid": "Anki-Android_Mistral_Ready.csv",
    "k9": "k-9_Mistral_Ready.csv",
    "brave": "brave_issues.csv",
}

OUTPUT_DIR = Path(VOLUME_MOUNT) / "bge_ft_seed42_controlled"


# ============================================================
# HELPERS
# ============================================================

def clean(v) -> str:
    import pandas as pd
    return "" if pd.isna(v) else str(v).strip()


def norm_id(v) -> str:
    import numpy as np
    import pandas as pd

    if pd.isna(v):
        return ""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))

    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


def parse_labels(v) -> str:
    s = clean(v)
    if not s or s.lower() == "nan" or s == "[]":
        return ""
    try:
        x = ast.literal_eval(s)
        if isinstance(x, list):
            return " ".join(
                str(i.get("name", "")) if isinstance(i, dict) else str(i)
                for i in x
            ).strip()
    except Exception:
        pass
    return s


def format_issue(title, body, labels) -> str:
    return f"{clean(title)}\n\n{clean(body)}\n\nLabels: {parse_labels(labels)}".strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def json_dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def find_exact_file(root: Path, basename: str) -> Path:
    hits = [
        p for p in root.rglob("*")
        if p.is_file() and p.name.lower() == basename.lower()
    ]
    if not hits:
        raise FileNotFoundError(f"Missing {basename} under {root}")

    # Prefer the original training-data directory if duplicates exist.
    hits.sort(
        key=lambda p: (
            "spladetrainingv12" not in str(p).lower(),
            len(str(p)),
        )
    )
    return hits[0]


def find_bottom15_dir(root: Path) -> Path:
    hits = []
    for p in root.rglob("training_triplets.csv"):
        if (p.parent / "synthetic_pairs_filtered.csv").exists():
            hits.append(p.parent)

    if not hits:
        raise FileNotFoundError(
            "No directory containing BOTH training_triplets.csv and "
            "synthetic_pairs_filtered.csv under /vol"
        )

    hits.sort(
        key=lambda p: (
            "bottom15_llm" not in str(p).lower(),
            len(str(p)),
        )
    )
    return hits[0]



def extract_modal_training_package(dest: Path) -> Path:
    """
    The existing `splade-data` Modal Volume stores the training data as
    /vol/modal_splade_data.zip. The previous working SPLADE Modal jobs
    extracted this archive into /tmp before running the trainer.
    """
    import zipfile

    zip_path = Path(VOLUME_MOUNT) / "modal_splade_data.zip"
    if not zip_path.exists():
        raise FileNotFoundError(
            f"{zip_path} not found in Modal Volume '{VOLUME_NAME}'."
        )

    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {zip_path} -> {dest}", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)

    print("Training package extracted.", flush=True)
    return dest


def select_body(df):
    import pandas as pd

    if "clean_body" in df.columns and "body" in df.columns:
        return df["clean_body"].where(df["clean_body"].notna(), df["body"])
    if "clean_body" in df.columns:
        return df["clean_body"]
    if "body" in df.columns:
        return df["body"]
    if "description" in df.columns:
        return df["description"]
    return pd.Series([""] * len(df), index=df.index)


def seed_everything(seed: int):
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    # Reproducibility over a tiny speed gain.
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ============================================================
# DATA LOADERS
# ============================================================

def load_full_issue_corpus(root: Path):
    import pandas as pd

    issue_map: Dict[str, str] = {}
    app_issue_ids: Dict[str, List[str]] = {}
    provenance = {}

    for app_name, basename in APP_SOURCES.items():
        path = find_exact_file(root, basename)
        df = pd.read_csv(path)

        number_col = "issue_number" if "issue_number" in df.columns else "number"
        if number_col not in df.columns:
            raise KeyError(
                f"{basename}: expected issue_number or number; "
                f"columns={df.columns.tolist()}"
            )

        titles = (
            df["title"]
            if "title" in df.columns
            else pd.Series([""] * len(df), index=df.index)
        )
        bodies = select_body(df)

        if "issue_labels" in df.columns:
            labels = df["issue_labels"]
        elif "labels" in df.columns:
            labels = df["labels"]
        else:
            labels = pd.Series([""] * len(df), index=df.index)

        ids = []
        for number, title, body, label in zip(
            df[number_col],
            titles,
            bodies,
            labels,
        ):
            iid = f"{app_name}-{norm_id(number)}"
            if iid not in issue_map:
                issue_map[iid] = format_issue(title, body, label)
                ids.append(iid)

        app_issue_ids[app_name] = ids
        provenance[app_name] = {
            "path": str(path),
            "sha256": sha256(path),
            "issues": len(ids),
        }

        print(
            f"FULL CORPUS {app_name:10s}: {len(ids):,} issues <- {path}",
            flush=True,
        )

    return issue_map, app_issue_ids, provenance


def load_pairs_triplets(root: Path):
    import pandas as pd

    d = find_bottom15_dir(root)
    pair_path = d / "synthetic_pairs_filtered.csv"
    triplet_path = d / "training_triplets.csv"

    pairs = pd.read_csv(pair_path)
    triplets = pd.read_csv(triplet_path)

    need_pairs = {"review_id", "generated_review", "issue_id"}
    need_triplets = {
        "query_review_id",
        "positive_issue_id",
        "negative_issue_id",
    }

    if not need_pairs.issubset(pairs.columns):
        raise KeyError(
            f"{pair_path}: required={sorted(need_pairs)} "
            f"actual={pairs.columns.tolist()}"
        )
    if not need_triplets.issubset(triplets.columns):
        raise KeyError(
            f"{triplet_path}: required={sorted(need_triplets)} "
            f"actual={triplets.columns.tolist()}"
        )

    pairs = pairs.copy()
    triplets = triplets.copy()

    pairs["review_id"] = pairs["review_id"].map(norm_id)
    pairs["issue_id"] = pairs["issue_id"].map(norm_id)
    pairs["generated_review"] = pairs["generated_review"].map(clean)

    for c in need_triplets:
        triplets[c] = triplets[c].map(norm_id)

    if pairs["review_id"].nunique() != EXPECTED_RETAINED_QUERIES:
        raise AssertionError(
            f"Expected {EXPECTED_RETAINED_QUERIES} retained queries, "
            f"got {pairs['review_id'].nunique()}"
        )

    if len(triplets) != EXPECTED_TRIPLETS:
        raise AssertionError(
            f"Expected {EXPECTED_TRIPLETS} triplets, got {len(triplets)}"
        )

    # One text and one source issue per review ID.
    if pairs.groupby("review_id")["generated_review"].nunique(dropna=False).max() != 1:
        raise AssertionError("A review_id maps to multiple query texts.")
    if pairs.groupby("review_id")["issue_id"].nunique(dropna=False).max() != 1:
        raise AssertionError("A review_id maps to multiple source issues.")

    examples = (
        pairs[["review_id", "generated_review", "issue_id"]]
        .drop_duplicates("review_id")
        .rename(
            columns={
                "review_id": "query_id",
                "generated_review": "query",
                "issue_id": "positive_issue_id",
            }
        )
        .reset_index(drop=True)
    )

    examples["app"] = examples["positive_issue_id"].map(
        lambda s: str(s).split("-", 1)[0]
    )

    # We expect the filtered setup to contain one review per positive issue.
    # This matters for clean in-batch negatives.
    n_unique_positive = examples["positive_issue_id"].nunique()
    if n_unique_positive != len(examples):
        raise AssertionError(
            "Expected one retained review per positive issue, but got "
            f"{len(examples):,} queries and {n_unique_positive:,} unique positives. "
            "Stop rather than silently introduce duplicate-positive in-batch labels."
        )

    provenance = {
        "bottom15_dir": str(d),
        "pairs_path": str(pair_path),
        "triplets_path": str(triplet_path),
        "pairs_sha256": sha256(pair_path),
        "triplets_sha256": sha256(triplet_path),
    }

    return examples, triplets, provenance


def make_issue_disjoint_split(examples, split_seed: int, dev_fraction: float):
    import numpy as np

    rng = np.random.RandomState(split_seed)
    dev_issues = set()

    print("\nISSUE-DISJOINT SPLIT", flush=True)

    for app_name, sub in examples.groupby("app", sort=True):
        issues = np.array(
            sorted(sub["positive_issue_id"].unique()),
            dtype=object,
        )
        rng.shuffle(issues)
        n_dev = max(1, int(round(len(issues) * dev_fraction)))
        chosen = set(issues[:n_dev].tolist())
        dev_issues.update(chosen)

        print(
            f"  {app_name:10s}: {len(issues):,} labeled issues "
            f"-> {len(chosen):,} dev",
            flush=True,
        )

    dev = (
        examples[examples["positive_issue_id"].isin(dev_issues)]
        .copy()
        .reset_index(drop=True)
    )
    train = (
        examples[~examples["positive_issue_id"].isin(dev_issues)]
        .copy()
        .reset_index(drop=True)
    )

    assert not (
        set(train["positive_issue_id"])
        & set(dev["positive_issue_id"])
    )
    assert not (
        set(train["query_id"])
        & set(dev["query_id"])
    )

    print(
        f"  TRAIN: {len(train):,} queries / "
        f"{train['positive_issue_id'].nunique():,} positives\n"
        f"  DEV:   {len(dev):,} queries / "
        f"{dev['positive_issue_id'].nunique():,} positives",
        flush=True,
    )

    return train, dev, dev_issues


def build_negative_lists(
    train,
    triplets,
    issue_map,
    dev_issue_ids,
):
    """
    Reuse the existing filtered hard negatives.

    Critical leakage guard:
      a dev positive issue is NEVER allowed as a train negative.
    """
    train_qids = set(train["query_id"])
    pos_by_q = dict(
        zip(train["query_id"], train["positive_issue_id"])
    )

    negs = defaultdict(list)

    for row in triplets.itertuples(index=False):
        qid = str(row.query_review_id)
        if qid not in train_qids:
            continue

        neg = str(row.negative_issue_id)
        pos = pos_by_q[qid]

        if not neg or neg == pos:
            continue
        if neg in dev_issue_ids:
            continue
        if neg not in issue_map:
            continue

        if neg not in negs[qid]:
            negs[qid].append(neg)

    missing = sorted(train_qids - set(negs))
    if missing:
        raise AssertionError(
            f"{len(missing)} train queries have zero usable hard negatives "
            f"after removing dev positives. Examples={missing[:10]}"
        )

    counts = [len(negs[q]) for q in train_qids]
    print(
        "\nHARD NEGATIVES AFTER LEAKAGE FILTER\n"
        f"  queries: {len(counts):,}\n"
        f"  min/query: {min(counts)}\n"
        f"  mean/query: {sum(counts)/len(counts):.2f}\n"
        f"  max/query: {max(counts)}",
        flush=True,
    )

    return negs


# ============================================================
# MODEL + DATASET
# ============================================================

def mean_or_cls_note():
    # BGE v1.5's sentence-transformer configuration uses the CLS
    # representation. We implement CLS directly to avoid a second abstraction
    # layer and make train/eval behavior explicit.
    return "CLS(last_hidden_state[:,0]) + L2 normalization"


class BGEEncoder:
    """
    Thin wrapper around AutoModel. The actual torch module is `.model`.
    """
    def __init__(self, model_name: str, device):
        from transformers import AutoModel, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(device)

        if hasattr(self.model.config, "use_cache"):
            self.model.config.use_cache = False

        self.device = device

    def tokenize(self, texts):
        return self.tokenizer(
            list(texts),
            max_length=MAX_LENGTH,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )

    def encode_batch(self, texts):
        import torch
        import torch.nn.functional as F

        tok = self.tokenize(texts)
        tok = {
            k: v.to(self.device, non_blocking=True)
            for k, v in tok.items()
        }

        out = self.model(**tok)
        emb = out.last_hidden_state[:, 0]
        return F.normalize(emb.float(), p=2, dim=1)


def make_dataset_and_collate(train, negs, issue_map):
    import torch
    from torch.utils.data import Dataset

    rows = train.to_dict("records")

    class TrainDataset(Dataset):
        def __init__(self):
            self.epoch = 0

        def set_epoch(self, epoch: int):
            self.epoch = int(epoch)

        def __len__(self):
            return len(rows)

        def __getitem__(self, idx):
            row = rows[idx]
            qid = row["query_id"]
            candidates = negs[qid]

            # Deterministic rotation across available hard negatives.
            hard_id = candidates[(idx + self.epoch) % len(candidates)]

            return {
                "query_id": qid,
                "query": row["query"],
                "positive_id": row["positive_issue_id"],
                "positive": issue_map[row["positive_issue_id"]],
                "negative_id": hard_id,
                "negative": issue_map[hard_id],
            }

    def collate(batch):
        return {
            "query_id": [x["query_id"] for x in batch],
            "query": [x["query"] for x in batch],
            "positive_id": [x["positive_id"] for x in batch],
            "positive": [x["positive"] for x in batch],
            "negative_id": [x["negative_id"] for x in batch],
            "negative": [x["negative"] for x in batch],
        }

    return TrainDataset(), collate


# ============================================================
# EVALUATION
# ============================================================

def metrics_from_ranks(ranks):
    import numpy as np

    ranks = np.asarray(ranks, dtype=np.int64)
    return {
        "n": int(len(ranks)),
        "H@1": float(np.mean(ranks <= 1)),
        "H@5": float(np.mean(ranks <= 5)),
        "H@10": float(np.mean(ranks <= 10)),
        "MRR": float(np.mean(1.0 / ranks)),
        "median_rank": float(np.median(ranks)),
    }


def encode_texts_batched(
    encoder,
    texts,
    batch_size=128,
):
    import torch

    blocks = []
    encoder.model.eval()

    with torch.inference_mode():
        for st in range(0, len(texts), batch_size):
            batch = texts[st:st + batch_size]

            use_amp = encoder.device.type == "cuda"
            if use_amp:
                dtype = (
                    torch.bfloat16
                    if torch.cuda.is_bf16_supported()
                    else torch.float16
                )
                with torch.autocast("cuda", dtype=dtype):
                    v = encoder.encode_batch(batch)
            else:
                v = encoder.encode_batch(batch)

            blocks.append(v.cpu())

    return torch.cat(blocks, dim=0)


def evaluate_full_corpus(
    encoder,
    dev,
    issue_map,
    app_issue_ids,
):
    """
    Each dev query is ranked against the FULL issue corpus of its app.

    This is INTERNAL synthetic dev only and is the sole checkpoint-selection
    metric. External real datasets must remain untouched.
    """
    import numpy as np

    all_ranks = []
    by_app = {}
    per_query = []

    encoder.model.eval()

    for app_name, sub in dev.groupby("app", sort=True):
        sub = sub.reset_index(drop=True)

        doc_ids = app_issue_ids[app_name]
        doc_texts = [issue_map[i] for i in doc_ids]
        id_to_idx = {iid: i for i, iid in enumerate(doc_ids)}

        qv = encode_texts_batched(
            encoder,
            sub["query"].tolist(),
            batch_size=128,
        )
        dv = encode_texts_batched(
            encoder,
            doc_texts,
            batch_size=128,
        )

        scores = (qv @ dv.T).numpy()
        app_ranks = []

        for qi, row in enumerate(sub.itertuples(index=False)):
            gold_idx = id_to_idx[row.positive_issue_id]
            order = np.argsort(-scores[qi], kind="stable")
            rank = int(np.where(order == gold_idx)[0][0]) + 1

            app_ranks.append(rank)
            all_ranks.append(rank)
            per_query.append({
                "query_id": row.query_id,
                "app": app_name,
                "positive_issue_id": row.positive_issue_id,
                "rank": rank,
            })

        by_app[app_name] = metrics_from_ranks(app_ranks)

        print(
            f"  DEV {app_name:10s} "
            f"H1={by_app[app_name]['H@1']:.4f} "
            f"H10={by_app[app_name]['H@10']:.4f} "
            f"MRR={by_app[app_name]['MRR']:.4f} "
            f"median={by_app[app_name]['median_rank']:.1f}",
            flush=True,
        )

        del qv, dv, scores
        gc.collect()

    pooled = metrics_from_ranks(all_ranks)

    print(
        f"  DEV POOLED     "
        f"H1={pooled['H@1']:.4f} "
        f"H10={pooled['H@10']:.4f} "
        f"MRR={pooled['MRR']:.4f} "
        f"median={pooled['median_rank']:.1f}",
        flush=True,
    )

    return pooled, by_app, per_query


# ============================================================
# VALIDATION BEFORE GPU
# ============================================================

@app.function(
    image=image,
    volumes={VOLUME_MOUNT: volume},
    cpu=4.0,
    memory=16384,
    timeout=20 * 60,
)
def validate_data():
    import pandas as pd

    volume.reload()
    root = extract_modal_training_package(
        Path("/tmp/bge_ft_validation_input")
    )

    issue_map, app_issue_ids, corpus_prov = load_full_issue_corpus(root)
    examples, triplets, data_prov = load_pairs_triplets(root)
    train, dev, dev_issue_ids = make_issue_disjoint_split(
        examples,
        SPLIT_SEED,
        DEV_FRACTION,
    )

    missing_pos = sorted(
        set(examples["positive_issue_id"]) - set(issue_map)
    )
    if missing_pos:
        raise AssertionError(
            f"{len(missing_pos)} positive issues absent from full issue corpus; "
            f"examples={missing_pos[:10]}"
        )

    negs = build_negative_lists(
        train,
        triplets,
        issue_map,
        dev_issue_ids,
    )

    result = {
        "status": "OK",
        "retained_queries": int(len(examples)),
        "triplets": int(len(triplets)),
        "train_queries": int(len(train)),
        "dev_queries": int(len(dev)),
        "train_positive_issues": int(train["positive_issue_id"].nunique()),
        "dev_positive_issues": int(dev["positive_issue_id"].nunique()),
        "hard_negative_min": int(min(len(negs[q]) for q in negs)),
        "hard_negative_mean": float(
            sum(len(negs[q]) for q in negs) / len(negs)
        ),
        "corpora": {
            k: len(v) for k, v in app_issue_ids.items()
        },
        "data_provenance": data_prov,
        "corpus_provenance": corpus_prov,
    }

    print("\nVALIDATION PASSED")
    print(json.dumps(result, indent=2), flush=True)
    return result


# ============================================================
# TRAIN
# ============================================================

@app.function(
    image=image,
    volumes={VOLUME_MOUNT: volume},
    gpu="A100-40GB",
    cpu=8.0,
    memory=32768,
    timeout=3 * 60 * 60,
)
def train_bge():
    import numpy as np
    import pandas as pd
    import torch
    import torch.nn.functional as F
    from torch.optim import AdamW
    from torch.utils.data import DataLoader
    from transformers import get_linear_schedule_with_warmup

    volume.reload()
    root = extract_modal_training_package(
        Path("/tmp/bge_ft_training_input")
    )
    seed_everything(SEED)

    if not torch.cuda.is_available():
        raise RuntimeError("GPU required.")

    device = torch.device("cuda")
    print("GPU:", torch.cuda.get_device_name(0), flush=True)

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    issue_map, app_issue_ids, corpus_prov = load_full_issue_corpus(root)
    examples, triplets, data_prov = load_pairs_triplets(root)

    missing_pos = sorted(
        set(examples["positive_issue_id"]) - set(issue_map)
    )
    if missing_pos:
        raise AssertionError(
            f"{len(missing_pos)} positives absent from issue corpus; "
            f"{missing_pos[:10]}"
        )

    train, dev, dev_issue_ids = make_issue_disjoint_split(
        examples,
        SPLIT_SEED,
        DEV_FRACTION,
    )

    negs = build_negative_lists(
        train,
        triplets,
        issue_map,
        dev_issue_ids,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    split_manifest = examples[
        ["query_id", "app", "positive_issue_id"]
    ].copy()
    split_manifest["split"] = np.where(
        split_manifest["positive_issue_id"].isin(dev_issue_ids),
        "dev",
        "train",
    )
    split_manifest.to_csv(
        OUTPUT_DIR / "issue_disjoint_split.csv",
        index=False,
    )

    run_config = {
        "experiment": "BGE-FT controlled synthetic adaptation",
        "model_name": MODEL_NAME,
        "pooling": mean_or_cls_note(),
        "query_prefix": None,
        "seed": SEED,
        "split_seed": SPLIT_SEED,
        "dev_fraction": DEV_FRACTION,
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "learning_rate": LR,
        "weight_decay": WEIGHT_DECAY,
        "warmup_ratio": WARMUP_RATIO,
        "temperature": TEMPERATURE,
        "max_length": MAX_LENGTH,
        "objective": (
            "InfoNCE over batch positives + one rotating existing hard negative "
            "per query; duplicate-positive columns masked"
        ),
        "checkpoint_selection": (
            "highest internal issue-disjoint full-app-corpus pooled synthetic-dev MRR"
        ),
        "external_data_used_for_selection": False,
        "train_queries": int(len(train)),
        "dev_queries": int(len(dev)),
        "train_positive_issues": int(train["positive_issue_id"].nunique()),
        "dev_positive_issues": int(dev["positive_issue_id"].nunique()),
        "data_provenance": data_prov,
        "corpus_provenance": corpus_prov,
    }
    json_dump(run_config, OUTPUT_DIR / "run_config.json")

    # --------------------------------------------------------
    # Model
    # --------------------------------------------------------

    encoder = BGEEncoder(MODEL_NAME, device)

    # --------------------------------------------------------
    # PRE-TRAINING BGE-ZS INTERNAL BASELINE
    # --------------------------------------------------------

    print("\n" + "=" * 90)
    print("INTERNAL FULL-CORPUS BGE-ZS BASELINE")
    print("=" * 90, flush=True)

    zs_pooled, zs_by_app, zs_per_query = evaluate_full_corpus(
        encoder,
        dev,
        issue_map,
        app_issue_ids,
    )

    pd.DataFrame(zs_per_query).to_csv(
        OUTPUT_DIR / "bge_zs_internal_per_query.csv",
        index=False,
    )
    json_dump(
        {
            "pooled": zs_pooled,
            "by_app": zs_by_app,
        },
        OUTPUT_DIR / "bge_zs_internal_metrics.json",
    )

    # --------------------------------------------------------
    # Dataset
    # --------------------------------------------------------

    dataset, collate = make_dataset_and_collate(
        train,
        negs,
        issue_map,
    )

    optimizer = AdamW(
        encoder.model.parameters(),
        lr=LR,
        weight_decay=WEIGHT_DECAY,
    )

    steps_per_epoch = math.ceil(len(dataset) / BATCH_SIZE)
    total_steps = steps_per_epoch * EPOCHS
    warmup_steps = int(round(total_steps * WARMUP_RATIO))

    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    use_bf16 = torch.cuda.is_bf16_supported()

    best_mrr = -1.0
    best_epoch = None
    epoch_summaries = []

    global_step = 0
    start_all = time.time()

    # --------------------------------------------------------
    # Train
    # --------------------------------------------------------

    for epoch in range(1, EPOCHS + 1):
        dataset.set_epoch(epoch - 1)

        generator = torch.Generator()
        generator.manual_seed(SEED + epoch)

        loader = DataLoader(
            dataset,
            batch_size=BATCH_SIZE,
            shuffle=True,
            generator=generator,
            num_workers=NUM_WORKERS,
            pin_memory=True,
            persistent_workers=(NUM_WORKERS > 0),
            collate_fn=collate,
            drop_last=False,
        )

        encoder.model.train()
        epoch_loss = 0.0
        seen = 0
        epoch_start = time.time()

        for batch in loader:
            optimizer.zero_grad(set_to_none=True)

            amp_dtype = torch.bfloat16 if use_bf16 else torch.float16

            with torch.autocast(
                device_type="cuda",
                dtype=amp_dtype,
                enabled=True,
            ):
                q = encoder.encode_batch(batch["query"])
                p = encoder.encode_batch(batch["positive"])
                n = encoder.encode_batch(batch["negative"])

                # B x (2B): positives followed by explicit hard negatives.
                docs = torch.cat([p, n], dim=0)
                logits = (q @ docs.T) / TEMPERATURE

                bsz = q.size(0)
                labels = torch.arange(bsz, device=device)

                # Prevent a duplicate copy of the query's true positive
                # from being treated as a negative if the same issue happens
                # to appear elsewhere in the document bank.
                doc_ids = (
                    list(batch["positive_id"])
                    + list(batch["negative_id"])
                )

                for i, gold_id in enumerate(batch["positive_id"]):
                    for j, doc_id in enumerate(doc_ids):
                        if j != i and doc_id == gold_id:
                            logits[i, j] = torch.finfo(logits.dtype).min

                loss = F.cross_entropy(logits, labels)

            if not torch.isfinite(loss):
                raise RuntimeError(
                    f"Non-finite loss at epoch={epoch} step={global_step}: "
                    f"{loss.item()}"
                )

            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                encoder.model.parameters(),
                max_norm=1.0,
            )
            optimizer.step()
            scheduler.step()

            global_step += 1
            epoch_loss += float(loss.item()) * bsz
            seen += bsz

            if global_step % 50 == 0:
                print(
                    f"epoch={epoch} step={global_step}/{total_steps} "
                    f"loss={loss.item():.5f} "
                    f"lr={scheduler.get_last_lr()[0]:.3e}",
                    flush=True,
                )

        mean_train_loss = epoch_loss / max(1, seen)

        # ----------------------------------------------------
        # Internal full-corpus dev evaluation
        # ----------------------------------------------------

        print("\n" + "-" * 90)
        print(
            f"EPOCH {epoch} COMPLETE | "
            f"train_loss={mean_train_loss:.6f} | "
            f"time={(time.time()-epoch_start)/60:.1f} min"
        )
        print("FULL-CORPUS SYNTHETIC DEV:", flush=True)

        pooled, by_app, per_query = evaluate_full_corpus(
            encoder,
            dev,
            issue_map,
            app_issue_ids,
        )

        pd.DataFrame(per_query).to_csv(
            OUTPUT_DIR / f"epoch{epoch}_internal_per_query.csv",
            index=False,
        )

        summary = {
            "epoch": epoch,
            "global_step": global_step,
            "train_loss": mean_train_loss,
            "pooled": pooled,
            "by_app": by_app,
            "elapsed_minutes": (time.time() - start_all) / 60.0,
        }
        epoch_summaries.append(summary)
        json_dump(
            epoch_summaries,
            OUTPUT_DIR / "epoch_summaries.json",
        )

        if pooled["MRR"] > best_mrr:
            best_mrr = pooled["MRR"]
            best_epoch = epoch

            best_dir = OUTPUT_DIR / "best_model"
            if best_dir.exists():
                shutil.rmtree(best_dir)
            best_dir.mkdir(parents=True, exist_ok=True)

            encoder.model.save_pretrained(best_dir)
            encoder.tokenizer.save_pretrained(best_dir)

            best_meta = {
                "best_epoch": best_epoch,
                "best_internal_dev_MRR": best_mrr,
                "metrics": pooled,
                "by_app": by_app,
                "global_step": global_step,
                "selection_rule": (
                    "highest internal issue-disjoint full-app-corpus "
                    "pooled synthetic-dev MRR"
                ),
            }
            json_dump(
                best_meta,
                OUTPUT_DIR / "best_checkpoint.json",
            )

            volume.commit()

            print(
                f"*** NEW BEST: epoch={epoch} "
                f"MRR={best_mrr:.6f} ***",
                flush=True,
            )

        gc.collect()
        torch.cuda.empty_cache()

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    final_summary = {
        "model": MODEL_NAME,
        "seed": SEED,
        "best_epoch": best_epoch,
        "best_internal_dev_MRR": best_mrr,
        "bge_zs_internal": zs_pooled,
        "bge_ft_best_internal": next(
            x["pooled"]
            for x in epoch_summaries
            if x["epoch"] == best_epoch
        ),
        "elapsed_minutes": (time.time() - start_all) / 60.0,
        "IMPORTANT": (
            "Do not conclude real-world improvement from this internal result. "
            "Next evaluate the frozen best_model once on the existing real "
            "repository-scale test sets against the unchanged BGE-ZS baseline."
        ),
    }

    json_dump(final_summary, OUTPUT_DIR / "FINAL_SUMMARY.json")

    # Small transport bundle: config + metrics + tokenizer/config/model.
    bundle_base = str(
        Path("/tmp") / "bge_ft_seed42_controlled"
    )
    shutil.make_archive(
        bundle_base,
        "zip",
        root_dir=str(OUTPUT_DIR),
    )
    shutil.copy2(
        bundle_base + ".zip",
        OUTPUT_DIR / "bge_ft_seed42_controlled.zip",
    )

    volume.commit()

    print("\n" + "=" * 90)
    print("BGE-FT TRAINING COMPLETE")
    print("=" * 90)
    print(json.dumps(final_summary, indent=2), flush=True)
    print(
        f"\nSaved under Modal Volume '{VOLUME_NAME}': "
        f"{OUTPUT_DIR}",
        flush=True,
    )
    print(
        "Bundle: "
        f"{OUTPUT_DIR / 'bge_ft_seed42_controlled.zip'}",
        flush=True,
    )

    return final_summary


@app.local_entrypoint()
def main():
    print("=" * 90)
    print("STEP 1/2: FREE/CPU DATA VALIDATION")
    print("=" * 90)
    validation = validate_data.remote()
    print(json.dumps(validation, indent=2))

    print("\n" + "=" * 90)
    print("STEP 2/2: ONE A100 TRAINING RUN — BGE seed 42")
    print("=" * 90)
    print(
        "This is intentionally NOT a hyperparameter sweep. "
        "External real data is untouched during checkpoint selection.\n"
    )

    result = train_bge.remote()
    print("\nFINAL RESULT")
    print(json.dumps(result, indent=2))
