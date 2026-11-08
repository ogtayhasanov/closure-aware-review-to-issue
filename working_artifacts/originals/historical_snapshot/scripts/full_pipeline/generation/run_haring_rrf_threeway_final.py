#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
FINAL RRF-EVIDENCE THREE-WAY GENERATION COMPARISON

Purpose
-------
Fix the manuscript configuration mismatch by evaluating all three generation
conditions on the SAME final RRF60-retrieved issue for each of the 82 Häring
positive-query reviews:

    1) closure_aware   -- REUSED exactly from the completed RRF run
    2) raw_metadata    -- NEW
    3) binary_state    -- NEW

No retrieval is rerun. No closure-aware response is regenerated.

New API work
------------
82 raw-metadata generations + 82 judges
82 binary-state generations + 82 judges
= 164 new responses + 164 new judgments = 328 model calls if each request is
one call.

Frozen inferential plan before the new arms are generated
---------------------------------------------------------
Primary final-RRF endpoint:
  closure_aware vs binary_state status correctness on RRF non-resolved closed
  evidence, using one two-sided exact McNemar test.

The raw_metadata arm remains a POST-HOC EXPLORATORY confound check because that
ablation was conceived after the original binary-vs-closure result. We do not
relabel it confirmatory merely because it is now replicated on RRF evidence.

All-82 three-way status rates are descriptive because they mix OPEN, RESOLVED,
and non-resolved evidence. Real-review hallucination comparisons remain
secondary/descriptive.

Inputs expected
---------------
C:\Users\Ogtay\Downloads\haring_rrf_e2e_generation_20260808\
    rrf_closure_aware_responses_and_judgments.csv

Outputs
-------
C:\Users\Ogtay\Downloads\haring_rrf_threeway_generation_20260808\
    api_progress.jsonl
    rrf_threeway_responses_and_judgments.csv
    rrf_threeway_metrics.csv
    rrf_threeway_primary_status_tests.csv
    rrf_threeway_descriptive_paired_tests.csv
    rrf_threeway_protocol.json
    rrf_threeway_summary.json

Safe/resumable: rerun after transient failures; successful jobs are reused.
"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from datetime import datetime, timezone
import getpass
import json
import math
import os
import time

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing openai package. Install with:\n"
        "  python -m pip install -U openai pandas numpy"
    ) from exc


# ---------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o-mini"
TEMPERATURE = 0
API_WORKERS = 3
API_MAX_ATTEMPTS = 5

BINARY_PROMPT_VERSION = "haring-rrf60-binary-generation-v1-2026-08-08"
RAW_PROMPT_VERSION = "haring-rrf60-raw-generation-v1-2026-08-08"
JUDGE_PROMPT_VERSION = "haring-rrf60-final-threeway-judge-v1-2026-08-08"

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
RRF_DIR = DOWNLOADS / "haring_rrf_e2e_generation_20260808"

CLOSURE_SOURCE = RRF_DIR / "rrf_closure_aware_responses_and_judgments.csv"

OUT = DOWNLOADS / "haring_rrf_threeway_generation_20260808"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS_PATH = OUT / "api_progress.jsonl"
THREEWAY_PATH = OUT / "rrf_threeway_responses_and_judgments.csv"
METRICS_PATH = OUT / "rrf_threeway_metrics.csv"
PRIMARY_TESTS_PATH = OUT / "rrf_threeway_primary_status_tests.csv"
DESCRIPTIVE_TESTS_PATH = OUT / "rrf_threeway_descriptive_paired_tests.csv"
PROTOCOL_PATH = OUT / "rrf_threeway_protocol.json"
SUMMARY_PATH = OUT / "rrf_threeway_summary.json"

thread_local = local()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

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
    if s in {"1", "0"}:
        return s == "1"
    raise ValueError(f"{field} is not boolean: {x!r}")


def strict_score(x, field):
    v = float(x)
    if not math.isfinite(v) or not (0.0 <= v <= 1.0):
        raise ValueError(f"{field} outside [0,1]: {x!r}")
    return v


def exact_mcnemar_p(a_only, b_only):
    n = int(a_only + b_only)
    if n == 0:
        return 1.0
    k = min(int(a_only), int(b_only))
    lower = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * lower)


def holm_adjust(ps):
    p = np.asarray(ps, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty(len(p), dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * float(p[idx])))
        adjusted[idx] = running
    return adjusted


def load_progress():
    progress = {}
    if not PROGRESS_PATH.exists():
        return progress
    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("ok"):
                progress[rec["job_key"]] = rec
    return progress


def save_progress(rec):
    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------
# Frozen prompts: binary baseline + raw-metadata arm
# ---------------------------------------------------------------------

BINARY_SYSTEM = """You are a developer-support assistant implementing
a binary issue-state baseline. Write a concise response to a real user review
using only the retrieved software issue evidence supplied below.

Rules:
- You may use only the binary state (open or closed), title, body, number, and
  URL supplied below. You are not given closure-reason metadata or taxonomy.
- Treat an open issue as a known active issue.
- Treat a closed issue as resolved/closed, which is the intended behavior of
  this binary-state baseline.
- Cite the retrieved issue number, and include its URL when one is supplied.
- Never invent versions, releases, dates, commits, file paths, technical causes,
  fixes, canonical issue numbers, or developer promises.
- Be empathetic and factual.
- Keep the response below 100 words.
"""

RAW_SYSTEM = """You are a developer-support assistant.
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


def common_issue_prompt(row):
    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

RETRIEVED ISSUE:
- Tracker: {clean(row.get('repository'))}
- Issue #{clean(row.get('display_issue_id'))}: {clean(row.get('issue_title'))}
- Binary state: {clean(row.get('binary_state'))}
- URL: {clean(row.get('issue_url')) or 'not supplied'}
- Issue body excerpt: {clean(row.get('issue_body'))[:1200]}
"""


def generation_prompt(row, system):
    common = common_issue_prompt(row)

    if system == "binary_state":
        return common + "\nWrite the binary-state baseline response."

    if system == "raw_metadata":
        return common + f"""
RAW TRACKER METADATA:
- resolution/state_reason signal: {clean(row.get('resolution_signal')) or 'none'}
- labels: {clean(row.get('labels')) or 'none'}
- closed_at: {clean(row.get('closed_at')) or 'not supplied'}

Write the response using the raw tracker evidence only."""

    raise KeyError(system)


def judge_prompt(row, response_text, system):
    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

GENERATED SYSTEM:
{system}

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


# ---------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------

def client(api_key):
    if not hasattr(thread_local, "client"):
        thread_local.client = OpenAI(api_key=api_key, timeout=60, max_retries=0)
    return thread_local.client


def call_openai(api_key, system_prompt, user_prompt, max_tokens, json_mode):
    last = None
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

            resp = client(api_key).chat.completions.create(**kwargs)
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
            last = exc
            if attempt + 1 < API_MAX_ATTEMPTS:
                time.sleep(min(30, 2 ** (attempt + 1)))
    raise RuntimeError(f"API call failed after {API_MAX_ATTEMPTS}: {last}")


def parse_judgment(text):
    # Match the completed BGE-FT/RRF judge parser: tolerate an accidental
    # fenced JSON response, but require exactly the frozen rubric fields.
    s = clean(text)
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\\s*", "", s)
        s = re.sub(r"\\s*```$", "", s)

    try:
        obj = json.loads(s)
    except Exception:
        m = re.search(r"\\{.*\\}", s, flags=re.DOTALL)
        if not m:
            raise ValueError("Judge output did not contain a JSON object.")
        obj = json.loads(m.group(0))

    if not isinstance(obj, dict):
        raise ValueError("Judge output was not an object.")

    expected = {
        "faithfulness", "hallucination", "status_correct",
        "specificity", "usefulness", "empathy", "actionability",
        "relevant_to_review", "reasoning",
    }
    if set(obj.keys()) != expected:
        raise ValueError(
            f"Judge fields mismatch. Expected {sorted(expected)}, "
            f"got {sorted(obj.keys())}"
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
            obj["relevant_to_review"], "relevant_to_review"
        ),
        "reasoning": clean(obj["reasoning"]),
    }


def gen_key(pair_key, system):
    ver = BINARY_PROMPT_VERSION if system == "binary_state" else RAW_PROMPT_VERSION
    return f"gen::{ver}::{OPENAI_MODEL}::{system}::{pair_key}"


def judge_key(pair_key, system):
    return f"judge::{JUDGE_PROMPT_VERSION}::{OPENAI_MODEL}::{system}::{pair_key}"


def generate_one(row, system, api_key):
    sys_prompt = BINARY_SYSTEM if system == "binary_state" else RAW_SYSTEM
    result = call_openai(
        api_key,
        sys_prompt,
        generation_prompt(row, system),
        max_tokens=220,
        json_mode=False,
    )
    return {
        "job_key": gen_key(row["pair_key"], system),
        "ok": True,
        "stage": "generation",
        "pair_key": row["pair_key"],
        "system": system,
        "response": result["content"],
        "model_returned": result["model_returned"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def judge_one(row, system, response_text, api_key):
    result = call_openai(
        api_key,
        JUDGE_SYSTEM,
        judge_prompt(row, response_text, system),
        max_tokens=300,
        json_mode=True,
    )
    return {
        "job_key": judge_key(row["pair_key"], system),
        "ok": True,
        "stage": "judge",
        "pair_key": row["pair_key"],
        "system": system,
        "judgment": parse_judgment(result["content"]),
        "model_returned": result["model_returned"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def run_jobs(label, jobs, fn, progress):
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
        for done, future in enumerate(as_completed(futures), 1):
            meta = futures[future]
            try:
                rec = future.result()
                progress[rec["job_key"]] = rec
                save_progress(rec)
            except Exception as exc:
                fail = {
                    "ok": False,
                    **meta,
                    "error": repr(exc),
                    "completed_at_utc": utc_now(),
                }
                save_progress(fail)
                failures.append(fail)
                print("FAILED:", fail, flush=True)

            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}; failures={len(failures)}", flush=True)


# ---------------------------------------------------------------------
# Load/reuse completed RRF closure-aware arm
# ---------------------------------------------------------------------

if not CLOSURE_SOURCE.exists():
    raise FileNotFoundError(
        f"Missing completed RRF closure-aware file:\n{CLOSURE_SOURCE}"
    )

closure = pd.read_csv(CLOSURE_SOURCE, low_memory=False).copy()

if len(closure) != 82 or closure["pair_key"].nunique() != 82:
    raise AssertionError(
        f"Expected 82 unique RRF closure-aware cases, got "
        f"{len(closure)} rows / {closure['pair_key'].nunique()} unique"
    )

if "system" in closure.columns:
    systems = set(closure["system"].astype(str))
    if systems != {"closure_aware"}:
        raise AssertionError(f"Unexpected systems in closure file: {systems}")
else:
    closure["system"] = "closure_aware"

required = {
    "pair_key", "app", "query_id", "review_text", "repository",
    "display_issue_id", "issue_title", "issue_body", "binary_state",
    "issue_url", "resolution_signal", "labels", "closed_at",
    "l1_class", "subtype", "action_l1", "known_positive_hit_at_1",
    "response", "judge_status_correct", "judge_hallucination",
    "judge_relevant_to_review", "judge_faithfulness",
    "judge_specificity", "judge_usefulness", "judge_empathy",
    "judge_actionability",
}
missing = required - set(closure.columns)
if missing:
    raise AssertionError(f"RRF closure file missing columns: {sorted(missing)}")

# Hard reproduce the completed RRF closure-aware run.
closure["judge_status_correct"] = closure["judge_status_correct"].map(
    lambda x: strict_bool(x, "judge_status_correct")
)
closure["judge_hallucination"] = closure["judge_hallucination"].map(
    lambda x: strict_bool(x, "judge_hallucination")
)
closure["judge_relevant_to_review"] = closure["judge_relevant_to_review"].map(
    lambda x: strict_bool(x, "judge_relevant_to_review")
)
closure["known_positive_hit_at_1"] = closure["known_positive_hit_at_1"].map(
    lambda x: strict_bool(x, "known_positive_hit_at_1")
)

assert int(closure["judge_status_correct"].sum()) == 76, (
    "Completed RRF closure-aware status baseline changed; expected 76/82."
)
assert int(closure["judge_hallucination"].sum()) == 6, (
    "Completed RRF closure-aware hallucination baseline changed; expected 6/82."
)
assert int(closure["known_positive_hit_at_1"].sum()) == 16, (
    "Completed RRF known-positive Hit@1 changed; expected 16/82."
)

nonresolved_mask_closure = closure["l1_class"].astype(str).isin(
    {"REJECTED", "ABANDONED", "REDIRECTED"}
)
assert int(nonresolved_mask_closure.sum()) == 36, (
    "Expected 36 RRF non-resolved closed cases."
)
assert int(closure.loc[nonresolved_mask_closure, "judge_status_correct"].sum()) == 30, (
    "Expected completed RRF closure status 30/36 on non-resolved closed."
)

base_cols = [
    "pair_key", "app", "query_id", "review_text", "repository",
    "display_issue_id", "issue_title", "issue_body", "binary_state",
    "issue_url", "resolution_signal", "labels", "closed_at",
    "l1_class", "subtype", "action_l1", "known_positive_hit_at_1",
]
base = closure[base_cols].drop_duplicates("pair_key").copy()


# ---------------------------------------------------------------------
# Run only the two missing arms
# ---------------------------------------------------------------------

api_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not api_key:
    api_key = getpass.getpass(
        "OPENAI_API_KEY not found. Paste key here (hidden): "
    ).strip()
if not api_key:
    raise SystemExit("No OpenAI API key supplied.")

progress = load_progress()

gen_jobs = []
for row in base.to_dict("records"):
    for system in ("binary_state", "raw_metadata"):
        key = gen_key(row["pair_key"], system)
        if key not in progress:
            gen_jobs.append(
                (
                    (row, system, api_key),
                    {
                        "job_key": key,
                        "stage": "generation",
                        "pair_key": row["pair_key"],
                        "system": system,
                    },
                )
            )

run_jobs("NEW RRF GENERATION", gen_jobs, generate_one, progress)

judge_jobs = []
for row in base.to_dict("records"):
    for system in ("binary_state", "raw_metadata"):
        gk = gen_key(row["pair_key"], system)
        jk = judge_key(row["pair_key"], system)
        if gk in progress and jk not in progress:
            judge_jobs.append(
                (
                    (row, system, progress[gk]["response"], api_key),
                    {
                        "job_key": jk,
                        "stage": "judge",
                        "pair_key": row["pair_key"],
                        "system": system,
                    },
                )
            )

run_jobs("NEW RRF JUDGE", judge_jobs, judge_one, progress)

expected = 82 * 2
complete_gen = sum(
    gen_key(row["pair_key"], system) in progress
    for row in base.to_dict("records")
    for system in ("binary_state", "raw_metadata")
)
complete_judge = sum(
    judge_key(row["pair_key"], system) in progress
    for row in base.to_dict("records")
    for system in ("binary_state", "raw_metadata")
)

print(f"\nCompletion: generations {complete_gen}/{expected}; judges {complete_judge}/{expected}")
if complete_gen != expected or complete_judge != expected:
    print("Incomplete. Rerun the same script; completed jobs will be reused.")
    raise SystemExit(2)


# ---------------------------------------------------------------------
# Build final 82 x 3 table
# ---------------------------------------------------------------------

new_rows = []
for row in base.to_dict("records"):
    for system in ("binary_state", "raw_metadata"):
        g = progress[gen_key(row["pair_key"], system)]
        jrec = progress[judge_key(row["pair_key"], system)]
        j = jrec["judgment"]

        out = dict(row)
        out.update({
            "system": system,
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
        })
        new_rows.append(out)

new = pd.DataFrame(new_rows)

# Keep closure file's extra audit columns; concat safely.
three = pd.concat([closure, new], ignore_index=True, sort=False)

if len(three) != 246:
    raise AssertionError(f"Expected 246 rows (82x3), got {len(three)}")
for system in ("closure_aware", "raw_metadata", "binary_state"):
    s = three[three["system"] == system]
    if len(s) != 82 or s["pair_key"].nunique() != 82:
        raise AssertionError(f"{system}: expected 82 unique rows")

for col in ("judge_status_correct", "judge_hallucination", "judge_relevant_to_review",
            "known_positive_hit_at_1"):
    three[col] = three[col].map(lambda x, c=col: strict_bool(x, c))
for col in ("judge_faithfulness", "judge_specificity", "judge_usefulness",
            "judge_empathy", "judge_actionability"):
    three[col] = three[col].astype(float)

# Benchmark-gated strict success for each arm.
three["known_positive_gated_strict_success"] = (
    three["known_positive_hit_at_1"].astype(bool)
    & three["judge_status_correct"].astype(bool)
    & ~three["judge_hallucination"].astype(bool)
    & three["judge_relevant_to_review"].astype(bool)
)

three.to_csv(THREEWAY_PATH, index=False)


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------

def metric_row(df, subset, system):
    s = df[df["system"] == system]
    return {
        "subset": subset,
        "system": system,
        "n": int(len(s)),
        "status_correct_count": int(s["judge_status_correct"].sum()),
        "status_correct_rate": float(s["judge_status_correct"].mean()),
        "hallucination_count": int(s["judge_hallucination"].sum()),
        "hallucination_rate": float(s["judge_hallucination"].mean()),
        "mean_faithfulness": float(s["judge_faithfulness"].mean()),
        "mean_specificity": float(s["judge_specificity"].mean()),
        "mean_usefulness": float(s["judge_usefulness"].mean()),
        "mean_empathy": float(s["judge_empathy"].mean()),
        "mean_actionability": float(s["judge_actionability"].mean()),
        "strict_success_count": int(s["known_positive_gated_strict_success"].sum()),
        "strict_success_rate": float(s["known_positive_gated_strict_success"].mean()),
    }

metric_rows = []
subsets = {
    "all_82": np.ones(len(three), dtype=bool),
    "nonresolved_closed": three["l1_class"].astype(str).isin(
        {"REJECTED", "ABANDONED", "REDIRECTED"}
    ),
    "benchmark_confirmed_top1": three["known_positive_hit_at_1"].astype(bool),
}

for subset_name, mask in subsets.items():
    d = three.loc[mask].copy()
    for system in ("closure_aware", "raw_metadata", "binary_state"):
        metric_rows.append(metric_row(d, subset_name, system))

metrics = pd.DataFrame(metric_rows)
metrics.to_csv(METRICS_PATH, index=False)


# ---------------------------------------------------------------------
# Paired tests
# ---------------------------------------------------------------------

def paired_binary(df, subset_mask, system_a, system_b, field):
    d = df.loc[subset_mask].copy()
    a = d[d["system"] == system_a].set_index("pair_key")
    b = d[d["system"] == system_b].set_index("pair_key")
    common = a.index.intersection(b.index)
    if len(common) == 0:
        raise AssertionError("No paired rows")

    aa = a.loc[common, field].astype(bool)
    bb = b.loc[common, field].astype(bool)

    # For hallucination, success = no hallucination.
    metric = field
    if field == "judge_hallucination":
        aa = ~aa
        bb = ~bb
        metric = "no_hallucination"

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


# PRIMARY final-RRF endpoint: non-resolved status, closure vs binary.
# This directly tests the paper's core closure-outcome hypothesis on the final
# retriever's evidence. Family size = 1, so no multiplicity adjustment is needed.
nr = three["l1_class"].astype(str).isin(
    {"REJECTED", "ABANDONED", "REDIRECTED"}
)
primary = pd.DataFrame([
    paired_binary(
        three,
        nr,
        "closure_aware",
        "binary_state",
        "judge_status_correct",
    )
])
primary["family"] = "FINAL_RRF_NONRESOLVED_STATUS_PRIMARY"
primary["analysis_status"] = "FROZEN_BEFORE_NEW_BINARY_ARM"
primary["multiplicity"] = "single_primary_endpoint_no_adjustment"
primary.to_csv(PRIMARY_TESTS_PATH, index=False)

# Secondary/descriptive checks. The structured-vs-raw comparison is explicitly
# POST-HOC EXPLORATORY because the raw-metadata ablation itself was motivated
# after the original closure-vs-binary result.
desc_rows = []
allmask = np.ones(len(three), dtype=bool)
for subset_name, mask in [("all_82", allmask), ("nonresolved_closed", nr)]:
    for a, b in [
        ("closure_aware", "binary_state"),
        ("closure_aware", "raw_metadata"),
        ("raw_metadata", "binary_state"),
    ]:
        for field in ("judge_status_correct", "judge_hallucination"):
            row = paired_binary(three, mask, a, b, field)
            row["subset"] = subset_name
            if {a, b} == {"closure_aware", "raw_metadata"}:
                row["analysis_status"] = "POST_HOC_EXPLORATORY_CONFOUND_CHECK"
            elif a == "raw_metadata" or b == "raw_metadata":
                row["analysis_status"] = "POST_HOC_EXPLORATORY_MECHANISM_CHECK"
            else:
                row["analysis_status"] = "DESCRIPTIVE_SECONDARY"
            desc_rows.append(row)

descriptive = pd.DataFrame(desc_rows)
descriptive.to_csv(DESCRIPTIVE_TESTS_PATH, index=False)


# ---------------------------------------------------------------------
# Protocol + summary
# ---------------------------------------------------------------------

protocol = {
    "created_at_utc": utc_now(),
    "experiment": "Final-RRF same-evidence three-way generation comparison",
    "retriever": "frozen RRF60(BGE-ZS + BM25), issue title retrieval",
    "queries": 82,
    "systems": ["closure_aware", "raw_metadata", "binary_state"],
    "closure_arm": "reused exactly from completed RRF closure-aware run",
    "new_arms": ["raw_metadata", "binary_state"],
    "model": OPENAI_MODEL,
    "temperature": TEMPERATURE,
    "new_model_calls_expected": 328,
    "primary_status_family": {
        "subset": "RRF-retrieved non-resolved closed evidence",
        "tests": ["closure_aware vs binary_state"],
        "metric": "judge_status_correct",
        "test": "two-sided exact McNemar",
        "multiplicity": "single primary endpoint; no adjustment required",
        "frozen_before_new_binary_arm_generated": True,
    },
    "raw_metadata_status": (
        "POST-HOC EXPLORATORY confound check; retain this status even though "
        "the RRF-evidence replication is frozen before generating the new arm"
    ),
    "all_82_rates": "descriptive final-configuration comparison",
    "hallucination": "secondary/descriptive on real reviews",
    "note": (
        "This run exists to remove the evidence-retriever mismatch in the manuscript. "
        "It does not rerun retrieval or tune prompts after outcomes."
    ),
}
PROTOCOL_PATH.write_text(
    json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8"
)

summary = {
    "created_at_utc": utc_now(),
    "metrics": metrics.to_dict("records"),
    "primary_status_tests": primary.to_dict("records"),
    "descriptive_paired_tests": descriptive.to_dict("records"),
}
SUMMARY_PATH.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
)

print("\n" + "=" * 112)
print("FINAL RRF THREE-WAY GENERATION COMPLETE")
print("=" * 112)

print("\nALL-82 STATUS / HALLUCINATION")
print(
    metrics[metrics["subset"] == "all_82"][
        ["system", "n", "status_correct_count", "status_correct_rate",
         "hallucination_count", "hallucination_rate",
         "strict_success_count", "strict_success_rate"]
    ].to_string(index=False)
)

print("\nNON-RESOLVED CLOSED STATUS / HALLUCINATION")
print(
    metrics[metrics["subset"] == "nonresolved_closed"][
        ["system", "n", "status_correct_count", "status_correct_rate",
         "hallucination_count", "hallucination_rate"]
    ].to_string(index=False)
)

print("\nPRIMARY FINAL-RRF STATUS TEST")
print(primary.to_string(index=False))

print("\nSaved:")
for p in (
    THREEWAY_PATH, METRICS_PATH, PRIMARY_TESTS_PATH,
    DESCRIPTIVE_TESTS_PATH, PROTOCOL_PATH, SUMMARY_PATH
):
    print(" ", p)
