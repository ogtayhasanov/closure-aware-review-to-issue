"""Deterministic closure-reason mapping from issue metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml


def normalize_labels(value: object) -> set[str]:
    if pd.isna(value):
        return set()
    text = str(value).lower().replace(";", ",")
    return {part.strip() for part in text.split(",") if part.strip()}


def map_closure_reason(state: str, state_reason: str, labels: set[str], rules: dict) -> str:
    state = (state or "").lower()
    state_reason = (state_reason or "").lower()
    if state != "closed":
        return "OPEN"
    if labels & set(rules.get("redirected", [])):
        return "REDIRECTED"
    if labels & set(rules.get("rejected", [])):
        return "REJECTED"
    if labels & set(rules.get("abandoned", [])):
        return "ABANDONED"
    if state_reason in set(rules.get("resolved_state_reasons", [])):
        return "RESOLVED"
    return "REJECTED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/closure_reason_rules.yaml"))
    parser.add_argument("--issues", type=Path, help="CSV with state,state_reason,labels")
    parser.add_argument("--output", type=Path, default=Path("closure_reason_mapped.csv"))
    args = parser.parse_args()

    rules = yaml.safe_load(args.config.read_text())
    if not args.issues:
        print("Template mode: provide --issues to map local issue metadata.")
        return

    df = pd.read_csv(args.issues)
    for col in ["state", "state_reason", "labels"]:
        if col not in df.columns:
            df[col] = ""
    df["closure_class"] = [
        map_closure_reason(row["state"], row["state_reason"], normalize_labels(row["labels"]), rules)
        for _, row in df.iterrows()
    ]
    df.to_csv(args.output, index=False)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

