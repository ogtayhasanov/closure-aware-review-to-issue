#!/usr/bin/env python3
# -*- coding: utf-8 -*-

r"""
BLINDED HUMAN STATUS-CORRECTNESS AUDIT FOR FINAL-RRF REAL-REVIEW RESPONSES

Usage
-----
1) Prepare the blinded 72-response sheet:
       python human_status_audit_72.py prepare

2) Open ONLY:
       C:\Users\Ogtay\Downloads\haring_human_status_audit_72\
           blinded_status_annotation_72.csv

   Fill `human_status_correct` with TRUE or FALSE for every row.
   `human_notes` is optional.

   Do NOT open BLINDING_KEY_DO_NOT_OPEN.csv until all 72 labels are frozen.

3) Analyze after annotation:
       python human_status_audit_72.py analyze

No API calls. No model inference. No retrieval.

Design
------
- 36 final-RRF non-resolved retrieved issues.
- Two response conditions per issue: structured closure and binary state.
- 72 response rows total.
- Condition identity and pair key are removed from the annotation sheet.
- Rows are randomized with a fixed seed.
- The annotator sees the same authoritative status target used by the
  automated judge (l1_class/subtype/action_l1) plus raw tracker evidence.
- The primary human endpoint is paired status correctness, analyzed with one
  two-sided exact McNemar test after labels are frozen.
- Existing gpt-4o-mini status labels are used only for human-vs-judge agreement
  diagnostics after unblinding.
"""

from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import re
import sys

import numpy as np
import pandas as pd

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
SOURCE = (
    DOWNLOADS
    / "haring_rrf_threeway_generation_20260808"
    / "rrf_threeway_responses_and_judgments.csv"
)
OUT = DOWNLOADS / "haring_human_status_audit_72"
OUT.mkdir(parents=True, exist_ok=True)

BLINDED = OUT / "blinded_status_annotation_72.csv"
KEY = OUT / "BLINDING_KEY_DO_NOT_OPEN.csv"
RUBRIC = OUT / "ANNOTATION_RUBRIC.txt"
PROTOCOL = OUT / "human_status_audit_protocol.json"

SUMMARY = OUT / "human_primary_status_summary.json"
PAIRED = OUT / "human_primary_paired_cases_36.csv"
AGREEMENT = OUT / "human_vs_llm_judge_agreement.csv"
DISAGREEMENTS = OUT / "human_vs_llm_judge_disagreements.csv"

SEED = 20260808
NONRESOLVED = {"REJECTED", "ABANDONED", "REDIRECTED"}
CONDITIONS = {"closure_aware", "binary_state"}


def clean(x):
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()


def parse_bool(x, field):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Cannot parse {field}={x!r} as boolean")


def exact_mcnemar_p(a_only, b_only):
    d = int(a_only + b_only)
    if d == 0:
        return 1.0
    k = min(int(a_only), int(b_only))
    lower = sum(math.comb(d, i) for i in range(k + 1)) / (2 ** d)
    return min(1.0, 2.0 * lower)


def cohen_kappa_binary(a, b):
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    if len(a) == 0:
        return float("nan")
    po = float(np.mean(a == b))
    pa = float(np.mean(a))
    pb = float(np.mean(b))
    pe = pa * pb + (1 - pa) * (1 - pb)
    if abs(1 - pe) < 1e-15:
        return float("nan")
    return (po - pe) / (1 - pe)


def binom_pmf(n, k, p):
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def exact_mcnemar_reject(a_only, b_only, alpha=0.05):
    return exact_mcnemar_p(a_only, b_only) <= alpha


def power_for_delta(n, q, delta, alpha=0.05):
    """
    Same conditional-discordance sensitivity model used in the manuscript:
      q = P(10)+P(01)
      delta = |P(10)-P(01)|
    Given D discordant pairs, A-only ~ Binomial(D, (q+delta)/(2q)).
    """
    if q <= 0 or delta < 0 or delta > q:
        return 0.0
    p_dir = 0.5 if q == 0 else (q + delta) / (2 * q)
    total = 0.0
    for d in range(n + 1):
        pd = binom_pmf(n, d, q)
        if pd == 0:
            continue
        reject_given_d = 0.0
        for a_only in range(d + 1):
            b_only = d - a_only
            if exact_mcnemar_reject(a_only, b_only, alpha):
                reject_given_d += binom_pmf(d, a_only, p_dir)
        total += pd * reject_given_d
    return total


def mde_80(n, discordant, alpha=0.05, target=0.80):
    q = discordant / n
    if q <= 0:
        return None
    lo, hi = 0.0, q
    if power_for_delta(n, q, hi, alpha) < target:
        return None
    for _ in range(55):
        mid = (lo + hi) / 2
        if power_for_delta(n, q, mid, alpha) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def make_annotation_id(pair_key, condition, rank):
    raw = f"{SEED}|{pair_key}|{condition}|{rank}".encode("utf-8")
    return "HS-" + hashlib.sha256(raw).hexdigest()[:10].upper()


def prepare():
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Missing source:\n{SOURCE}\n"
            "Run this on the machine containing the completed three-way RRF CSV."
        )

    df = pd.read_csv(SOURCE, low_memory=False).copy()

    required = {
        "pair_key", "system", "app", "query_id", "review_text",
        "repository", "display_issue_id", "issue_title", "issue_body",
        "binary_state", "resolution_signal", "labels", "closed_at",
        "l1_class", "subtype", "action_l1", "response",
        "judge_status_correct",
    }
    missing = required - set(df.columns)
    if missing:
        raise AssertionError(f"Source missing columns: {sorted(missing)}")

    df["l1_class"] = df["l1_class"].astype(str).str.strip().str.upper()
    df = df[
        df["l1_class"].isin(NONRESOLVED)
        & df["system"].astype(str).isin(CONDITIONS)
    ].copy()

    if df["pair_key"].nunique() != 36:
        raise AssertionError(
            f"Expected 36 non-resolved pair keys, got {df['pair_key'].nunique()}"
        )
    if len(df) != 72:
        raise AssertionError(f"Expected 72 response rows, got {len(df)}")

    counts = df.groupby("pair_key")["system"].nunique()
    if not (counts == 2).all():
        raise AssertionError("Every pair must contain exactly two conditions.")

    # Deterministic random order independent of system names shown to annotator.
    rng = random.Random(SEED)
    rows = df.to_dict("records")
    rng.shuffle(rows)

    blinded_rows = []
    key_rows = []

    for rank, r in enumerate(rows, start=1):
        annotation_id = make_annotation_id(r["pair_key"], r["system"], rank)

        blinded_rows.append({
            "annotation_id": annotation_id,
            "app": clean(r["app"]),
            "user_review": clean(r["review_text"]),
            "retrieved_issue_tracker": clean(r["repository"]),
            "retrieved_issue_id": clean(r["display_issue_id"]),
            "retrieved_issue_title": clean(r["issue_title"]),
            "retrieved_issue_body_excerpt": clean(r["issue_body"])[:1200],
            "binary_state": clean(r["binary_state"]),
            "resolution_signal": clean(r["resolution_signal"]),
            "labels": clean(r["labels"]),
            "closed_at": clean(r["closed_at"]),
            "authoritative_l1_class": clean(r["l1_class"]),
            "authoritative_subtype": clean(r["subtype"]),
            "authoritative_action": clean(r["action_l1"]),
            "generated_response": clean(r["response"]),
            "human_status_correct": "",
            "human_notes": "",
        })

        key_rows.append({
            "annotation_id": annotation_id,
            "pair_key": clean(r["pair_key"]),
            "system": clean(r["system"]),
            "app": clean(r["app"]),
            "query_id": clean(r["query_id"]),
            "l1_class": clean(r["l1_class"]),
            "subtype": clean(r["subtype"]),
            "llm_judge_status_correct": parse_bool(
                r["judge_status_correct"], "judge_status_correct"
            ),
        })

    blinded = pd.DataFrame(blinded_rows)
    key = pd.DataFrame(key_rows)

    if blinded["annotation_id"].duplicated().any():
        raise AssertionError("Duplicate annotation IDs.")
    if set(blinded["annotation_id"]) != set(key["annotation_id"]):
        raise AssertionError("Blinding key mismatch.")

    blinded.to_csv(BLINDED, index=False)
    key.to_csv(KEY, index=False)

    rubric = """BLINDED STATUS-CORRECTNESS RUBRIC — FINAL RRF NON-RESOLVED CASES

Goal
----
Judge ONLY whether the generated response correctly communicates the
authoritative status/outcome of the retrieved issue.

You are blinded to which generation system produced each response. Do not open
BLINDING_KEY_DO_NOT_OPEN.csv until all 72 labels are complete.

Primary field
-------------
human_status_correct = TRUE or FALSE

Mark TRUE when the response communicates the authoritative L1 class/subtype/
action without contradicting it. Exact wording is not required; accurate
paraphrases count.

Mark FALSE when the response states or clearly implies the wrong status,
especially when it turns a non-resolved closure into a fix/resolution.

Outcome guidance
----------------
REJECTED:
  The issue was declined/not planned/wontfix/invalid/by-design/not-a-bug.
  A response must not claim it was fixed/resolved.

ABANDONED:
  The issue was closed without confirmed resolution, e.g. stale, needs more
  information, cannot reproduce, upstream, or another non-resolution reason.
  A response must not claim a confirmed fix. It should communicate the
  available subtype when the response makes a concrete status claim.

REDIRECTED:
  The issue was closed as a duplicate or moved/tracked elsewhere.
  A response must communicate redirection/duplication and must not claim the
  retrieved issue itself was fixed unless the supplied evidence explicitly
  supports that claim.

Ignore for the primary label
----------------------------
- Whether the retrieved issue is the correct issue for the original review.
  Retrieval relevance is evaluated separately.
- Fluency, politeness, empathy, verbosity, citation style, and general
  usefulness, unless they change the factual status claim.
- Minor omissions that do not change the stated closure status.

Use human_notes only for genuinely ambiguous cases. Do not compare paired
responses side-by-side and do not infer the hidden system identity.
"""
    RUBRIC.write_text(rubric, encoding="utf-8")

    protocol = {
        "protocol": "blinded-human-status-correctness-final-rrf-v1",
        "created_for": "36 final-RRF non-resolved retrieved issues x 2 systems",
        "n_pairs": 36,
        "n_responses": 72,
        "conditions_hidden": ["closure_aware", "binary_state"],
        "row_randomization_seed": SEED,
        "primary_metric": "human_status_correct",
        "primary_test": "two-sided exact McNemar on 36 paired human labels",
        "llm_judge_role": "secondary agreement check only",
        "raw_metadata_arm": "not part of primary 72-response human comparison",
        "instruction": (
            "Freeze all 72 human labels before opening the blinding key or "
            "running analyze."
        ),
    }
    PROTOCOL.write_text(json.dumps(protocol, indent=2), encoding="utf-8")

    print("Prepared blinded audit.")
    print("ANNOTATE ONLY:")
    print(" ", BLINDED)
    print("READ RUBRIC:")
    print(" ", RUBRIC)
    print("DO NOT OPEN UNTIL LABELS ARE FROZEN:")
    print(" ", KEY)
    print("\nRows:", len(blinded), "| pairs:", key["pair_key"].nunique())


def agreement_row(df, subset):
    h = df["human_status_correct"].astype(bool).to_numpy()
    j = df["llm_judge_status_correct"].astype(bool).to_numpy()
    return {
        "subset": subset,
        "n": int(len(df)),
        "raw_agreement": float(np.mean(h == j)),
        "cohen_kappa": float(cohen_kappa_binary(h, j)),
        "human_positive_rate": float(np.mean(h)),
        "llm_positive_rate": float(np.mean(j)),
        "human_true_llm_false": int(np.sum(h & ~j)),
        "human_false_llm_true": int(np.sum(~h & j)),
    }


def analyze():
    for p in (BLINDED, KEY):
        if not p.exists():
            raise FileNotFoundError(
                f"Missing {p}. Run `python human_status_audit_72.py prepare` first."
            )

    blind = pd.read_csv(BLINDED, low_memory=False)
    key = pd.read_csv(KEY, low_memory=False)

    if len(blind) != 72 or len(key) != 72:
        raise AssertionError("Expected 72 rows in both blinded sheet and key.")

    blank = blind["human_status_correct"].map(clean) == ""
    if blank.any():
        raise SystemExit(
            f"Annotation incomplete: {int(blank.sum())} rows still have blank "
            "human_status_correct."
        )

    blind["human_status_correct"] = blind["human_status_correct"].map(
        lambda x: parse_bool(x, "human_status_correct")
    )
    key["llm_judge_status_correct"] = key["llm_judge_status_correct"].map(
        lambda x: parse_bool(x, "llm_judge_status_correct")
    )

    merged = blind.merge(
        key,
        on=["annotation_id", "app"],
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != 72:
        raise AssertionError("Annotation/key merge did not produce 72 rows.")

    # Wide paired human table.
    base_cols = ["pair_key", "app", "query_id", "l1_class", "subtype"]
    human_wide = (
        merged.pivot(
            index=base_cols,
            columns="system",
            values="human_status_correct",
        )
        .reset_index()
    )

    if not CONDITIONS.issubset(human_wide.columns):
        raise AssertionError("Missing structured or binary condition after unblinding.")
    if len(human_wide) != 36:
        raise AssertionError(f"Expected 36 paired rows, got {len(human_wide)}")

    s = human_wide["closure_aware"].astype(bool)
    b = human_wide["binary_state"].astype(bool)

    structured_correct = int(s.sum())
    binary_correct = int(b.sum())
    structured_only = int((s & ~b).sum())
    binary_only = int((~s & b).sum())
    both_correct = int((s & b).sum())
    both_wrong = int((~s & ~b).sum())
    p = exact_mcnemar_p(structured_only, binary_only)

    discordant = structured_only + binary_only
    observed_diff = (structured_correct - binary_correct) / 36
    mde = mde_80(36, discordant)

    human_wide["structured_only"] = s & ~b
    human_wide["binary_only"] = ~s & b
    human_wide.to_csv(PAIRED, index=False)

    agreement_rows = [
        agreement_row(merged, "pooled_72"),
        agreement_row(
            merged[merged["system"] == "closure_aware"],
            "structured_36",
        ),
        agreement_row(
            merged[merged["system"] == "binary_state"],
            "binary_36",
        ),
    ]
    agreement = pd.DataFrame(agreement_rows)
    agreement.to_csv(AGREEMENT, index=False)

    disagreements = merged[
        merged["human_status_correct"]
        != merged["llm_judge_status_correct"]
    ].copy()
    disagreements.to_csv(DISAGREEMENTS, index=False)

    by_class = {}
    for cls, g in human_wide.groupby("l1_class"):
        ss = g["closure_aware"].astype(bool)
        bb = g["binary_state"].astype(bool)
        by_class[str(cls)] = {
            "n": int(len(g)),
            "structured_correct": int(ss.sum()),
            "binary_correct": int(bb.sum()),
            "structured_only": int((ss & ~bb).sum()),
            "binary_only": int((~ss & bb).sum()),
        }

    summary = {
        "primary_human_comparison": {
            "n_pairs": 36,
            "structured_correct": structured_correct,
            "structured_rate": structured_correct / 36,
            "binary_correct": binary_correct,
            "binary_rate": binary_correct / 36,
            "difference_structured_minus_binary": observed_diff,
            "structured_only": structured_only,
            "binary_only": binary_only,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "exact_mcnemar_two_sided_p": p,
            "discordant_pairs": discordant,
            "mde_80_power_two_sided_alpha_0_05": mde,
        },
        "by_l1_class": by_class,
        "human_vs_llm": agreement_rows,
        "llm_disagreement_rows": int(len(disagreements)),
    }
    SUMMARY.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 96)
    print("PRIMARY BLINDED HUMAN STATUS COMPARISON")
    print("=" * 96)
    print(f"Structured: {structured_correct}/36 ({structured_correct/36:.1%})")
    print(f"Binary:     {binary_correct}/36 ({binary_correct/36:.1%})")
    print(
        f"Discordants: structured-only={structured_only}, "
        f"binary-only={binary_only}"
    )
    print(f"Exact two-sided McNemar p = {p:.10g}")
    if mde is not None:
        print(f"80%-power MDE at observed discordance = {mde:.1%}")
    else:
        print("80%-power MDE: not estimable at this discordance level")

    print("\nBY CLASS")
    for cls, d in by_class.items():
        print(
            f"{cls:10s} n={d['n']:2d} | structured "
            f"{d['structured_correct']}/{d['n']} | binary "
            f"{d['binary_correct']}/{d['n']} | "
            f"S-only={d['structured_only']} B-only={d['binary_only']}"
        )

    print("\nHUMAN vs EXISTING LLM JUDGE")
    print(agreement.to_string(index=False))

    print("\nSaved:")
    print(" ", SUMMARY)
    print(" ", PAIRED)
    print(" ", AGREEMENT)
    print(" ", DISAGREEMENTS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "analyze"])
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    else:
        analyze()


if __name__ == "__main__":
    main()
