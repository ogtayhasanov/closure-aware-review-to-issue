#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKING_ARTIFACTS = ROOT / "working_artifacts"
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv"}
FORBIDDEN_SUFFIXES = {".xlsx", ".xls", ".zip", ".pdf", ".tex", ".bib", ".jsonl"}
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
    "Google auth key": re.compile(r"\bAQ\.[0-9A-Za-z_-]{30,}\b"),
    "private key": re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----"),
}
FOLLOWUP_SCHEMAS = {
    "followup_cases_162.csv": (
        "case_id dataset project tracker probe_group audit35 routing_cohort "
        "tracker_supported_status status_evidence_source analysis_exclusion "
        "switch_state closer_type linked_fix switch"
    ),
    "followup_judgments_1780.csv": (
        "case_id model arm judge_declined lexical_declined judge_fix_claim lexical_fix_claim "
        "judge_inactivity lexical_inactivity judge_states_outcome lexical_states_outcome "
        "judge_asks_details lexical_asks_details judge_says_duplicate lexical_says_duplicate"
    ),
    "followup_human_check_24.csv": "case_id model arm human_states_outcome",
    "provenance_prevalence_7.csv": (
        "project closed_issues paper_table1_closed_issues paper_table1_nonresolved_pct "
        "nonresolved_v1_count nonresolved_v2_count issues_with_any_rejection_label "
        "rejection_label_instances rejection_labels_added_by_bot rejection_label_adder_unknown "
        "rejection_labeled_issues_closed_by_bot_no_fix all_issues_closed_by_bot_no_fix "
        "script_v1_rejected_by_label script_v1_reject_label_added_by_bot "
        "script_v1_reject_closed_by_bot_no_fix"
    ),
    "retrieval_query_scores_82.csv": (
        "query_id project bm25_rank bge_zs_rank rrf_rank corroboration_rr "
        "rrf_relative_margin mean_top10_jaccard strict_success"
    ),
    "retrieval_thresholds_12.csv": "signal target_coverage threshold_inclusive",
    "synthetic_bge_ranks_794.csv": "query_id project bge_zs_rank bge_ft_rank",
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


def verify_working_artifacts(paths: list[Path]) -> list[str]:
    if not WORKING_ARTIFACTS.exists():
        return []
    manifest_path = WORKING_ARTIFACTS / "SOURCE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"Could not read working-artifact checksum inventory: {error}"]
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, dict) or not entries:
        return ["Missing working-artifact checksum inventory"]

    observed = {path.relative_to(WORKING_ARTIFACTS).as_posix(): path for path in paths}
    if observed.keys() != entries.keys() | {"README.md", "SOURCE_MANIFEST.json"}:
        return ["Working artifacts differ from their checksum inventory"]
    failures = []
    for name, spec in entries.items():
        path = observed[name]
        if path.is_symlink() or not path.resolve().is_relative_to(WORKING_ARTIFACTS):
            failures.append(f"Unsafe working-artifact path: {name}")
            continue
        data = path.read_bytes()
        if (
            not isinstance(spec, dict)
            or len(data) != spec.get("bytes")
            or hashlib.sha256(data).hexdigest() != spec.get("sha256")
        ):
            failures.append(f"Working-artifact checksum mismatch: {name}")
    if not failures:
        print(f"PASS SHA-256 integrity for {len(entries)} working-artifact files")
    return failures


def main() -> int:
    paths = files()
    working_files = [path for path in paths if path.is_relative_to(WORKING_ARTIFACTS)]
    failures = verify_working_artifacts(working_files)
    all_files = [path for path in paths if not path.is_relative_to(WORKING_ARTIFACTS)]
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
            if re.search(r"[A-Za-z]:[/\\]{1,2}Users[/\\]{1,2}", text, re.IGNORECASE):
                failures.append(f"Local Windows path in {relative}")

    expected = {
        "data/derived/human_status_72.csv": 72,
        "data/derived/taxonomy_predictions_120.csv": 120,
        "data/derived/generation_judgments_246.csv": 246,
        "data/derived/action_routing_46.csv": 46,
        "data/derived/splade_checkpoint_audit_5seeds.csv": 5,
        "data/derived/reported_study_scale.csv": 5,
        **{
            f"data/derived/{name}": int(name.removesuffix(".csv").rsplit("_", 1)[1])
            for name in FOLLOWUP_SCHEMAS
        },
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
        schema = FOLLOWUP_SCHEMAS.get(path.name)
        if schema and headers != set(schema.split()):
            failures.append(f"{relative}: unexpected columns in the text-free release schema")
        for row_number, row in enumerate(rows, start=2):
            for field, value in row.items():
                if len(value or "") > 256:
                    failures.append(f"{relative}:{row_number} unexpectedly long value in {field}")
            if schema and "case_id" in row and not re.fullmatch(r"F\d{3}", row["case_id"] or ""):
                failures.append(f"{relative}:{row_number} expected an opaque follow-up case ID")
            if schema and "query_id" in row and not re.fullmatch(r"[QS]\d{3}", row["query_id"] or ""):
                failures.append(f"{relative}:{row_number} expected an opaque query ID")
            for field in row:
                if schema and field and field.startswith(("judge_", "lexical_", "human_")):
                    if row[field] not in {"", "0", "1"}:
                        failures.append(f"{relative}:{row_number} expected a binary or unavailable label in {field}")

    unexpected_data = [
        path.relative_to(ROOT).as_posix()
        for path in all_files
        if "data" in path.relative_to(ROOT).parts
        and path.is_file()
        and path.relative_to(ROOT).as_posix() not in expected
        and path != ROOT / "data" / "README.md"
    ]
    if unexpected_data:
        failures.append(f"Data outside the public allowlist: {unexpected_data}")

    for failure in failures:
        print("FAIL", failure)
    if failures:
        return 1
    print("PASS public-data boundary, row counts, size limits, and secret scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
