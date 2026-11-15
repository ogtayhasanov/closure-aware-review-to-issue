"""Validate and print TOSEM table-level metric CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


METRIC_COLUMNS = ["R@1", "R@5", "R@10", "MRR", "NDCG@10"]


def validate_metrics(df: pd.DataFrame) -> None:
    missing = [c for c in METRIC_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing metric columns: {missing}")
    for col in METRIC_COLUMNS:
        bad = df[~df[col].between(0, 1, inclusive="both")]
        if not bad.empty:
            raise ValueError(f"Column {col} contains values outside [0, 1]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="CSV result table to validate")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    validate_metrics(df)
    print(df.to_string(index=False))
    print(f"\nValidated {len(df)} rows from {args.input}")


if __name__ == "__main__":
    main()

