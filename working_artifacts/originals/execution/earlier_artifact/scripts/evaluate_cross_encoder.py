"""Template for secondary cross-encoder re-ranking evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sentence_transformers import CrossEncoder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, help="CSV with review_id,review_text,issue_id,issue_text,rank")
    parser.add_argument("--output", type=Path, default=Path("cross_encoder_reranked.csv"))
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-12-v2")
    parser.add_argument("--top_k", type=int, default=20)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    if not args.candidates:
        print("Template mode: provide --candidates to run secondary CE re-ranking.")
        print("Required columns: review_id, review_text, issue_id, issue_text, rank")
        return

    df = pd.read_csv(args.candidates)
    required = {"review_id", "review_text", "issue_id", "issue_text", "rank"}
    if not required.issubset(df.columns):
        raise ValueError(f"Candidate file must contain {sorted(required)}")

    ce = CrossEncoder(args.model, device=args.device)
    out_parts = []
    for review_id, group in df.groupby("review_id", sort=False):
        top = group.sort_values("rank").head(args.top_k).copy()
        pairs = list(zip(top["review_text"].astype(str), top["issue_text"].astype(str)))
        top["ce_score"] = ce.predict(pairs, show_progress_bar=False)
        top["ce_rank"] = top["ce_score"].rank(ascending=False, method="first").astype(int)
        out_parts.append(top.sort_values("ce_rank"))

    result = pd.concat(out_parts, ignore_index=True)
    result.to_csv(args.output, index=False)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

