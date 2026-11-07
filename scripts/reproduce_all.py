#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from closure_artifact.analysis import reproduce_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce the frozen artifact results.")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "generated")
    args = parser.parse_args()
    summary = reproduce_all(ROOT, args.output)
    human = summary["human_primary"]
    generation = summary["generation_descriptive"]
    print("PASS human primary:", human["by_system"])
    print("PASS exact McNemar p:", f"{human['exact_two_sided_mcnemar_p']:.12g}")
    print("PASS generation rows:", generation["n_system_rows"])
    print("PASS follow-up generation rows:", summary["generation_followup"]["generation_rows"])
    print("PASS external retrieval queries:", summary["external_retrieval"]["queries"])
    print(f"Wrote {args.output / 'reproduction_summary.json'}")


if __name__ == "__main__":
    main()
