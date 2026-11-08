"""Template for bottom-15-percent synthetic-pair filtering."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd
import yaml


def filter_bottom15(scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"pair_id", "application", "quality_score"}
    if not required.issubset(scores.columns):
        raise ValueError(f"Input must contain {sorted(required)}")
    removed_parts = []
    kept_parts = []
    for app, group in scores.groupby("application", sort=False):
        group = group.sort_values(["quality_score", "pair_id"], ascending=[True, True])
        remove_n = math.ceil(len(group) * 0.15)
        removed_parts.append(group.head(remove_n))
        kept_parts.append(group.iloc[remove_n:])
    return pd.concat(kept_parts, ignore_index=True), pd.concat(removed_parts, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/filtering_config.yaml"))
    parser.add_argument("--scores", type=Path, help="CSV with pair_id,application,quality_score")
    parser.add_argument("--kept-output", type=Path, default=Path("filtered_pairs.csv"))
    parser.add_argument("--removed-output", type=Path, default=Path("removed_pairs.csv"))
    args = parser.parse_args()

    if args.config.exists():
        print(yaml.safe_load(args.config.read_text()))

    if not args.scores:
        print("Template mode: provide --scores to filter local synthetic-pair quality scores.")
        return

    scores = pd.read_csv(args.scores)
    kept, removed = filter_bottom15(scores)
    kept.to_csv(args.kept_output, index=False)
    removed.to_csv(args.removed_output, index=False)
    print(f"Kept {len(kept)} pairs; removed {len(removed)} pairs")


if __name__ == "__main__":
    main()

