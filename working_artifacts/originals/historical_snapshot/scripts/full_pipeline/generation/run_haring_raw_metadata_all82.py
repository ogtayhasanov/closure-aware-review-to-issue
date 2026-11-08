# ============================================================
# EXTEND HÄRING RAW-METADATA ABLATION FROM 45 TO ALL 82 CASES
# ============================================================
#
# Reuses:
#   - completed original 82-case closure-aware + binary-state run
#   - completed 45-case raw-metadata ablation on non-resolved closed issues
#
# New API work:
#   ONLY the remaining 37 raw-metadata generations + 37 judgments.
#
# Final comparison:
#   closure_aware vs raw_metadata vs binary_state on ALL 82 cases
#
# IMPORTANT:
#   The all-82 raw-vs-closure significance test is POST-HOC / EXPLORATORY,
#   because it was motivated after observing p=.065 on the 45-case subset.
#
# Inputs:
#   C:\Users\Ogtay\Downloads\haring_e2e_generation_20260808\
#       responses_and_judgments.csv
#
#   C:\Users\Ogtay\Downloads\haring_e2e_raw_metadata_ablation\
#       raw_metadata_responses_and_judgments.csv
#
# Outputs:
#   C:\Users\Ogtay\Downloads\haring_e2e_raw_metadata_all82\
#       raw_metadata_remaining37_progress.jsonl
#       raw_metadata_all82.csv
#       three_arm_all82.csv
#       three_arm_all82_metrics.csv
#       paired_raw_vs_closure_all82.csv
#       paired_raw_vs_binary_all82.csv
#       continuous_paired_tests_all82.csv
#       protocol.json
#       summary.json
#
# Safe/resumable.
# ============================================================

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from datetime import datetime, timezone
import getpass
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing openai package. Install with:\n"
        "  python -m pip install -U openai pandas numpy scipy\n"
    ) from exc

try:
    from scipy.stats import wilcoxon
except ImportError as exc:
    raise SystemExit(
        "Missing scipy. Install with:\n"
        "  python -m pip install -U scipy\n"
    ) from exc


# ------------------------------------------------------------------
# Frozen protocol
# ------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o-mini"
TEMPERATURE = 0
API_WORKERS = 3
API_MAX_ATTEMPTS = 5

RAW_GEN_PROMPT_VERSION = "haring-raw-metadata-ablation-generation-v1-2026-08-08"
RAW_JUDGE_PROMPT_VERSION = "haring-raw-metadata-ablation-judge-v1-2026-08-08"

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")

FULL82_SOURCE = (
    DOWNLOADS
    / "haring_e2e_generation_20260808"
    / "responses_and_judgments.csv"
)

RAW45_SOURCE = (
    DOWNLOADS
    / "haring_e2e_raw_metadata_ablation"
    / "raw_metadata_responses_and_judgments.csv"
)

OUT = DOWNLOADS / "haring_e2e_raw_metadata_all82"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS_PATH = OUT / "raw_metadata_remaining37_progress.jsonl"
RAW82_PATH = OUT / "raw_metadata_all82.csv"
THREE82_PATH = OUT / "three_arm_all82.csv"
METRICS_PATH = OUT / "three_arm_all82_metrics.csv"
PAIR_RC_PATH = OUT / "paired_raw_vs_closure_all82.csv"
PAIR_RB_PATH = OUT / "paired_raw_vs_binary_all82.csv"
CONT_PATH = OUT / "continuous_paired_tests_all82.csv"
PROTOCOL_PATH = OUT / "protocol.json"
SUMMARY_PATH = OUT / "summary.json"

thread_local = local()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def clean(x):
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def strict_bool(x, field):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "false"}:
        return s == "true"
    raise ValueError(f"{field} is not boolean: {x!r}")


def strict_score(x, field):
    v = float(x)
    if not math.isfinite(v) or not (0.0 <= v <= 1.0):
        raise ValueError(f"{field} outside [0,1]: {x!r}")
    return v


# ------------------------------------------------------------------
# SAME raw-metadata arm as the completed 45-case experiment
# ------------------------------------------------------------------

RAW_METADATA_SYSTEM = """You are a developer-support assistant.
Write a concise response to a real user review using only the retrieved software
issue evidence supplied below.

You are given raw tracker metadata, but no normalized closure taxonomy and no
action-specific policy template. Infer what can safely be said from the raw
metadata itself.

Rules:
- Use only facts present in the supplied metadata.
- Cite the retrieved issue number, and include its URL when one is supplied.
- Never invent versions, releases, dates, commits, file paths, technical causes,
  fixes, canonical issue numbers, or developer promises.
- Do not assume that every closed issue was fixed.
- Be empathetic and factual.
- Keep the response below 100 words.
"""


JUDGE_SYSTEM = """You are evaluating a generated app-support response.

The authoritative outcome is defined by l1_class, subtype, and action_l1.
Tracker-specific resolution signals and labels are supporting metadata and are
not authoritative when the normalized taxonomy encodes a more specific outcome.

Taxonomy:
- OPEN: the issue remains open.
- RESOLVED: fixed/resolved/completed.
- REJECTED: not planned, wontfix, invalid, by-design, or not-a-bug.
- ABANDONED: stale, inactive, needs information, cannot reproduce, upstream, or
  closed without confirmed resolution.
- REDIRECTED: duplicate or tracked elsewhere.

Evaluate:
- faithfulness: 0.0-1.0, factual support from the retrieved metadata.
- hallucination: true only for unsupported versions, dates, paths, causes,
  canonical issue numbers, fixes, or similarly specific factual claims.
- status_correct: whether the response communicates l1_class/subtype/action_l1.
- specificity: 0.0-1.0, whether it uses the specific retrieved issue rather than
  only generic advice.
- usefulness: 0.0-1.0.
- empathy: 0.0-1.0.
- actionability: 0.0-1.0.
- relevant_to_review: whether the response addresses the complaint as written.

Return only one JSON object with exactly these fields:
{"faithfulness": 0.0, "hallucination": false, "status_correct": true,
"specificity": 0.0, "usefulness": 0.0, "empathy": 0.0,
"actionability": 0.0, "relevant_to_review": true,
"reasoning": "brief explanation"}
"""


def raw_user_prompt(row):
    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

RETRIEVED ISSUE:
- Tracker: {clean(row.get('repository'))}
- Issue #{clean(row.get('display_issue_id'))}: {clean(row.get('issue_title'))}
- Binary state: {clean(row.get('binary_state'))}
- URL: {clean(row.get('issue_url')) or 'not supplied'}
- Issue body excerpt: {clean(row.get('issue_body'))[:1200]}

RAW TRACKER METADATA:
- resolution/state_reason signal: {clean(row.get('resolution_signal')) or 'none'}
- labels: {clean(row.get('labels')) or 'none'}
- closed_at: {clean(row.get('closed_at')) or 'not supplied'}

Write the response using the raw tracker evidence only."""


def judge_user_prompt(row, response_text):
    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

GENERATED SYSTEM:
raw_metadata

GENERATED RESPONSE:
{response_text}

AUTHORITATIVE RETRIEVED-ISSUE METADATA:
- Tracker: {clean(row.get('repository'))}
- Issue #{clean(row.get('display_issue_id'))}: {clean(row.get('issue_title'))}
- State: {clean(row.get('binary_state'))}
- Resolution signal: {clean(row.get('resolution_signal')) or 'none'}
- Labels: {clean(row.get('labels')) or 'none'}
- Closed date: {clean(row.get('closed_at')) or 'not supplied'}
- URL: {clean(row.get('issue_url')) or 'not supplied'}
- l1_class: {clean(row.get('l1_class'))}
- subtype: {clean(row.get('subtype'))}
- action_l1: {clean(row.get('action_l1'))}
- Issue body excerpt: {clean(row.get('issue_body'))[:1200]}

Judge the response against the retrieved issue. Do not decide whether retrieval
selected a benchmark-known positive issue; benchmark Hit@1 is computed
separately from the original Häring judgments."""


# ------------------------------------------------------------------
# OpenAI
# ------------------------------------------------------------------

def get_client(api_key):
    if not hasattr(thread_local, "client"):
        thread_local.client = OpenAI(
            api_key=api_key,
            timeout=60,
            max_retries=0,
        )
    return thread_local.client


def call_openai(api_key, system_prompt, user_prompt, max_tokens, json_mode=False):
    last_error = None

    for attempt in range(API_MAX_ATTEMPTS):
        try:
            kwargs = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": TEMPERATURE,
            }

            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            resp = get_client(api_key).chat.completions.create(**kwargs)
            text = clean(resp.choices[0].message.content)

            if not text:
                raise RuntimeError("Empty API response")

            usage = {}
            if getattr(resp, "usage", None) is not None and hasattr(resp.usage, "model_dump"):
                usage = resp.usage.model_dump()

            return {
                "content": text,
                "model_returned": clean(getattr(resp, "model", OPENAI_MODEL)),
                "usage": usage,
            }

        except Exception as exc:
            last_error = exc
            if attempt + 1 < API_MAX_ATTEMPTS:
                time.sleep(min(30, 2 ** (attempt + 1)))

    raise RuntimeError(
        f"OpenAI call failed after {API_MAX_ATTEMPTS}: {last_error}"
    )


def parse_judgment(text):
    s = clean(text)

    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)

    try:
        obj = json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not m:
            raise
        obj = json.loads(m.group(0))

    expected = {
        "faithfulness",
        "hallucination",
        "status_correct",
        "specificity",
        "usefulness",
        "empathy",
        "actionability",
        "relevant_to_review",
        "reasoning",
    }

    if set(obj) != expected:
        raise ValueError(
            f"Judge schema mismatch: expected {sorted(expected)}, got {sorted(obj)}"
        )

    return {
        "faithfulness": strict_score(obj["faithfulness"], "faithfulness"),
        "hallucination": strict_bool(obj["hallucination"], "hallucination"),
        "status_correct": strict_bool(obj["status_correct"], "status_correct"),
        "specificity": strict_score(obj["specificity"], "specificity"),
        "usefulness": strict_score(obj["usefulness"], "usefulness"),
        "empathy": strict_score(obj["empathy"], "empathy"),
        "actionability": strict_score(obj["actionability"], "actionability"),
        "relevant_to_review": strict_bool(
            obj["relevant_to_review"],
            "relevant_to_review",
        ),
        "reasoning": clean(obj["reasoning"]),
    }


def gen_key(pair_key):
    return (
        f"gen::{RAW_GEN_PROMPT_VERSION}::{OPENAI_MODEL}::raw_metadata::{pair_key}"
    )


def judge_key(pair_key):
    return (
        f"judge::{RAW_JUDGE_PROMPT_VERSION}::{OPENAI_MODEL}::raw_metadata::{pair_key}"
    )


def load_progress():
    done = {}

    if not PROGRESS_PATH.exists():
        return done

    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("ok") is True and row.get("job_key"):
                done[row["job_key"]] = row

    return done


def save_progress(record):
    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def generate_one(row, api_key):
    result = call_openai(
        api_key,
        RAW_METADATA_SYSTEM,
        raw_user_prompt(row),
        max_tokens=220,
        json_mode=False,
    )

    return {
        "job_key": gen_key(row["pair_key"]),
        "ok": True,
        "stage": "generation",
        "pair_key": row["pair_key"],
        "response": result["content"],
        "model_returned": result["model_returned"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def judge_one(row, response_text, api_key):
    result = call_openai(
        api_key,
        JUDGE_SYSTEM,
        judge_user_prompt(row, response_text),
        max_tokens=300,
        json_mode=True,
    )

    judgment = parse_judgment(result["content"])

    return {
        "job_key": judge_key(row["pair_key"]),
        "ok": True,
        "stage": "judge",
        "pair_key": row["pair_key"],
        "judgment": judgment,
        "model_returned": result["model_returned"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def run_parallel(label, jobs, fn, progress):
    if not jobs:
        print(f"{label}: already complete.")
        return

    print(f"{label}: {len(jobs)} jobs")
    failures = []

    with ThreadPoolExecutor(max_workers=min(API_WORKERS, len(jobs))) as pool:
        futures = {
            pool.submit(fn, *args): meta
            for args, meta in jobs
        }

        for done, future in enumerate(as_completed(futures), start=1):
            meta = futures[future]

            try:
                rec = future.result()
                progress[rec["job_key"]] = rec
                save_progress(rec)
            except Exception as exc:
                fail = {
                    "job_key": meta["job_key"],
                    "ok": False,
                    "stage": meta["stage"],
                    "pair_key": meta["pair_key"],
                    "error": str(exc),
                    "completed_at_utc": utc_now(),
                }
                save_progress(fail)
                failures.append(fail)
                print("FAILED:", fail)

            if done % 10 == 0 or done == len(jobs):
                print(
                    f"  {done}/{len(jobs)}; failures={len(failures)}",
                    flush=True,
                )


# ------------------------------------------------------------------
# Statistics
# ------------------------------------------------------------------

def exact_mcnemar_p(a_only, b_only):
    n = int(a_only + b_only)

    if n == 0:
        return 1.0

    k = min(int(a_only), int(b_only))
    lower = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)

    return min(1.0, 2.0 * lower)


def paired_binary(df, system_a, system_b, field):
    a = df[df["system"] == system_a].set_index("pair_key")
    b = df[df["system"] == system_b].set_index("pair_key")

    common = a.index.intersection(b.index)

    aa = a.loc[common, field].astype(bool)
    bb = b.loc[common, field].astype(bool)

    if field == "judge_hallucination":
        aa = ~aa
        bb = ~bb
        metric = "no_hallucination"
    else:
        metric = field

    a_only = int((aa & ~bb).sum())
    b_only = int((~aa & bb).sum())

    return {
        "system_a": system_a,
        "system_b": system_b,
        "metric": metric,
        "pairs": int(len(common)),
        "a_only_successes": a_only,
        "b_only_successes": b_only,
        "exact_mcnemar_p": exact_mcnemar_p(a_only, b_only),
    }


def continuous_paired(df, system_a, system_b, field):
    a = df[df["system"] == system_a].set_index("pair_key")
    b = df[df["system"] == system_b].set_index("pair_key")

    common = a.index.intersection(b.index)

    x = a.loc[common, field].astype(float).to_numpy()
    y = b.loc[common, field].astype(float).to_numpy()
    diff = x - y

    if np.allclose(diff, 0):
        stat = 0.0
        p = 1.0
    else:
        result = wilcoxon(
            x,
            y,
            zero_method="wilcox",
            alternative="two-sided",
            method="auto",
        )
        stat = float(result.statistic)
        p = float(result.pvalue)

    return {
        "system_a": system_a,
        "system_b": system_b,
        "metric": field,
        "pairs": int(len(common)),
        "mean_a": float(np.mean(x)),
        "mean_b": float(np.mean(y)),
        "mean_difference_a_minus_b": float(np.mean(diff)),
        "median_difference_a_minus_b": float(np.median(diff)),
        "a_higher": int(np.sum(diff > 0)),
        "b_higher": int(np.sum(diff < 0)),
        "ties": int(np.sum(diff == 0)),
        "wilcoxon_statistic": stat,
        "wilcoxon_two_sided_p": p,
        "analysis_status": "POST_HOC_EXPLORATORY",
    }


def metric_table(df):
    rows = []

    for system in ("closure_aware", "raw_metadata", "binary_state"):
        s = df[df["system"] == system]

        rows.append(
            {
                "system": system,
                "n": int(len(s)),
                "status_correct": float(
                    s["judge_status_correct"].astype(bool).mean()
                ),
                "hallucination": float(
                    s["judge_hallucination"].astype(bool).mean()
                ),
                "relevant_to_review": float(
                    s["judge_relevant_to_review"].astype(bool).mean()
                ),
                "mean_faithfulness": float(
                    s["judge_faithfulness"].astype(float).mean()
                ),
                "mean_specificity": float(
                    s["judge_specificity"].astype(float).mean()
                ),
                "mean_usefulness": float(
                    s["judge_usefulness"].astype(float).mean()
                ),
                "mean_empathy": float(
                    s["judge_empathy"].astype(float).mean()
                ),
                "mean_actionability": float(
                    s["judge_actionability"].astype(float).mean()
                ),
            }
        )

    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Load and validate existing results
# ------------------------------------------------------------------

for path in (FULL82_SOURCE, RAW45_SOURCE):
    if not path.exists():
        raise FileNotFoundError(path)

full = pd.read_csv(FULL82_SOURCE, low_memory=False)
raw45 = pd.read_csv(RAW45_SOURCE, low_memory=False)

if full["pair_key"].nunique() != 82:
    raise AssertionError(
        f"Expected 82 pair keys in original E2E results, got {full['pair_key'].nunique()}"
    )

for system in ("closure_aware", "binary_state"):
    n = int((full["system"] == system).sum())
    if n != 82:
        raise AssertionError(f"Expected 82 {system} rows, got {n}")

if raw45["pair_key"].nunique() != 45 or len(raw45) != 45:
    raise AssertionError(
        f"Expected exactly 45 completed raw-metadata rows, got {len(raw45)}"
    )

if set(raw45["system"].astype(str)) != {"raw_metadata"}:
    raise AssertionError("raw45 file contains unexpected system labels")

all_pairs = (
    full[full["system"] == "closure_aware"]
    .drop_duplicates("pair_key")
    .copy()
)

required_base_cols = [
    "pair_key",
    "app",
    "query_id",
    "review_text",
    "repository",
    "display_issue_id",
    "issue_title",
    "issue_body",
    "binary_state",
    "issue_url",
    "resolution_signal",
    "labels",
    "closed_at",
    "l1_class",
    "subtype",
    "action_l1",
    "known_positive_hit_at_1",
]

missing = set(required_base_cols) - set(all_pairs.columns)

if missing:
    raise AssertionError(
        f"Original E2E file missing columns: {sorted(missing)}"
    )

base82 = all_pairs[required_base_cols].copy()

already_done = set(raw45["pair_key"].astype(str))
remaining = base82[
    ~base82["pair_key"].astype(str).isin(already_done)
].copy()

if len(remaining) != 37:
    raise AssertionError(
        f"Expected exactly 37 remaining raw-metadata cases, got {len(remaining)}"
    )

print("Existing raw-metadata cases reused:", len(raw45))
print("New raw-metadata cases required:", len(remaining))


# ------------------------------------------------------------------
# Run only remaining 37
# ------------------------------------------------------------------

api_key = os.environ.get("OPENAI_API_KEY", "").strip()

if not api_key:
    api_key = getpass.getpass(
        "OPENAI_API_KEY not found. Paste key here (hidden): "
    ).strip()

if not api_key:
    raise SystemExit("No API key supplied.")

progress = load_progress()

gen_jobs = []

for row in remaining.to_dict("records"):
    key = gen_key(row["pair_key"])
    if key not in progress:
        gen_jobs.append(
            (
                (row, api_key),
                {
                    "job_key": key,
                    "stage": "generation",
                    "pair_key": row["pair_key"],
                },
            )
        )

run_parallel(
    "RAW GENERATION — REMAINING 37",
    gen_jobs,
    generate_one,
    progress,
)

judge_jobs = []

for row in remaining.to_dict("records"):
    gk = gen_key(row["pair_key"])
    jk = judge_key(row["pair_key"])

    if gk in progress and jk not in progress:
        judge_jobs.append(
            (
                (
                    row,
                    progress[gk]["response"],
                    api_key,
                ),
                {
                    "job_key": jk,
                    "stage": "judge",
                    "pair_key": row["pair_key"],
                },
            )
        )

run_parallel(
    "RAW JUDGE — REMAINING 37",
    judge_jobs,
    judge_one,
    progress,
)

complete_gen = sum(
    gen_key(x) in progress
    for x in remaining["pair_key"]
)

complete_judge = sum(
    judge_key(x) in progress
    for x in remaining["pair_key"]
)

print(
    f"\nRemaining-37 completion: "
    f"generation {complete_gen}/37; judge {complete_judge}/37"
)

if complete_gen != 37 or complete_judge != 37:
    print(
        "Incomplete. Rerun the same script; completed jobs will be reused."
    )
    raise SystemExit(2)


# ------------------------------------------------------------------
# Build the 37 new rows
# ------------------------------------------------------------------

raw37_rows = []

for row in remaining.to_dict("records"):
    g = progress[gen_key(row["pair_key"])]
    jrec = progress[judge_key(row["pair_key"])]
    j = jrec["judgment"]

    out = dict(row)
    out.update(
        {
            "system": "raw_metadata",
            "response": g["response"],
            "generation_model_returned": g["model_returned"],
            "judge_model_returned": jrec["model_returned"],
            "judge_faithfulness": j["faithfulness"],
            "judge_hallucination": j["hallucination"],
            "judge_status_correct": j["status_correct"],
            "judge_specificity": j["specificity"],
            "judge_usefulness": j["usefulness"],
            "judge_empathy": j["empathy"],
            "judge_actionability": j["actionability"],
            "judge_relevant_to_review": j["relevant_to_review"],
            "judge_reasoning": j["reasoning"],
        }
    )

    raw37_rows.append(out)

raw37 = pd.DataFrame(raw37_rows)

# ------------------------------------------------------------------
# Combine 45 + 37 = 82 raw-metadata rows
# ------------------------------------------------------------------

# Keep shared/result columns; concat tolerates extra columns from the old file.
raw82 = pd.concat(
    [raw45, raw37],
    ignore_index=True,
    sort=False,
)

if len(raw82) != 82 or raw82["pair_key"].nunique() != 82:
    raise AssertionError(
        f"Expected 82 unique raw-metadata rows, got "
        f"{len(raw82)} rows / {raw82['pair_key'].nunique()} unique"
    )

raw82.to_csv(RAW82_PATH, index=False)


# ------------------------------------------------------------------
# Build complete 82 x 3 comparison
# ------------------------------------------------------------------

existing = full[
    full["system"].isin(
        ["closure_aware", "binary_state"]
    )
].copy()

three82 = pd.concat(
    [existing, raw82],
    ignore_index=True,
    sort=False,
)

if len(three82) != 246:
    raise AssertionError(
        f"Expected 246 rows (82x3), got {len(three82)}"
    )

for system in (
    "closure_aware",
    "raw_metadata",
    "binary_state",
):
    n = int((three82["system"] == system).sum())
    if n != 82:
        raise AssertionError(
            f"Expected 82 rows for {system}, got {n}"
        )

# Normalize judge columns.
for col in (
    "judge_status_correct",
    "judge_hallucination",
    "judge_relevant_to_review",
):
    three82[col] = three82[col].map(
        lambda x: strict_bool(x, col)
    )

for col in (
    "judge_faithfulness",
    "judge_specificity",
    "judge_usefulness",
    "judge_empathy",
    "judge_actionability",
):
    three82[col] = three82[col].astype(float)

three82.to_csv(THREE82_PATH, index=False)


# ------------------------------------------------------------------
# Metrics and paired tests
# ------------------------------------------------------------------

metrics = metric_table(three82)
metrics.to_csv(METRICS_PATH, index=False)

binary_fields = (
    "judge_status_correct",
    "judge_hallucination",
    "judge_relevant_to_review",
)

raw_vs_closure = pd.DataFrame(
    [
        paired_binary(
            three82,
            "closure_aware",
            "raw_metadata",
            field,
        )
        for field in binary_fields
    ]
)

raw_vs_binary = pd.DataFrame(
    [
        paired_binary(
            three82,
            "raw_metadata",
            "binary_state",
            field,
        )
        for field in binary_fields
    ]
)

raw_vs_closure["analysis_status"] = "POST_HOC_EXPLORATORY"
raw_vs_binary["analysis_status"] = "POST_HOC_EXPLORATORY"

raw_vs_closure.to_csv(PAIR_RC_PATH, index=False)
raw_vs_binary.to_csv(PAIR_RB_PATH, index=False)

continuous_fields = (
    "judge_faithfulness",
    "judge_specificity",
    "judge_usefulness",
    "judge_empathy",
    "judge_actionability",
)

continuous = pd.DataFrame(
    [
        continuous_paired(
            three82,
            "closure_aware",
            "raw_metadata",
            field,
        )
        for field in continuous_fields
    ]
)

continuous.to_csv(CONT_PATH, index=False)


# ------------------------------------------------------------------
# Protocol + summary
# ------------------------------------------------------------------

PROTOCOL_PATH.write_text(
    json.dumps(
        {
            "created_at_utc": utc_now(),
            "experiment": "raw-metadata isolating ablation extended to all 82",
            "existing_raw_cases_reused": 45,
            "new_raw_cases_generated": 37,
            "total_cases": 82,
            "systems": [
                "closure_aware",
                "raw_metadata",
                "binary_state",
            ],
            "model": OPENAI_MODEL,
            "temperature": TEMPERATURE,
            "raw_metadata_arm": {
                "visible": [
                    "binary state",
                    "resolution/state_reason signal",
                    "labels",
                    "closed_at",
                    "issue title/body/number/url",
                ],
                "hidden": [
                    "l1_class",
                    "subtype",
                    "action_l1",
                    "action template",
                ],
            },
            "statistical_status": (
                "POST-HOC / EXPLORATORY: extension to all 82 was motivated "
                "after observing p=.065 on the 45-case non-resolved subset. "
                "Do not present all-82 p-values as confirmatory."
            ),
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

summary = {
    "created_at_utc": utc_now(),
    "three_arm_metrics": metrics.to_dict("records"),
    "closure_vs_raw_binary_tests": raw_vs_closure.to_dict("records"),
    "raw_vs_binary_binary_tests": raw_vs_binary.to_dict("records"),
    "closure_vs_raw_continuous_tests": continuous.to_dict("records"),
    "statistical_status": "POST_HOC_EXPLORATORY",
}

SUMMARY_PATH.write_text(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)


# ------------------------------------------------------------------
# Print
# ------------------------------------------------------------------

print("\n" + "=" * 110)
print("HÄRING RAW-METADATA ABLATION — ALL 82 COMPLETE")
print("=" * 110)

print("\nTHREE-ARM METRICS")
print(metrics.to_string(index=False))

print("\nCLOSURE-AWARE vs RAW-METADATA — ALL 82")
print(raw_vs_closure.to_string(index=False))

print("\nRAW-METADATA vs BINARY — ALL 82")
print(raw_vs_binary.to_string(index=False))

print("\nCONTINUOUS PAIRED TESTS: CLOSURE-AWARE vs RAW-METADATA")
print(continuous.to_string(index=False))

print(
    "\nSTATISTICAL NOTE: all-82 inferential tests are POST-HOC / "
    "EXPLORATORY because this extension was motivated after the 45-case "
    "p=.065 result."
)

print("\nSaved:")
for path in (
    RAW82_PATH,
    THREE82_PATH,
    METRICS_PATH,
    PAIR_RC_PATH,
    PAIR_RB_PATH,
    CONT_PATH,
    PROTOCOL_PATH,
    SUMMARY_PATH,
):
    print(" ", path)
