"""Template for single-stage review-to-issue retrieval evaluation.

This script computes ranking metrics when the user provides local files with
review texts, issue texts, and review--issue ground truth. It intentionally
does not hardcode APPRISE or Kaggle paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml
from rank_bm25 import BM25Okapi


def compute_metrics(rankings: dict[str, list[str]], ground_truth: dict[str, set[str]]) -> dict[str, float]:
    n = len(rankings)
    if n == 0:
        raise ValueError("No rankings to evaluate")
    result: dict[str, float] = {}
    for k in (1, 5, 10):
        hits = sum(bool(set(ranking[:k]) & ground_truth.get(qid, set())) for qid, ranking in rankings.items())
        result[f"R@{k}"] = hits / n
    rr = 0.0
    ndcg = 0.0
    for qid, ranking in rankings.items():
        relevant = ground_truth.get(qid, set())
        rr += next((1.0 / rank for rank, doc_id in enumerate(ranking, start=1) if doc_id in relevant), 0.0)
        dcg = sum(1.0 / np.log2(rank + 1) for rank, doc_id in enumerate(ranking[:10], start=1) if doc_id in relevant)
        ndcg += dcg
    result["MRR"] = rr / n
    result["NDCG@10"] = ndcg / n
    return result


def bm25_rankings(reviews: pd.DataFrame, issues: pd.DataFrame) -> dict[str, list[str]]:
    issue_ids = issues["issue_id"].astype(str).tolist()
    issue_texts = issues["issue_text"].astype(str).tolist()
    tokenized = [text.lower().split() for text in issue_texts]
    bm25 = BM25Okapi(tokenized)
    rankings: dict[str, list[str]] = {}
    for _, row in reviews.iterrows():
        qid = str(row["review_id"])
        scores = bm25.get_scores(str(row["review_text"]).lower().split())
        order = np.argsort(scores)[::-1]
        rankings[qid] = [issue_ids[i] for i in order]
    return rankings


def load_ground_truth(path: Path) -> dict[str, set[str]]:
    gt_df = pd.read_csv(path)
    required = {"review_id", "issue_id"}
    if not required.issubset(gt_df.columns):
        raise ValueError(f"Ground-truth file must contain {sorted(required)}")
    gt: dict[str, set[str]] = {}
    for _, row in gt_df.iterrows():
        gt.setdefault(str(row["review_id"]), set()).add(str(row["issue_id"]))
    return gt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, help="Optional YAML config for documentation/reproducibility")
    parser.add_argument("--reviews", type=Path, help="CSV with review_id,review_text")
    parser.add_argument("--issues", type=Path, help="CSV with issue_id,issue_text")
    parser.add_argument("--ground_truth", type=Path, help="CSV with review_id,issue_id")
    parser.add_argument("--output", type=Path, default=Path("single_stage_metrics.csv"))
    args = parser.parse_args()

    if args.config:
        print(yaml.safe_load(args.config.read_text()))

    if not (args.reviews and args.issues and args.ground_truth):
        print("Template mode: provide --reviews --issues --ground_truth to compute metrics.")
        return

    reviews = pd.read_csv(args.reviews)
    issues = pd.read_csv(args.issues)
    gt = load_ground_truth(args.ground_truth)
    rankings = bm25_rankings(reviews, issues)
    metrics = compute_metrics(rankings, gt)
    pd.DataFrame([metrics]).to_csv(args.output, index=False)
    print(metrics)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

