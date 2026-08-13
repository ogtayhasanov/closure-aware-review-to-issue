#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv"}
FORBIDDEN_SUFFIXES = {".xlsx", ".xls", ".zip", ".pdf", ".tex", ".bib"}
FORBIDDEN_HEADERS = {
    "review_text", "user review", "issue_title", "issue_body", "issue body",
    "title", "body", "response", "generated response", "raw-metadata response",
    "issue / tracker evidence", "closure_evidence", "judge_reasoning",
}
SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub classic token": re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "private key": re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----"),
}


def files() -> list[Path]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS)
        found.extend(Path(directory) / name for name in sorted(filenames))
    return sorted(found)


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    failures: list[str] = []
    all_files = files()
    for path in all_files:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"Prohibited binary/raw artifact file: {relative}")
        if path.stat().st_size > 2 * 1024 * 1024:
            failures.append(f"Unexpected file larger than 2 MiB: {relative}")
        if path.suffix.lower() in {".py", ".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".cff", ".toml"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    failures.append(f"Potential {label} in {relative}")
            source_review_prefix = "gp:" + "AO"
            if source_review_prefix in text:
                failures.append(f"Potential source app-review identifier in {relative}")
            if re.search(r"[A-Za-z]:\\\\Users\\\\", text):
                failures.append(f"Local Windows path in {relative}")

    expected = {
        "data/derived/human_status_72.csv": 72,
        "data/derived/taxonomy_predictions_120.csv": 120,
        "data/derived/generation_judgments_246.csv": 246,
        "data/derived/action_routing_46.csv": 46,
        "data/derived/splade_checkpoint_audit_5seeds.csv": 5,
        "data/derived/reported_study_scale.csv": 5,
    }
    for relative, count in expected.items():
        path = ROOT / relative
        if not path.exists():
            failures.append(f"Missing public evidence file: {relative}")
            continue
        rows = csv_rows(path)
        if len(rows) != count:
            failures.append(f"{relative}: expected {count} rows, found {len(rows)}")
        headers = {header.strip().lower() for header in (rows[0].keys() if rows else [])}
        exposed = sorted(headers & FORBIDDEN_HEADERS)
        if exposed:
            failures.append(f"{relative}: prohibited raw-text columns {exposed}")
        for row_number, row in enumerate(rows, start=2):
            for field, value in row.items():
                if len(value or "") > 256:
                    failures.append(f"{relative}:{row_number} unexpectedly long value in {field}")

    unexpected_data = [
        path.relative_to(ROOT).as_posix()
        for path in all_files
        if "data" in path.relative_to(ROOT).parts
        and path.is_file()
        and path.parent != ROOT / "data" / "derived"
        and path != ROOT / "data" / "README.md"
    ]
    if unexpected_data:
        failures.append(f"Data found outside data/derived: {unexpected_data}")

    for failure in failures:
        print("FAIL", failure)
    if failures:
        return 1
    print("PASS public-data boundary, row counts, size limits, and secret scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
