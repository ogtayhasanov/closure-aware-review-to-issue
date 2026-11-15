#!/usr/bin/env python3
"""Check manuscript-reported arithmetic and compare the later seven-project scan.

The historical counts are transcribed from the manuscript, not independently
reconstructed from the original tracker records.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    historical = read_csv(ROOT / "working_artifacts/curated/manuscript_figure1_prevalence_9.csv")
    scan = read_csv(ROOT / "data/derived/provenance_prevalence_7.csv")
    if len(historical) != 9 or len({r["project"] for r in historical}) != 9:
        raise ValueError("Expected nine distinct manuscript project counts")
    numer = sum(int(r["nonresolved_count"]) for r in historical)
    denom = sum(int(r["closed_issues"]) for r in historical)
    print(f"Manuscript-reported counts: {numer:,}/{denom:,} = {100 * numer / denom:.1f}%")
    print("The underlying historical issue-level records are not provided.")
    print("Later seven-project scan versus manuscript (percentage points):")
    original = {r["project"]: r for r in historical}
    for row in scan:
        old = original[row["project"]]
        old_rate = 100 * int(old["nonresolved_count"]) / int(old["closed_issues"])
        new_rate = 100 * int(row["nonresolved_v1_count"]) / int(row["closed_issues"])
        print(f"  {row['project']}: {new_rate:.1f}% vs {old_rate:.1f}% ({new_rate - old_rate:+.1f} pp)")
    print("The later scan has different denominators and is not an exact historical replication.")


if __name__ == "__main__":
    main()
