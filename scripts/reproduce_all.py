#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from closure_artifact.analysis import reproduce_all


def main() -> None:
    summary = reproduce_all(ROOT)
    human = summary["human_primary"]
    taxonomy = summary["taxonomy_validation"]
    generation = summary["generation_descriptive"]
    print("PASS human primary:", human["by_system"])
    print("PASS exact McNemar p:", f"{human['exact_two_sided_mcnemar_p']:.12g}")
    print(
        "PASS taxonomy:",
        f"{taxonomy['correct']}/{taxonomy['n']}",
        f"macro-F1={taxonomy['macro_f1']:.4f}",
        f"kappa={taxonomy['cohen_kappa']:.4f}",
    )
    print("PASS generation rows:", generation["n_system_rows"])
    print("Wrote results/generated/reproduction_summary.json")


if __name__ == "__main__":
    main()
