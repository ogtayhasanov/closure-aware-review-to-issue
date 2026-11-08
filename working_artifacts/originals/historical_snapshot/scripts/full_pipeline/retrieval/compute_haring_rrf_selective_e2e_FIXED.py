#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ZERO-COMPUTE SELECTIVE END-TO-END INTERSECTION

Joins:
  1) the completed RRF closure-aware per-case E2E results, and
  2) the completed RRF confidence/abstention per-query output.

No model inference. No retrieval. No API calls.

Reports the final architecture exactly as deployed in the paper:
  RRF -> corroboration/abstain -> closure-aware generation

Key metric:
  benchmark-gated strict success among ACCEPTED queries

Also reports how many of the original 14/82 strict successes are retained.
"""

from pathlib import Path
import json
import math
import zipfile
import subprocess

import numpy as np
import pandas as pd

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")

E2E_CANDIDATES = [
    DOWNLOADS / "haring_rrf_e2e_generation_20260808" / "rrf_closure_aware_per_case_e2e.csv",
    DOWNLOADS / "haring_rrf_e2e_generation_20260808" / "rrf_closure_aware_responses_and_judgments.csv",
]

ABSTENTION_DIR_CANDIDATES = [
    DOWNLOADS / "haring_rrf_abstention",
    DOWNLOADS / "haring_rrf_abstention_results",
]

ABSTENTION_ZIP_CANDIDATES = [
    DOWNLOADS / "haring_rrf_abstention_results.zip",
    DOWNLOADS / "haring_rrf_abstention" / "haring_rrf_abstention_results.zip",
]

OUT = DOWNLOADS / "haring_rrf_selective_e2e"
OUT.mkdir(parents=True, exist_ok=True)

OUT_CSV = OUT / "selective_strict_e2e_curve.csv"
JOIN_CSV = OUT / "selective_strict_e2e_per_query.csv"
SUMMARY_JSON = OUT / "selective_strict_e2e_summary.json"

TARGET_COVERAGES = [1.00, 0.75, 0.50, 0.25]
SCORE_COL = "base_ranker_corroboration_rr"


def clean(x):
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()


def norm_id(x):
    s = clean(x)
    if s.endswith(".0"):
        try:
            return str(int(float(s)))
        except Exception:
            pass
    return s


def strict_bool(x, field):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"{field} cannot be parsed as bool: {x!r}")


def find_e2e():
    for p in E2E_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Could not find completed RRF E2E CSV. Expected one of:\n"
        + "\n".join(map(str, E2E_CANDIDATES))
    )


def _read_abstention_if_local():
    # Unzipped folder first.
    for d in ABSTENTION_DIR_CANDIDATES:
        p = d / "rrf_confidence_per_query_82.csv"
        if p.exists():
            return pd.read_csv(p, low_memory=False), str(p)

    # Then inspect downloaded zip directly.
    for zpath in ABSTENTION_ZIP_CANDIDATES:
        if not zpath.exists():
            continue
        with zipfile.ZipFile(zpath, "r") as z:
            matches = [
                name for name in z.namelist()
                if name.endswith("rrf_confidence_per_query_82.csv")
            ]
            if len(matches) == 1:
                with z.open(matches[0]) as f:
                    return pd.read_csv(f, low_memory=False), f"{zpath}::{matches[0]}"
            if len(matches) > 1:
                raise RuntimeError(
                    f"Multiple per-query confidence files in {zpath}: {matches}"
                )
    return None


def load_abstention():
    local = _read_abstention_if_local()
    if local is not None:
        return local

    # The confidence experiment saved the archive on Modal, not necessarily
    # in Downloads. Fetch the exact frozen archive automatically.
    target = DOWNLOADS / "haring_rrf_abstention_results.zip"
    remote = "haring_rrf_abstention/haring_rrf_abstention_results.zip"

    print(
        "Local abstention output not found. Fetching the completed frozen "
        "archive from Modal volume 'splade-data'..."
    )

    commands = [
        # This is the exact command emitted by modal_haring_rrf_abstention.py.
        [
            "modal", "volume", "get", "-e", "main",
            "splade-data", remote, str(target),
        ],
        # Compatibility fallback for Modal CLI versions where -e is not needed.
        [
            "modal", "volume", "get",
            "splade-data", remote, str(target),
        ],
    ]

    errors = []
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            errors.append(f"{cmd}: {exc}")
            break

        if proc.returncode == 0 and target.exists():
            print(f"Downloaded: {target}")
            local = _read_abstention_if_local()
            if local is not None:
                return local

        errors.append(
            "COMMAND: " + " ".join(cmd)
            + "\nSTDOUT:\n" + (proc.stdout or "")
            + "\nSTDERR:\n" + (proc.stderr or "")
        )

    raise FileNotFoundError(
        "The selective-E2E calculation itself needs no new compute, but the "
        "completed confidence CSV is still on the Modal volume and could not "
        "be downloaded automatically.\n\n"
        "Run this once in PowerShell:\n"
        "modal volume get -e main splade-data "
        "haring_rrf_abstention/haring_rrf_abstention_results.zip "
        "C:\\Users\\Ogtay\\Downloads\\haring_rrf_abstention_results.zip\n\n"
        "Then rerun this script.\n\n"
        + "\n\n".join(errors)
    )


e2e_path = find_e2e()
e2e = pd.read_csv(e2e_path, low_memory=False).copy()
conf, conf_source = load_abstention()

# The completed RRF E2E file should be one closure-aware row per query.
if "system" in e2e.columns:
    e2e = e2e[e2e["system"].astype(str) == "closure_aware"].copy()

if len(e2e) != 82:
    raise AssertionError(f"Expected 82 RRF closure-aware E2E rows, got {len(e2e)}")
if len(conf) != 82:
    raise AssertionError(f"Expected 82 confidence rows, got {len(conf)}")

for df in (e2e, conf):
    if "app" not in df.columns or "query_id" not in df.columns:
        raise AssertionError("Both files must contain app and query_id")
    df["app"] = df["app"].map(clean)
    df["query_id"] = df["query_id"].map(norm_id)

if SCORE_COL not in conf.columns:
    raise AssertionError(
        f"Confidence file missing primary score column {SCORE_COL!r}; "
        f"available={list(conf.columns)}"
    )

# Build strict success if not already stored.
if "known_positive_gated_strict_success" not in e2e.columns:
    needed = {
        "known_positive_hit_at_1",
        "judge_status_correct",
        "judge_hallucination",
        "judge_relevant_to_review",
    }
    missing = needed - set(e2e.columns)
    if missing:
        raise AssertionError(f"E2E file missing strict-success inputs: {sorted(missing)}")

    for col in needed:
        e2e[col] = e2e[col].map(lambda x, c=col: strict_bool(x, c))

    e2e["known_positive_gated_strict_success"] = (
        e2e["known_positive_hit_at_1"]
        & e2e["judge_status_correct"]
        & ~e2e["judge_hallucination"]
        & e2e["judge_relevant_to_review"]
    )
else:
    e2e["known_positive_gated_strict_success"] = e2e[
        "known_positive_gated_strict_success"
    ].map(lambda x: strict_bool(x, "known_positive_gated_strict_success"))

# Confidence file's benchmark hit is useful for consistency.
if "benchmark_confirmed_hit1" in conf.columns:
    conf["benchmark_confirmed_hit1"] = conf["benchmark_confirmed_hit1"].map(
        lambda x: strict_bool(x, "benchmark_confirmed_hit1")
    )

join_cols = ["app", "query_id", SCORE_COL]
for optional in [
    "benchmark_confirmed_hit1",
    "rrf_top1_issue_id",
    "rrf_top1_issue_title",
]:
    if optional in conf.columns:
        join_cols.append(optional)

merged = e2e.merge(
    conf[join_cols],
    on=["app", "query_id"],
    how="inner",
    validate="one_to_one",
)

if len(merged) != 82:
    missing_left = set(zip(e2e["app"], e2e["query_id"])) - set(
        zip(merged["app"], merged["query_id"])
    )
    missing_right = set(zip(conf["app"], conf["query_id"])) - set(
        zip(merged["app"], merged["query_id"])
    )
    raise AssertionError(
        f"Join produced {len(merged)}/82 rows. "
        f"Missing from confidence={list(missing_left)[:5]}, "
        f"missing from E2E={list(missing_right)[:5]}"
    )

total_strict = int(merged["known_positive_gated_strict_success"].sum())
if total_strict != 14:
    raise AssertionError(
        f"Expected completed RRF strict success count 14/82, got {total_strict}/82"
    )

if "benchmark_confirmed_hit1" in merged.columns:
    total_confirmed = int(merged["benchmark_confirmed_hit1"].sum())
    if total_confirmed != 16:
        raise AssertionError(f"Expected 16 benchmark-confirmed RRF top1 hits, got {total_confirmed}")

scores = merged[SCORE_COL].astype(float).to_numpy()
if not np.isfinite(scores).all():
    raise AssertionError("Non-finite confidence scores")

sorted_scores = np.sort(scores)[::-1]
n = len(merged)

rows = []
for target in TARGET_COVERAGES:
    target_n = max(
        1,
        min(n, int(math.floor(target * n + 0.5))),
    )
    threshold = float(sorted_scores[target_n - 1])
    accepted_mask = merged[SCORE_COL].astype(float) >= threshold

    accepted = merged.loc[accepted_mask].copy()
    abstained = merged.loc[~accepted_mask].copy()

    strict_acc = int(accepted["known_positive_gated_strict_success"].sum())
    strict_abs = int(abstained["known_positive_gated_strict_success"].sum())

    row = {
        "target_coverage": float(target),
        "threshold_inclusive": threshold,
        "accepted_queries": int(len(accepted)),
        "realized_coverage": float(len(accepted) / n),
        "strict_successes_accepted": strict_acc,
        "benchmark_gated_strict_success_among_accepted": float(
            strict_acc / len(accepted)
        ),
        "strict_successes_retained_fraction": float(strict_acc / total_strict),
        "strict_successes_abstained": strict_abs,
    }

    if "benchmark_confirmed_hit1" in accepted.columns:
        confirmed_acc = int(accepted["benchmark_confirmed_hit1"].sum())
        row.update({
            "confirmed_top1_accepted": confirmed_acc,
            "confirmed_hit1_among_accepted": float(confirmed_acc / len(accepted)),
        })

    rows.append(row)

curve = pd.DataFrame(rows)

# Hard reproduction of the already reported abstention curve.
expected = {
    1.00: (82, 16),
    0.75: (62, 15),
    0.50: (41, 13),
    0.25: (21, 8),
}
if "benchmark_confirmed_hit1" in curve.columns:
    for _, row in curve.iterrows():
        key = float(row["target_coverage"])
        exp_n, exp_hits = expected[key]
        if int(row["accepted_queries"]) != exp_n:
            raise AssertionError(
                f"Coverage reproduction failed at {key}: "
                f"accepted={row['accepted_queries']} expected={exp_n}"
            )
        if int(row["confirmed_top1_accepted"]) != exp_hits:
            raise AssertionError(
                f"Hit retention reproduction failed at {key}: "
                f"hits={row['confirmed_top1_accepted']} expected={exp_hits}"
            )

curve.to_csv(OUT_CSV, index=False)
merged.to_csv(JOIN_CSV, index=False)

summary = {
    "e2e_source": str(e2e_path),
    "confidence_source": conf_source,
    "n": 82,
    "full_coverage_strict_successes": total_strict,
    "metric_name": "benchmark-gated strict success among accepted queries",
    "interpretation": (
        "This is a conservative benchmark-gated selective end-to-end diagnostic, "
        "not full semantic response accuracy, because Häring relevance judgments "
        "are pool-incomplete."
    ),
    "curve": curve.to_dict("records"),
}
SUMMARY_JSON.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
)

print("\n" + "=" * 108)
print("RRF -> ABSTENTION -> CLOSURE-AWARE SELECTIVE END-TO-END")
print("=" * 108)
print(curve.to_string(index=False))
print("\nSaved:")
print(" ", OUT_CSV)
print(" ", JOIN_CSV)
print(" ", SUMMARY_JSON)
