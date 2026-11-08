#!/usr/bin/env python3
"""Train and evaluate SPLADE-SE on the already-created bottom-15%-filtered data.

This variant adds epoch-boundary resume support for durable cloud runs.  It
saves the model, optimizer, scheduler, RNG states, loader generator, history,
and best-checkpoint metadata after every validation epoch.

Kaggle usage (one independent notebook/session per seed):

    !python /kaggle/working/splade_bottom15_multiseed.py --seed 13 --dry-run
    !python /kaggle/working/splade_bottom15_multiseed.py --seed 13
    !python /kaggle/working/splade_bottom15_multiseed.py --seed 13 --resume

Final seeds: 13, 21, 42, 87, 100.  The data split is intentionally fixed at
split seed 42; only training randomness changes between runs.

The script expects the same Kaggle inputs used by spladetraining (4).ipynb:
  * bottom15_llm/training_triplets.csv
  * bottom15_llm/synthetic_pairs_filtered.csv
  * the four original issue CSVs
  * the three external *_matching.csv evaluation datasets

It never calls an LLM and never recreates the filter.  It verifies that the
input already contains 7,944 retained queries and 62,515 triplets, reconstructs
all issue texts (including hard-negative issues), uses a query-disjoint fixed
validation split, and saves aggregate plus per-query evaluation outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForMaskedLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)


EXPECTED_RETAINED_QUERIES = 7_944
EXPECTED_REMOVED_QUERIES = 1_405
EXPECTED_TRIPLETS = 62_515
MODEL_NAME = "naver/splade-cocondenser-ensembledistil"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True, help="Training seed")
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--output-root", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="Validate data only")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last completed epoch when a durable checkpoint exists",
    )
    return parser.parse_args()


def json_dump(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, ensure_ascii=False)


def sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_id(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def clean_scalar(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def format_issue(title: object, body: object, labels: object) -> str:
    title_text = clean_scalar(title)
    body_text = clean_scalar(body)
    labels_text = clean_scalar(labels)
    return f"{title_text}\n\n{body_text}\n\nLabels: {labels_text}".strip()


def find_bottom15_dir(input_root: Path) -> Path:
    candidates: List[Path] = []
    for triplet_path in input_root.rglob("training_triplets.csv"):
        parent = triplet_path.parent
        if (parent / "synthetic_pairs_filtered.csv").exists():
            candidates.append(parent)

    if not candidates:
        raise FileNotFoundError(
            "No directory under /kaggle/input contains both training_triplets.csv "
            "and synthetic_pairs_filtered.csv"
        )

    # Prefer the artifact explicitly named bottom15_llm and then the notebook's
    # uploaded 'trivlet' dataset.  Counts are verified immediately afterward.
    candidates.sort(
        key=lambda p: (
            p.name != "bottom15_llm",
            "trivlet" not in str(p).lower(),
            len(str(p)),
        )
    )
    print("Bottom-15 candidates:")
    for candidate in candidates:
        print(" ", candidate)
    print("Using bottom-15 directory:", candidates[0])
    return candidates[0]


def find_exact_file(input_root: Path, basename: str) -> Path:
    wanted_name = basename.lower()
    wanted_stem = Path(basename).stem.lower()
    matches = []
    for path in input_root.rglob("*.csv"):
        candidate_name = path.name.lower()
        # Kaggle may rename duplicate uploads to names such as
        # "brave_issues (1).csv".  Accept that suffix without relaxing the
        # semantic file match.
        candidate_stem = re.sub(r"\s*\(\d+\)$", "", path.stem.lower())
        if candidate_name == wanted_name or candidate_stem == wanted_stem:
            matches.append(path)
    if not matches:
        raise FileNotFoundError(f"Missing {basename} under {input_root}")
    matches.sort(
        key=lambda p: (
            p.name.lower() != wanted_name,
            "spladetrainingv12" not in str(p).lower(),
            len(str(p)),
        )
    )
    return matches[0]


def select_body(df: pd.DataFrame) -> pd.Series:
    if "clean_body" in df.columns and "body" in df.columns:
        return df["clean_body"].where(df["clean_body"].notna(), df["body"])
    if "clean_body" in df.columns:
        return df["clean_body"]
    if "body" in df.columns:
        return df["body"]
    return pd.Series([""] * len(df), index=df.index)


def load_original_issue_map(input_root: Path) -> Dict[str, str]:
    sources = {
        "signal": "Signal-Android_Mistral_Ready.csv",
        "ankidroid": "Anki-Android_Mistral_Ready.csv",
        "k9": "k-9_Mistral_Ready.csv",
        "brave": "brave_issues.csv",
    }

    issue_map: Dict[str, str] = {}
    for app, basename in sources.items():
        path = find_exact_file(input_root, basename)
        frame = pd.read_csv(path)
        number_col = "issue_number" if "issue_number" in frame.columns else "number"
        if number_col not in frame.columns:
            raise KeyError(f"Neither issue_number nor number found in {path}")

        titles = frame["title"] if "title" in frame.columns else pd.Series([""] * len(frame))
        bodies = select_body(frame)
        if "issue_labels" in frame.columns:
            labels = frame["issue_labels"]
        elif "labels" in frame.columns:
            labels = frame["labels"]
        else:
            labels = pd.Series([""] * len(frame), index=frame.index)

        for number, title, body, label in zip(frame[number_col], titles, bodies, labels):
            issue_id = f"{app}-{norm_id(number)}"
            issue_map[issue_id] = format_issue(title, body, label)

        print(f"Loaded {len(frame):,} issues for {app}: {path.name}")

    return issue_map


def validate_and_build_training_frame(
    input_root: Path,
    bottom15_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, Mapping[str, object]]:
    triplet_path = bottom15_dir / "training_triplets.csv"
    pairs_path = bottom15_dir / "synthetic_pairs_filtered.csv"
    removed_path = bottom15_dir / "removed_examples.csv"
    counts_path = bottom15_dir / "filter_counts.json"

    triplets = pd.read_csv(triplet_path)
    pairs = pd.read_csv(pairs_path)

    required_triplet_columns = {
        "query_review_id",
        "positive_issue_id",
        "negative_issue_id",
    }
    required_pair_columns = {
        "review_id",
        "generated_review",
        "issue_id",
        "issue_title",
        "issue_body",
    }
    if not required_triplet_columns.issubset(triplets.columns):
        raise KeyError(f"Triplet columns are {triplets.columns.tolist()}")
    if not required_pair_columns.issubset(pairs.columns):
        raise KeyError(f"Filtered-pair columns are {pairs.columns.tolist()}")

    for col in required_triplet_columns:
        triplets[col] = triplets[col].map(norm_id)
    pairs["review_id"] = pairs["review_id"].map(norm_id)
    pairs["issue_id"] = pairs["issue_id"].map(norm_id)

    retained_queries = pairs["review_id"].nunique()
    if retained_queries != EXPECTED_RETAINED_QUERIES:
        raise AssertionError(
            f"Expected {EXPECTED_RETAINED_QUERIES:,} retained reviews, got "
            f"{retained_queries:,}. Refusing to train on the wrong artifact."
        )
    if len(triplets) != EXPECTED_TRIPLETS:
        raise AssertionError(
            f"Expected {EXPECTED_TRIPLETS:,} triplets, got {len(triplets):,}. "
            "Refusing to train on the wrong artifact."
        )
    removed_examples_rows = None
    if removed_path.exists():
        # This artifact is a small qualitative preview, not necessarily the
        # complete set of removed reviews.  The full count is recorded in
        # filter_counts.json and is also implied by 9,349 - 7,944 = 1,405.
        removed_examples_rows = len(pd.read_csv(removed_path))
        if not 0 < removed_examples_rows <= EXPECTED_REMOVED_QUERIES:
            raise AssertionError(
                f"Invalid removed-examples preview size: {removed_examples_rows:,}."
            )

    pair_review_counts = pairs.groupby("review_id")["generated_review"].nunique(dropna=False)
    if int(pair_review_counts.max()) != 1:
        raise AssertionError("A review_id maps to multiple generated-review texts")

    review_map = dict(
        zip(pairs["review_id"], pairs["generated_review"].map(clean_scalar))
    )

    # Preserve the exact positive-issue formatting used in the notebook, then
    # fill hard-negative issue IDs from the four original issue files.  The old
    # cell omitted this second step and silently lost 9,140 triplets.
    labels_col = "issue_labels" if "issue_labels" in pairs.columns else None
    issue_map: Dict[str, str] = {}
    for row in pairs.itertuples(index=False):
        label_value = getattr(row, labels_col) if labels_col else ""
        issue_map[norm_id(row.issue_id)] = format_issue(
            row.issue_title,
            row.issue_body,
            label_value,
        )

    needed_issue_ids = set(triplets["positive_issue_id"]) | set(triplets["negative_issue_id"])
    missing_before = needed_issue_ids - set(issue_map)
    print(f"Issue IDs absent from filtered positive pairs: {len(missing_before):,}")

    original_issue_map = load_original_issue_map(input_root)
    for issue_id in missing_before:
        if issue_id in original_issue_map:
            issue_map[issue_id] = original_issue_map[issue_id]

    frame = triplets.copy()
    frame["query_id"] = frame["query_review_id"]
    frame["query"] = frame["query_review_id"].map(review_map)
    frame["positive"] = frame["positive_issue_id"].map(issue_map)
    frame["negative"] = frame["negative_issue_id"].map(issue_map)

    missing_mask = frame[["query", "positive", "negative"]].isna().any(axis=1)
    if missing_mask.any():
        bad = frame.loc[
            missing_mask,
            ["query_review_id", "positive_issue_id", "negative_issue_id"],
        ].head(20)
        raise AssertionError(
            f"{int(missing_mask.sum()):,} triplets still lack text. Examples:\n{bad}"
        )

    if len(frame) != EXPECTED_TRIPLETS:
        raise AssertionError("Triplet reconstruction changed row count")
    if not set(frame["query_id"]).issubset(set(pairs["review_id"])):
        raise AssertionError("A training query is not in the retained bottom-15 pair file")

    filter_counts: Mapping[str, object] = {}
    if counts_path.exists():
        with counts_path.open("r", encoding="utf-8") as handle:
            filter_counts = json.load(handle)

    print("Verified bottom-15 artifact:")
    print(f"  retained queries: {retained_queries:,}")
    print(f"  removed queries:  {EXPECTED_REMOVED_QUERIES:,}")
    print(f"  removed percent:  {100 * EXPECTED_REMOVED_QUERIES / (EXPECTED_RETAINED_QUERIES + EXPECTED_REMOVED_QUERIES):.2f}%")
    print(f"  usable triplets:  {len(frame):,} / {len(triplets):,}")

    metadata = {
        "bottom15_dir": str(bottom15_dir),
        "triplet_sha256": sha256(triplet_path),
        "pairs_sha256": sha256(pairs_path),
        "retained_queries": int(retained_queries),
        "removed_queries": EXPECTED_REMOVED_QUERIES,
        "removed_examples_preview_rows": removed_examples_rows,
        "triplets": int(len(frame)),
        "filter_counts": filter_counts,
    }
    return frame, pairs, metadata


def make_fixed_query_split(
    frame: pd.DataFrame,
    split_seed: int,
    valid_fraction: float = 0.10,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    query_ids = np.array(sorted(frame["query_id"].unique()), dtype=object)
    rng = np.random.RandomState(split_seed)
    shuffled = query_ids.copy()
    rng.shuffle(shuffled)
    valid_count = max(1, int(round(len(shuffled) * valid_fraction)))
    valid_ids = set(shuffled[:valid_count].tolist())

    valid_frame = frame[frame["query_id"].isin(valid_ids)].copy()
    train_frame = frame[~frame["query_id"].isin(valid_ids)].copy()
    train_frame = train_frame.reset_index(drop=True)
    valid_frame = valid_frame.sort_values(
        ["query_id", "positive_issue_id", "negative_issue_id"]
    ).reset_index(drop=True)

    if set(train_frame["query_id"]) & set(valid_frame["query_id"]):
        raise AssertionError("Query leakage between train and validation sets")

    split_manifest = pd.DataFrame(
        {
            "query_id": query_ids,
            "split": ["validation" if q in valid_ids else "train" for q in query_ids],
        }
    ).sort_values("query_id")

    print("Fixed query-disjoint split:")
    print(
        f"  train: {train_frame['query_id'].nunique():,} queries / "
        f"{len(train_frame):,} triplets"
    )
    print(
        f"  valid: {valid_frame['query_id'].nunique():,} queries / "
        f"{len(valid_frame):,} triplets"
    )
    return train_frame, valid_frame, split_manifest


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class TripletDataset(Dataset):
    def __init__(self, frame: pd.DataFrame):
        self.query = frame["query"].astype(str).tolist()
        self.positive = frame["positive"].astype(str).tolist()
        self.negative = frame["negative"].astype(str).tolist()

    def __len__(self) -> int:
        return len(self.query)

    def __getitem__(self, index: int) -> Tuple[str, str, str]:
        return self.query[index], self.positive[index], self.negative[index]


class SpladeEncoder(nn.Module):
    def __init__(self, model_name_or_path: str | Path):
        super().__init__()
        self.model = AutoModelForMaskedLM.from_pretrained(model_name_or_path)
        if hasattr(self.model, "gradient_checkpointing_enable"):
            self.model.gradient_checkpointing_enable()
        if hasattr(self.model.config, "use_cache"):
            self.model.config.use_cache = False

    def forward(self, batch: Mapping[str, torch.Tensor], device: torch.device) -> torch.Tensor:
        moved = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
        logits = self.model(**moved).logits
        attention = moved["attention_mask"].unsqueeze(-1)
        values = torch.log1p(torch.relu(logits)) * attention
        return torch.max(values, dim=1).values


def worker_seed_init(worker_id: int) -> None:
    worker_seed = torch.initial_seed() % (2**32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def train_model(
    args: argparse.Namespace,
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    run_dir: Path,
    run_metadata: Mapping[str, object],
) -> Path:
    seed_everything(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Final training requires a CUDA GPU")

    max_length = 128
    temperature = 1.0
    splade_lambda = 1e-4
    learning_rate = 2e-5
    weight_decay = 0.01
    warmup_ratio = 0.10

    checkpoints = run_dir / "checkpoints"
    best_dir = checkpoints / "best"
    last_dir = checkpoints / "last"
    resume_path = checkpoints / "resume_state.pt"
    checkpoints.mkdir(parents=True, exist_ok=True)

    resume_state = None
    if args.resume and resume_path.exists():
        try:
            resume_state = torch.load(
                resume_path,
                map_location="cpu",
                weights_only=False,
            )
        except TypeError:
            resume_state = torch.load(resume_path, map_location="cpu")
        if not (last_dir / "config.json").exists():
            raise FileNotFoundError(
                f"Resume state exists but the last model is missing: {last_dir}"
            )
        if int(resume_state["train_seed"]) != args.seed:
            raise ValueError("Resume checkpoint training seed does not match --seed")
        if int(resume_state["split_seed"]) != args.split_seed:
            raise ValueError("Resume checkpoint split seed does not match --split-seed")
        if resume_state["dataset_triplet_sha256"] != run_metadata["triplet_sha256"]:
            raise ValueError("Resume checkpoint was created from different triplets")
        if resume_state["dataset_pairs_sha256"] != run_metadata["pairs_sha256"]:
            raise ValueError("Resume checkpoint was created from different pairs")
        model_source: str | Path = last_dir
        print(
            "RESUMING from completed epoch "
            f"{resume_state['epoch']} / step {resume_state['global_step']}"
        )
    else:
        model_source = MODEL_NAME
        if args.resume:
            print("No completed-epoch checkpoint found; starting this seed from scratch.")

    tokenizer = AutoTokenizer.from_pretrained(model_source)

    def collate(batch: Sequence[Tuple[str, str, str]]):
        query, positive, negative = zip(*batch)

        def tokenize(texts: Sequence[str]):
            return tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )

        return tokenize(query), tokenize(positive), tokenize(negative)

    generator = torch.Generator()
    generator.manual_seed(args.seed)
    if resume_state is not None and "loader_generator_state" in resume_state:
        generator.set_state(resume_state["loader_generator_state"])
    loader_kwargs = {
        "batch_size": args.batch_size,
        "collate_fn": collate,
        "num_workers": args.num_workers,
        "pin_memory": True,
    }
    if args.num_workers > 0:
        loader_kwargs["worker_init_fn"] = worker_seed_init
        loader_kwargs["persistent_workers"] = True

    train_loader = DataLoader(
        TripletDataset(train_frame),
        shuffle=True,
        generator=generator,
        **loader_kwargs,
    )
    valid_loader = DataLoader(
        TripletDataset(valid_frame),
        shuffle=False,
        **loader_kwargs,
    )

    model = SpladeEncoder(model_source).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    optimizer_steps_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
    total_steps = optimizer_steps_per_epoch * args.epochs
    warmup_steps = int(total_steps * warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )
    if resume_state is not None:
        optimizer.load_state_dict(resume_state["optimizer"])
        scheduler.load_state_dict(resume_state["scheduler"])

    config = {
        **run_metadata,
        "status": "running",
        "train_seed": args.seed,
        "split_seed": args.split_seed,
        "model_name": MODEL_NAME,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.grad_accum,
        "effective_batch_size": args.batch_size * args.grad_accum,
        "max_length": max_length,
        "temperature": temperature,
        "splade_lambda": splade_lambda,
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "warmup_ratio": warmup_ratio,
        "train_queries": int(train_frame["query_id"].nunique()),
        "valid_queries": int(valid_frame["query_id"].nunique()),
        "train_triplets": int(len(train_frame)),
        "valid_triplets": int(len(valid_frame)),
        "optimizer_steps_per_epoch": optimizer_steps_per_epoch,
        "total_optimizer_steps": total_steps,
        "torch_version": torch.__version__,
        "transformers_version": __import__("transformers").__version__,
        "python_version": sys.version,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0),
    }
    json_dump(config, run_dir / "run_config.json")

    def loss_function(query, positive, negative):
        positive_score = torch.sum(query * positive, dim=1)
        negative_score = torch.sum(query * negative, dim=1)
        logits = torch.stack([positive_score, negative_score], dim=1) / temperature
        labels = torch.zeros(logits.size(0), dtype=torch.long, device=device)
        ce = F.cross_entropy(logits, labels)
        l1 = (query.mean() + positive.mean() + negative.mean()) / 3.0
        return ce + splade_lambda * l1, ce.detach(), l1.detach()

    @torch.no_grad()
    def validate() -> Tuple[float, float, float]:
        model.eval()
        loss_values: List[float] = []
        ce_values: List[float] = []
        l1_values: List[float] = []
        for query_tokens, positive_tokens, negative_tokens in valid_loader:
            query = model(query_tokens, device)
            positive = model(positive_tokens, device)
            negative = model(negative_tokens, device)
            loss, ce, l1 = loss_function(query, positive, negative)
            loss_values.append(float(loss.item()))
            ce_values.append(float(ce.item()))
            l1_values.append(float(l1.item()))
        model.train()
        return (
            float(np.mean(loss_values)),
            float(np.mean(ce_values)),
            float(np.mean(l1_values)),
        )

    def save_model(path: Path, epoch: int, global_step: int, val_loss: float) -> None:
        path.mkdir(parents=True, exist_ok=True)
        model.model.save_pretrained(path, safe_serialization=True)
        tokenizer.save_pretrained(path)
        json_dump(
            {
                "epoch": epoch,
                "global_step": global_step,
                "validation_loss": val_loss,
                "train_seed": args.seed,
                "split_seed": args.split_seed,
                "dataset_triplet_sha256": run_metadata["triplet_sha256"],
                "dataset_pairs_sha256": run_metadata["pairs_sha256"],
            },
            path / "training_state.json",
        )

    def save_resume_state(
        epoch: int,
        global_step: int,
        best_validation_loss: float,
        best_epoch: int,
        elapsed_minutes: float,
        history: List[Mapping[str, object]],
    ) -> None:
        payload = {
            "format_version": 1,
            "epoch": epoch,
            "global_step": global_step,
            "best_validation_loss": best_validation_loss,
            "best_epoch": best_epoch,
            "elapsed_minutes": elapsed_minutes,
            "train_seed": args.seed,
            "split_seed": args.split_seed,
            "dataset_triplet_sha256": run_metadata["triplet_sha256"],
            "dataset_pairs_sha256": run_metadata["pairs_sha256"],
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "loader_generator_state": generator.get_state(),
            "python_rng_state": random.getstate(),
            "numpy_rng_state": np.random.get_state(),
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_states": torch.cuda.get_rng_state_all(),
            "history": history,
        }
        temporary_path = resume_path.with_suffix(".pt.tmp")
        torch.save(payload, temporary_path)
        os.replace(temporary_path, resume_path)

    if resume_state is None:
        history: List[Mapping[str, object]] = []
        best_validation_loss = float("inf")
        best_epoch = 0
        global_step = 0
        start_epoch = 1
        elapsed_before_resume = 0.0
    else:
        history = list(resume_state.get("history", []))
        best_validation_loss = float(resume_state["best_validation_loss"])
        best_epoch = int(resume_state["best_epoch"])
        global_step = int(resume_state["global_step"])
        start_epoch = int(resume_state["epoch"]) + 1
        elapsed_before_resume = float(resume_state.get("elapsed_minutes", 0.0))
        random.setstate(resume_state["python_rng_state"])
        np.random.set_state(resume_state["numpy_rng_state"])
        torch.set_rng_state(resume_state["torch_rng_state"])
        torch.cuda.set_rng_state_all(resume_state["cuda_rng_states"])

    started = time.time() - elapsed_before_resume * 60.0

    print("\nTraining configuration")
    print(json.dumps(config, indent=2, default=str))
    model.train()

    if start_epoch > args.epochs:
        print("All requested training epochs were already completed.")
        del model
        torch.cuda.empty_cache()
        return best_dir

    for epoch in range(start_epoch, args.epochs + 1):
        optimizer.zero_grad(set_to_none=True)
        accumulation_count = 0
        interval_loss: List[float] = []
        interval_ce: List[float] = []
        interval_l1: List[float] = []
        print(f"\nEpoch {epoch}/{args.epochs}")

        for batch_index, (query_tokens, positive_tokens, negative_tokens) in enumerate(
            train_loader,
            start=1,
        ):
            query = model(query_tokens, device)
            positive = model(positive_tokens, device)
            negative = model(negative_tokens, device)
            loss, ce, l1 = loss_function(query, positive, negative)
            (loss / args.grad_accum).backward()
            accumulation_count += 1

            interval_loss.append(float(loss.item()))
            interval_ce.append(float(ce.item()))
            interval_l1.append(float(l1.item()))

            is_last_batch = batch_index == len(train_loader)
            if accumulation_count == args.grad_accum or is_last_batch:
                # Correct the final partial accumulation group instead of
                # silently under-weighting it.
                if accumulation_count < args.grad_accum:
                    correction = args.grad_accum / accumulation_count
                    for parameter in model.parameters():
                        if parameter.grad is not None:
                            parameter.grad.mul_(correction)

                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                accumulation_count = 0
                global_step += 1

                if global_step % 25 == 0:
                    elapsed_minutes = (time.time() - started) / 60
                    rate = global_step / max(elapsed_minutes, 1e-9)
                    eta_minutes = (total_steps - global_step) / max(rate, 1e-9)
                    record = {
                        "kind": "train",
                        "seed": args.seed,
                        "epoch": epoch,
                        "global_step": global_step,
                        "loss": float(np.mean(interval_loss[-25:])),
                        "ce": float(np.mean(interval_ce[-25:])),
                        "l1": float(np.mean(interval_l1[-25:])),
                        "elapsed_minutes": elapsed_minutes,
                        "eta_minutes": eta_minutes,
                    }
                    history.append(record)
                    print(
                        f"step={global_step}/{total_steps} "
                        f"loss={record['loss']:.4f} ce={record['ce']:.4f} "
                        f"l1={record['l1']:.4f} elapsed={elapsed_minutes:.1f}m "
                        f"eta={eta_minutes:.1f}m",
                        flush=True,
                    )

        validation_loss, validation_ce, validation_l1 = validate()
        validation_record = {
            "kind": "validation",
            "seed": args.seed,
            "epoch": epoch,
            "global_step": global_step,
            "loss": validation_loss,
            "ce": validation_ce,
            "l1": validation_l1,
            "elapsed_minutes": (time.time() - started) / 60,
        }
        history.append(validation_record)
        print(
            f"VALID epoch={epoch} step={global_step} "
            f"loss={validation_loss:.4f} ce={validation_ce:.4f} "
            f"l1={validation_l1:.4f}"
        )

        save_model(last_dir, epoch, global_step, validation_loss)
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_epoch = epoch
            save_model(best_dir, epoch, global_step, validation_loss)
            print(f"NEW BEST epoch={epoch} validation_loss={validation_loss:.4f}")

        pd.DataFrame(history).to_csv(run_dir / "training_history.csv", index=False)
        save_resume_state(
            epoch=epoch,
            global_step=global_step,
            best_validation_loss=best_validation_loss,
            best_epoch=best_epoch,
            elapsed_minutes=(time.time() - started) / 60,
            history=history,
        )
        print(f"DURABLE CHECKPOINT epoch={epoch} saved to {resume_path}", flush=True)

    config.update(
        {
            "status": "training_complete",
            "best_epoch": best_epoch,
            "best_validation_loss": best_validation_loss,
            "completed_optimizer_steps": global_step,
            "elapsed_minutes": (time.time() - started) / 60,
        }
    )
    json_dump(config, run_dir / "run_config.json")
    archive = args.output_root / f"splade_bottom15_seed{args.seed}_best"
    if archive.with_suffix(".zip").exists():
        archive.with_suffix(".zip").unlink()
    shutil.make_archive(str(archive), "zip", best_dir)
    print("Training complete. Best checkpoint:", best_dir)
    print("Checkpoint ZIP:", archive.with_suffix(".zip"))

    del model
    torch.cuda.empty_cache()
    return best_dir


def find_evaluation_files(input_root: Path) -> List[Path]:
    wanted = {
        "dolphin_emulator_issues_matching.csv",
        "jitsi_communication_issues_matching.csv",
        "ppsspp_emulator_issues_matching.csv",
    }
    matches: Dict[str, List[Path]] = {name: [] for name in wanted}
    for path in input_root.rglob("*.csv"):
        if path.name.lower() in wanted:
            matches[path.name.lower()].append(path)

    selected: List[Path] = []
    for name in sorted(wanted):
        paths = matches[name]
        if not paths:
            raise FileNotFoundError(f"Missing evaluation file: {name}")
        paths.sort(key=lambda p: ("matchessss" not in str(p).lower(), len(str(p))))
        selected.append(paths[0])
    return selected


def prepare_evaluation_data(frame: pd.DataFrame):
    required = {"issue_id", "issue_text", "issue_body", "review_id", "review_text"}
    if not required.issubset(frame.columns):
        raise KeyError(f"Evaluation columns are {frame.columns.tolist()}")

    issues = frame[["issue_id", "issue_text", "issue_body"]].drop_duplicates("issue_id")
    issues = issues.reset_index(drop=True)
    issue_ids = issues["issue_id"].map(norm_id).tolist()
    issue_texts = [
        f"{clean_scalar(row.issue_text)} {clean_scalar(row.issue_body)[:500]}".strip()
        for row in issues.itertuples(index=False)
    ]
    issue_to_index = {issue_id: index for index, issue_id in enumerate(issue_ids)}

    reviews = frame[["review_id", "review_text"]].drop_duplicates("review_id")
    reviews = reviews.reset_index(drop=True)
    review_ids = reviews["review_id"].map(norm_id).tolist()
    review_texts = reviews["review_text"].map(clean_scalar).tolist()
    review_to_index = {review_id: index for index, review_id in enumerate(review_ids)}

    ground_truth: Dict[int, Set[int]] = {}
    for row in frame.itertuples(index=False):
        review_index = review_to_index[norm_id(row.review_id)]
        issue_index = issue_to_index[norm_id(row.issue_id)]
        ground_truth.setdefault(review_index, set()).add(issue_index)
    return review_ids, review_texts, issue_ids, issue_texts, ground_truth


def evaluate_model(
    args: argparse.Namespace,
    checkpoint: Path,
    run_dir: Path,
) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = SpladeEncoder(checkpoint).to(device)
    model.eval()

    @torch.no_grad()
    def encode(texts: Sequence[str], batch_size: int = 8) -> torch.Tensor:
        vectors: List[torch.Tensor] = []
        for start in range(0, len(texts), batch_size):
            tokens = tokenizer(
                list(texts[start : start + batch_size]),
                max_length=128,
                truncation=True,
                padding=True,
                return_tensors="pt",
            )
            vectors.append(model(tokens, device).cpu())
        return torch.cat(vectors, dim=0)

    aggregate_rows: List[Mapping[str, object]] = []
    per_query_rows: List[Mapping[str, object]] = []
    ranking_rows: List[Mapping[str, object]] = []

    for test_path in find_evaluation_files(args.input_root):
        dataset = (
            test_path.name.replace("_issues_matching.csv", "")
            .replace("_matching.csv", "")
            .replace("_", " ")
            .title()
        )
        frame = pd.read_csv(test_path)
        review_ids, review_texts, issue_ids, issue_texts, ground_truth = prepare_evaluation_data(frame)
        print(f"Evaluating {dataset}: {len(review_ids)} reviews / {len(issue_ids)} issues")

        review_vectors = encode(review_texts)
        issue_vectors = encode(issue_texts)
        similarity = torch.mm(review_vectors, issue_vectors.t()).numpy()

        for review_index, review_id in enumerate(review_ids):
            order = np.argsort(similarity[review_index])[::-1].tolist()
            relevant = ground_truth.get(review_index, set())
            relevant_ranks = [rank for rank, idx in enumerate(order, start=1) if idx in relevant]
            best_rank = min(relevant_ranks) if relevant_ranks else 0
            reciprocal_rank = 1.0 / best_rank if best_rank else 0.0
            dcg10 = sum(
                1.0 / np.log2(rank + 1)
                for rank, idx in enumerate(order[:10], start=1)
                if idx in relevant
            )
            # This matches the notebook's reported NDCG implementation.  The
            # supplied datasets normally have one relevant issue per review.
            ndcg10 = float(dcg10)
            per_query_rows.append(
                {
                    "seed": args.seed,
                    "dataset": dataset,
                    "review_id": review_id,
                    "relevant_issue_ids": "|".join(issue_ids[idx] for idx in sorted(relevant)),
                    "best_relevant_rank": best_rank,
                    "hit_at_1": int(bool(best_rank and best_rank <= 1)),
                    "hit_at_5": int(bool(best_rank and best_rank <= 5)),
                    "hit_at_10": int(bool(best_rank and best_rank <= 10)),
                    "reciprocal_rank": reciprocal_rank,
                    "ndcg_at_10": ndcg10,
                }
            )
            top20 = order[:20]
            ranking_rows.append(
                {
                    "seed": args.seed,
                    "dataset": dataset,
                    "review_id": review_id,
                    "relevant_issue_ids": [issue_ids[idx] for idx in sorted(relevant)],
                    "top20_issue_ids": [issue_ids[idx] for idx in top20],
                    "top20_scores": [float(similarity[review_index, idx]) for idx in top20],
                }
            )

        dataset_rows = [
            row
            for row in per_query_rows
            if row["seed"] == args.seed and row["dataset"] == dataset
        ]
        aggregate = {
            "seed": args.seed,
            "dataset": dataset,
            "queries": len(dataset_rows),
            "R@1": float(np.mean([row["hit_at_1"] for row in dataset_rows])),
            "R@5": float(np.mean([row["hit_at_5"] for row in dataset_rows])),
            "R@10": float(np.mean([row["hit_at_10"] for row in dataset_rows])),
            "MRR": float(np.mean([row["reciprocal_rank"] for row in dataset_rows])),
            "NDCG@10": float(np.mean([row["ndcg_at_10"] for row in dataset_rows])),
        }
        aggregate_rows.append(aggregate)
        print(aggregate)
        del review_vectors, issue_vectors, similarity
        torch.cuda.empty_cache()

    pd.DataFrame(aggregate_rows).to_csv(run_dir / "evaluation_summary.csv", index=False)
    pd.DataFrame(per_query_rows).to_csv(run_dir / "evaluation_per_query.csv", index=False)
    with (run_dir / "evaluation_rankings_top20.jsonl").open("w", encoding="utf-8") as handle:
        for row in ranking_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    config_path = run_dir / "run_config.json"
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    config["status"] = "complete"
    config["evaluation_datasets"] = [row["dataset"] for row in aggregate_rows]
    json_dump(config, config_path)
    (run_dir / "COMPLETED").write_text("training and evaluation complete\n", encoding="utf-8")
    print("Saved evaluation summary and per-query outputs to", run_dir)


def main() -> None:
    args = parse_args()
    args.input_root = args.input_root.resolve()
    args.output_root = args.output_root.resolve()
    suffix = "_dryrun" if args.dry_run else ""
    run_dir = args.output_root / f"splade_bottom15_seed{args.seed}{suffix}"

    if (run_dir / "COMPLETED").exists() and not args.dry_run:
        print(f"Seed {args.seed} is already complete: {run_dir}")
        return

    if (
        run_dir.exists()
        and any(run_dir.iterdir())
        and not args.dry_run
        and not args.resume
    ):
        raise FileExistsError(
            f"{run_dir} already contains files. Pass --resume only when these files "
            "belong to the same seed, split, dataset, and training configuration."
        )
    run_dir.mkdir(parents=True, exist_ok=True)

    bottom15_dir = find_bottom15_dir(args.input_root)
    frame, pairs, dataset_metadata = validate_and_build_training_frame(
        args.input_root,
        bottom15_dir,
    )
    train_frame, valid_frame, split_manifest = make_fixed_query_split(
        frame,
        split_seed=args.split_seed,
    )
    split_manifest.to_csv(run_dir / "split_manifest.csv", index=False)
    json_dump(dataset_metadata, run_dir / "dataset_verification.json")

    if args.dry_run:
        print("\nDRY RUN PASSED: bottom 15% is removed and all 62,515 triplets are usable.")
        print("Now rerun the same command without --dry-run.")
        return

    checkpoint = train_model(
        args,
        train_frame,
        valid_frame,
        run_dir,
        dataset_metadata,
    )
    if args.skip_eval:
        (run_dir / "TRAINING_COMPLETED").write_text("training complete\n", encoding="utf-8")
        print("Evaluation skipped by request.")
    else:
        evaluate_model(args, checkpoint, run_dir)


if __name__ == "__main__":
    main()
