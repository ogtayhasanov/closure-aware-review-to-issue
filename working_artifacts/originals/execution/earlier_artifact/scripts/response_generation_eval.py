"""Summarize judged response-generation outputs.

External LLM judging is intentionally disabled by default. This script expects
an already judged CSV and computes table-level status-correctness and
hallucination summaries.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgments", type=Path, help="CSV with method,status_correct,hallucinated_fix_narrative")
    parser.add_argument("--output", type=Path, default=Path("response_generation_summary.csv"))
    parser.add_argument("--enable-llm-judge", action="store_true", help="Reserved; external API judging is not run by default")
    args = parser.parse_args()

    if args.enable_llm_judge:
        raise RuntimeError("LLM judging is intentionally disabled in this lightweight artifact. Provide judged CSVs instead.")

    if not args.judgments:
        default = Path("results/generation_status_correctness.csv")
        if default.exists():
            print(pd.read_csv(default).to_string(index=False))
            return
        print("Template mode: provide --judgments to summarize judged responses.")
        return

    df = pd.read_csv(args.judgments)
    required = {"method", "status_correct", "hallucinated_fix_narrative"}
    if not required.issubset(df.columns):
        raise ValueError(f"Judgment file must contain {sorted(required)}")

    df["status_correct_bool"] = to_bool(df["status_correct"])
    df["hallucinated_fix_bool"] = to_bool(df["hallucinated_fix_narrative"])
    summary = (
        df.groupby("method")
        .agg(
            total=("method", "size"),
            status_correct_count=("status_correct_bool", "sum"),
            hallucinated_fix_count=("hallucinated_fix_bool", "sum"),
        )
        .reset_index()
    )
    summary["status_correct_percent"] = summary["status_correct_count"] / summary["total"] * 100
    summary["hallucinated_fix_percent"] = summary["hallucinated_fix_count"] / summary["total"] * 100
    summary.to_csv(args.output, index=False)
    print(summary.to_string(index=False))
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

