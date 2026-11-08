# ============================================================
# FROZEN HÄRING BGE-FT END-TO-END GENERATION + EVALUATION
# ============================================================
#
# Input:
#   C:\Users\Ogtay\Downloads\haring_e2e_manifest\
#       haring_e2e_bge_ft_manifest_82_FINAL.csv
#
# Experiment:
#   82 real Häring known-positive reviews
#   frozen BGE-FT epoch-2 top-1 issue per review
#   two generation systems on THE SAME retrieved issue:
#       1) closure_aware
#       2) binary_state
#
# IMPORTANT:
#   The benchmark labels are pool-incomplete. Therefore the existing
#   retrieval_correct_at_1 field is reported as KNOWN-POSITIVE HIT@1.
#   A False value does NOT prove the retrieved issue is semantically irrelevant.
#
# Generation/judge model:
#   gpt-4o-mini
#   temperature = 0
#
# The prompt logic is the same as the prior paper protocol, with only
# tracker-agnostic wording ("issue" rather than "GitHub issue") so Firefox
# Bugzilla and VLC Trac are represented correctly.
#
# Outputs:
#   C:\Users\Ogtay\Downloads\haring_e2e_generation_20260808\
#       api_progress.jsonl
#       responses_and_judgments.csv
#       per_case_e2e.csv
#       headline_metrics.csv
#       outcome_metrics.csv
#       paired_tests.csv
#       manual_audit_9_BLINDED.csv
#       manual_audit_9_KEY.csv
#       semantic_top1_audit_82.csv
#       prompts_and_protocol.json
#       run_summary.json
#
# Safe/resumable:
#   - progress appended after every successful API call
#   - rerun resumes completed generation/judge jobs
#   - API key is never saved or printed
# ============================================================

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
import getpass
import hashlib
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing package 'openai'. Install once with:\n"
        "  python -m pip install -U openai pandas numpy\n"
    ) from exc


# ------------------------------------------------------------------
# Frozen protocol
# ------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o-mini"
GENERATION_TEMPERATURE = 0
JUDGE_TEMPERATURE = 0
API_WORKERS = 3
API_MAX_ATTEMPTS = 5

GEN_PROMPT_VERSION = "haring-real-review-e2e-generation-v1-2026-08-08"
JUDGE_PROMPT_VERSION = "haring-real-review-e2e-judge-v1-2026-08-08"

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
INPUT_PATH = (
    DOWNLOADS
    / "haring_e2e_manifest"
    / "haring_e2e_bge_ft_manifest_82_FINAL.csv"
)

OUT = DOWNLOADS / "haring_e2e_generation_20260808"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS_PATH = OUT / "api_progress.jsonl"
RESPONSES_PATH = OUT / "responses_and_judgments.csv"
PER_CASE_PATH = OUT / "per_case_e2e.csv"
HEADLINE_PATH = OUT / "headline_metrics.csv"
OUTCOME_PATH = OUT / "outcome_metrics.csv"
PAIRED_PATH = OUT / "paired_tests.csv"
MANUAL_BLIND_PATH = OUT / "manual_audit_9_BLINDED.csv"
MANUAL_KEY_PATH = OUT / "manual_audit_9_KEY.csv"
SEMANTIC_AUDIT_PATH = OUT / "semantic_top1_audit_82.csv"
PROMPTS_PATH = OUT / "prompts_and_protocol.json"
SUMMARY_PATH = OUT / "run_summary.json"

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


def as_bool(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return clean(x).lower() in {"true", "1", "yes", "y"}


def norm_id(x):
    s = clean(x)
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_labels(value):
    s = clean(value)
    if not s:
        return []
    if ";" in s:
        return [x.strip() for x in s.split(";") if x.strip()]
    return [s]


def human_issue_id(row):
    # Nextcloud corpus retrieval IDs are GitHub global IDs; cite issue number.
    if clean(row.get("app")) == "Nextcloud":
        n = norm_id(row.get("nextcloud_issue_number"))
        if n:
            return n
    return norm_id(row.get("bge_top1_issue_id"))


def normalized_binary_state(row):
    app = clean(row.get("app"))
    raw = clean(row.get("status")).lower()

    if app == "Firefox":
        if raw.upper() in {"RESOLVED", "VERIFIED"}:
            return "closed"
        if raw.upper() in {"NEW", "REOPENED", "UNCONFIRMED", "ASSIGNED"}:
            return "open"

    if app == "VLC":
        if raw == "closed":
            return "closed"
        if raw in {"new", "reopened", "assigned"}:
            return "open"

    if app == "Nextcloud":
        if raw in {"open", "closed"}:
            return raw

    raise ValueError(f"Cannot normalize binary state for {app}: {raw!r}")


def repository_label(row):
    app = clean(row.get("app"))
    if app == "Firefox":
        return "Mozilla Firefox (Bugzilla)"
    if app == "VLC":
        return "VLC Android (Trac)"
    if app == "Nextcloud":
        return "nextcloud/android (GitHub)"
    return app


def historical_closed_at(row):
    app = clean(row.get("app"))
    if app == "Firefox":
        return clean(row.get("cf_last_resolved"))
    if app == "Nextcloud":
        return clean(row.get("closed_at"))
    return ""


def normalized_resolution_signal(row):
    # This is the tracker-agnostic replacement for GitHub-only state_reason.
    return clean(row.get("closure_resolution_signal"))


def pair_key_for(row):
    material = "\n".join(
        [
            clean(row.get("app")),
            clean(row.get("query_id")),
            norm_id(row.get("bge_top1_issue_id")),
            clean(row.get("review_text")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------
# Frozen action guidance from the paper protocol
# ------------------------------------------------------------------

ACTION_INSTRUCTIONS = {
    "KNOWN_BUG": (
        "This is a known open bug. Acknowledge it and say the team is "
        "investigating; do not promise a date or fix."
    ),
    "KNOWN_ISSUE": (
        "This is a known open issue. Acknowledge it and say the team is aware; "
        "do not promise a date or fix."
    ),
    "RESOLVED": (
        "This issue was resolved. State that outcome and cite the issue. If a "
        "close date is present, it may be cited. Do not invent the fix, release, "
        "version, commit, or date."
    ),
    "REJECTED": (
        "Developers closed this without planning a fix, or marked it wontfix, "
        "invalid, by-design, or not-a-bug. Communicate the literal available "
        "metadata honestly. Do not say it was fixed and do not promise a fix."
    ),
    "ABANDONED": (
        "The issue was closed without confirmed resolution. If metadata indicates "
        "stale or inactivity, say that explicitly; otherwise say the metadata "
        "does not confirm a resolution. Suggest a new report if the problem still "
        "occurs. Do not say it was fixed."
    ),
    "ABANDONED_NEEDS_INFO": (
        "The issue was closed because more information or reproduction evidence "
        "was needed. Ask for concrete reproduction steps, device/OS/app version, "
        "and useful logs or screenshots. Do not say it was fixed."
    ),
    "ABANDONED_UPSTREAM": (
        "The issue depends on an upstream or third-party project. Communicate "
        "that dependency without inventing its name or status. Do not claim that "
        "this app fixed it."
    ),
    "REDIRECTED": (
        "The issue was closed as a duplicate or redirected elsewhere. Say it is "
        "tracked elsewhere. Mention a canonical issue only if its number is "
        "explicitly present in the supplied metadata; never invent one."
    ),
}


GENERATION_SYSTEM_CLOSURE = """You are a developer-support assistant.
Write a concise response to a real user review using only the retrieved software
issue evidence supplied below.

Rules:
- Use only facts present in the supplied metadata.
- Cite the retrieved issue number, and include its URL when one is supplied.
- Never invent versions, releases, dates, commits, file paths, technical causes,
  fixes, canonical issue numbers, or developer promises.
- Correctly communicate the authoritative closure class and action.
- Be empathetic and factual.
- Keep the response below 100 words.
"""


GENERATION_SYSTEM_BINARY = """You are a developer-support assistant implementing
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


def generation_user_prompt(row, system):
    common = f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

RETRIEVED ISSUE:
- Tracker: {clean(row.get('repository'))}
- Issue #{clean(row.get('display_issue_id'))}: {clean(row.get('issue_title'))}
- Binary state: {clean(row.get('binary_state'))}
- URL: {clean(row.get('issue_url')) or 'not supplied'}
- Issue body excerpt: {clean(row.get('issue_body'))[:1200]}
"""

    if system == "binary_state":
        return common + "\nWrite the binary-state baseline response."

    labels = ", ".join(parse_labels(row.get("labels"))) or "none"
    action = clean(row.get("action_l1"))
    if action not in ACTION_INSTRUCTIONS:
        raise KeyError(f"Unknown action_l1={action!r}")

    instruction = ACTION_INSTRUCTIONS[action]

    return common + f"""

AUTHORITATIVE CLOSURE METADATA:
- resolution_signal: {clean(row.get('resolution_signal')) or 'none'}
- labels: {labels}
- closed_at: {clean(row.get('closed_at')) or 'not supplied'}
- l1_class: {clean(row.get('l1_class'))}
- subtype: {clean(row.get('subtype'))}
- action_l1: {action}

ACTION-SPECIFIC GUIDANCE:
{instruction}

Write the closure-reason-aware response."""


def judge_user_prompt(row, response_text, system):
    labels = ", ".join(parse_labels(row.get("labels"))) or "none"

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
- Labels: {labels}
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
# OpenAI calls
# ------------------------------------------------------------------

def get_openai_client(api_key):
    if not hasattr(thread_local, "openai_client"):
        thread_local.openai_client = OpenAI(
            api_key=api_key,
            timeout=60,
            max_retries=0,
        )
    return thread_local.openai_client


def call_openai(api_key, system_prompt, user_prompt, max_tokens, temperature, json_mode=False):
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
                "temperature": temperature,
            }

            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = get_openai_client(api_key).chat.completions.create(**kwargs)
            content = clean(response.choices[0].message.content)

            if not content:
                raise RuntimeError("API returned an empty response.")

            usage = {}
            if getattr(response, "usage", None) is not None:
                if hasattr(response.usage, "model_dump"):
                    usage = response.usage.model_dump()
                else:
                    usage = {
                        k: getattr(response.usage, k, None)
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                    }

            return {
                "content": content,
                "model_returned": clean(getattr(response, "model", OPENAI_MODEL)),
                "usage": usage,
            }

        except Exception as exc:
            last_error = exc
            if attempt + 1 < API_MAX_ATTEMPTS:
                time.sleep(min(30, 2 ** (attempt + 1)))

    raise RuntimeError(
        f"OpenAI call failed after {API_MAX_ATTEMPTS} attempts: {last_error}"
    )


def parse_json_object(text):
    s = clean(text)
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)

    try:
        obj = json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not m:
            raise ValueError("Judge output did not contain a JSON object.")
        obj = json.loads(m.group(0))

    if not isinstance(obj, dict):
        raise ValueError("Judge output was not an object.")

    return obj


def strict_bool(value, field):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"Judge field {field!r} is not boolean: {value!r}")


def strict_score(value, field):
    x = float(value)
    if not math.isfinite(x) or not (0.0 <= x <= 1.0):
        raise ValueError(f"Judge field {field!r} outside [0,1]: {value!r}")
    return x


def validate_judgment(raw):
    exact_fields = {
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

    if set(raw.keys()) != exact_fields:
        raise ValueError(
            f"Judge fields mismatch. Expected {sorted(exact_fields)}, "
            f"got {sorted(raw.keys())}"
        )

    out = {}
    for field in ("faithfulness", "specificity", "usefulness", "empathy", "actionability"):
        out[field] = strict_score(raw[field], field)

    out["hallucination"] = strict_bool(raw["hallucination"], "hallucination")
    out["status_correct"] = strict_bool(raw["status_correct"], "status_correct")
    out["relevant_to_review"] = strict_bool(
        raw["relevant_to_review"], "relevant_to_review"
    )
    out["reasoning"] = clean(raw["reasoning"])

    if not out["reasoning"]:
        raise ValueError("Judge reasoning is empty.")

    return out


# ------------------------------------------------------------------
# Progress / resume
# ------------------------------------------------------------------

def generation_job_key(pair_key, system):
    return (
        f"generation::{GEN_PROMPT_VERSION}::{OPENAI_MODEL}::"
        f"{system}::{pair_key}"
    )


def judge_job_key(pair_key, system):
    return (
        f"judge::{JUDGE_PROMPT_VERSION}::{OPENAI_MODEL}::"
        f"{system}::{pair_key}"
    )


def load_progress():
    progress = {}

    if not PROGRESS_PATH.exists():
        return progress

    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                raise RuntimeError(
                    f"Malformed progress JSONL at line {line_no}: {exc}"
                ) from exc

            if row.get("ok") is True and row.get("job_key"):
                progress[row["job_key"]] = row

    return progress


def append_progress(record):
    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def execute_generation(row, system, api_key):
    pair_key = row["pair_key"]
    system_prompt = (
        GENERATION_SYSTEM_CLOSURE
        if system == "closure_aware"
        else GENERATION_SYSTEM_BINARY
    )

    result = call_openai(
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=generation_user_prompt(row, system),
        max_tokens=220,
        temperature=GENERATION_TEMPERATURE,
        json_mode=False,
    )

    return {
        "job_key": generation_job_key(pair_key, system),
        "stage": "generation",
        "ok": True,
        "pair_key": pair_key,
        "system": system,
        "prompt_version": GEN_PROMPT_VERSION,
        "model_requested": OPENAI_MODEL,
        "model_returned": result["model_returned"],
        "response": result["content"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def execute_judge(row, system, response_text, api_key):
    pair_key = row["pair_key"]

    result = call_openai(
        api_key=api_key,
        system_prompt=JUDGE_SYSTEM,
        user_prompt=judge_user_prompt(row, response_text, system),
        max_tokens=300,
        temperature=JUDGE_TEMPERATURE,
        json_mode=True,
    )

    judgment = validate_judgment(parse_json_object(result["content"]))

    return {
        "job_key": judge_job_key(pair_key, system),
        "stage": "judge",
        "ok": True,
        "pair_key": pair_key,
        "system": system,
        "prompt_version": JUDGE_PROMPT_VERSION,
        "model_requested": OPENAI_MODEL,
        "model_returned": result["model_returned"],
        "judgment": judgment,
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def run_jobs(label, jobs, worker, progress):
    if not jobs:
        print(f"{label}: all complete.", flush=True)
        return []

    failures = []

    print(f"{label}: {len(jobs)} API jobs", flush=True)

    with ThreadPoolExecutor(max_workers=min(API_WORKERS, len(jobs))) as pool:
        futures = {
            pool.submit(worker, *job["args"]): job
            for job in jobs
        }

        for completed, future in enumerate(as_completed(futures), start=1):
            job = futures[future]

            try:
                record = future.result()
                progress[record["job_key"]] = record
                append_progress(record)
            except Exception as exc:
                failure = {
                    "job_key": job["job_key"],
                    "stage": job["stage"],
                    "ok": False,
                    "pair_key": job["pair_key"],
                    "system": job["system"],
                    "error": str(exc),
                    "completed_at_utc": utc_now(),
                }
                append_progress(failure)
                failures.append(failure)
                print(
                    f"  FAILED {job['stage']} {job['system']} "
                    f"{job['pair_key'][:10]}: {exc}",
                    flush=True,
                )

            if completed % 20 == 0 or completed == len(jobs):
                print(
                    f"  {label} {completed}/{len(jobs)}; "
                    f"failures={len(failures)}",
                    flush=True,
                )

    return failures


# ------------------------------------------------------------------
# Statistics
# ------------------------------------------------------------------

def exact_mcnemar_p(b, c):
    # Exact two-sided binomial test on discordant pairs under p=0.5.
    n = int(b + c)
    if n == 0:
        return 1.0

    k = min(int(b), int(c))
    lower = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2.0 * lower)


def mean_bool(series):
    return float(pd.Series(series).astype(bool).mean()) if len(series) else float("nan")


def metrics_for(subset, label):
    rows = []

    for system in ("closure_aware", "binary_state"):
        s = subset[subset["system"] == system].copy()
        if len(s) == 0:
            continue

        rows.append(
            {
                "subset": label,
                "system": system,
                "n": int(len(s)),
                "status_correct_rate": mean_bool(s["judge_status_correct"]),
                "hallucination_rate": mean_bool(s["judge_hallucination"]),
                "relevant_to_review_rate": mean_bool(s["judge_relevant_to_review"]),
                "mean_faithfulness": float(s["judge_faithfulness"].mean()),
                "mean_specificity": float(s["judge_specificity"].mean()),
                "mean_usefulness": float(s["judge_usefulness"].mean()),
                "mean_empathy": float(s["judge_empathy"].mean()),
                "mean_actionability": float(s["judge_actionability"].mean()),
                "known_positive_gated_status_success_rate": mean_bool(
                    s["known_positive_gated_status_success"]
                ),
                "known_positive_gated_safe_success_rate": mean_bool(
                    s["known_positive_gated_safe_success"]
                ),
                "known_positive_gated_strict_success_rate": mean_bool(
                    s["known_positive_gated_strict_success"]
                ),
            }
        )

    return rows


def paired_binary_test(per_case, field, subset_mask, subset_name):
    temp = per_case[subset_mask].copy()

    left = temp[temp["system"] == "closure_aware"].set_index("pair_key")
    right = temp[temp["system"] == "binary_state"].set_index("pair_key")

    common = left.index.intersection(right.index)
    left = left.loc[common]
    right = right.loc[common]

    if field == "judge_hallucination":
        # For hallucination, success means NOT hallucinating.
        a = ~left[field].astype(bool)
        bsys = ~right[field].astype(bool)
        metric_name = "no_hallucination"
    else:
        a = left[field].astype(bool)
        bsys = right[field].astype(bool)
        metric_name = field

    closure_only = int((a & ~bsys).sum())
    binary_only = int((~a & bsys).sum())

    return {
        "subset": subset_name,
        "metric": metric_name,
        "pairs": int(len(common)),
        "closure_only_successes": closure_only,
        "binary_only_successes": binary_only,
        "exact_mcnemar_p": exact_mcnemar_p(closure_only, binary_only),
    }


# ------------------------------------------------------------------
# Load + hard validate frozen manifest
# ------------------------------------------------------------------

if not INPUT_PATH.exists():
    raise FileNotFoundError(
        f"Missing frozen manifest:\n{INPUT_PATH}"
    )

src = pd.read_csv(INPUT_PATH, low_memory=False)

if len(src) != 82:
    raise AssertionError(f"Expected 82 rows, got {len(src)}")

if int((src["closure_class"].astype(str) == "UNRESOLVED").sum()) != 0:
    raise AssertionError("Frozen manifest still contains unresolved closure cases.")

app_counts = src.groupby("app").size().astype(int).to_dict()
if app_counts != {"Firefox": 28, "Nextcloud": 33, "VLC": 21}:
    raise AssertionError(f"Unexpected app counts: {app_counts}")

known_hit = src["retrieval_correct_at_1"].map(as_bool)
if int(known_hit.sum()) != 9:
    raise AssertionError(
        f"Expected 9 benchmark-known positive Hit@1 cases, got {int(known_hit.sum())}"
    )

class_counts = src.groupby("closure_class").size().astype(int).to_dict()
expected_classes = {
    "ABANDONED": 31,
    "OPEN": 19,
    "REDIRECTED": 11,
    "REJECTED": 3,
    "RESOLVED": 18,
}
if class_counts != expected_classes:
    raise AssertionError(
        f"Closure distribution changed.\nExpected {expected_classes}\nGot {class_counts}"
    )

# Build normalized generation rows.
input_rows = []

for raw in src.to_dict("records"):
    action = clean(raw.get("closure_action"))
    l1 = clean(raw.get("closure_class"))
    subtype = clean(raw.get("closure_subtype"))

    if action not in ACTION_INSTRUCTIONS:
        raise AssertionError(
            f"Unknown/missing closure_action={action!r} for "
            f"{raw.get('app')}/{raw.get('query_id')}"
        )

    row = {
        "pair_key": pair_key_for(raw),
        "app": clean(raw.get("app")),
        "query_id": norm_id(raw.get("query_id")),
        "review_text": clean(raw.get("review_text")),
        "known_positive_issue_ids": clean(raw.get("gold_issue_ids")),
        "known_positive_hit_at_1": as_bool(raw.get("retrieval_correct_at_1")),
        "retrieved_corpus_issue_id": norm_id(raw.get("bge_top1_issue_id")),
        "display_issue_id": human_issue_id(raw),
        "repository": repository_label(raw),
        "issue_title": clean(raw.get("issue_title")),
        "issue_body": clean(raw.get("issue_body")),
        "binary_state": normalized_binary_state(raw),
        "issue_url": clean(raw.get("issue_url")),
        "resolution_signal": normalized_resolution_signal(raw),
        "labels": clean(raw.get("labels")),
        "closed_at": historical_closed_at(raw),
        "l1_class": l1,
        "subtype": subtype,
        "action_l1": action,
        "closure_mapping_source": clean(raw.get("closure_mapping_source")),
        "closure_evidence": clean(raw.get("closure_evidence")),
        "bge_top1_score": raw.get("bge_top1_score"),
    }

    if not row["review_text"]:
        raise AssertionError(
            f"Missing review text: {row['app']}/{row['query_id']}"
        )
    if not row["display_issue_id"]:
        raise AssertionError(
            f"Missing human-facing issue id: {row['app']}/{row['query_id']}"
        )
    if not row["issue_title"]:
        raise AssertionError(
            f"Missing issue title: {row['app']}/{row['query_id']}"
        )

    input_rows.append(row)

inputs = pd.DataFrame(input_rows)

if inputs["pair_key"].duplicated().any():
    raise AssertionError("Duplicate pair_key detected.")

# Save exact prompts/protocol before API calls.
PROMPTS_PATH.write_text(
    json.dumps(
        {
            "created_at_utc": utc_now(),
            "input_manifest": str(INPUT_PATH),
            "retriever": "BAAI/bge-base-en-v1.5 fine-tuned epoch 2; frozen",
            "retrieval_scope": (
                "82 real Häring reviews with >=1 original human-judged positive; "
                "top-1 ranked against each app's full tracker corpus"
            ),
            "benchmark_note": (
                "Original Häring pair judgments are pool-incomplete. "
                "known_positive_hit_at_1=False does not prove semantic irrelevance."
            ),
            "model_requested": OPENAI_MODEL,
            "generation_temperature": GENERATION_TEMPERATURE,
            "judge_temperature": JUDGE_TEMPERATURE,
            "generation_prompt_version": GEN_PROMPT_VERSION,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "closure_aware_system_prompt": GENERATION_SYSTEM_CLOSURE,
            "binary_state_system_prompt": GENERATION_SYSTEM_BINARY,
            "judge_system_prompt": JUDGE_SYSTEM,
            "action_instructions": ACTION_INSTRUCTIONS,
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

# ------------------------------------------------------------------
# API key
# ------------------------------------------------------------------

api_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not api_key:
    api_key = getpass.getpass(
        "OPENAI_API_KEY not found in environment. Paste key here (hidden): "
    ).strip()

if not api_key:
    raise SystemExit("No OpenAI API key supplied.")

# ------------------------------------------------------------------
# Run / resume generation
# ------------------------------------------------------------------

progress = load_progress()

generation_jobs = []

for row in inputs.to_dict("records"):
    for system in ("closure_aware", "binary_state"):
        key = generation_job_key(row["pair_key"], system)
        if key not in progress:
            generation_jobs.append(
                {
                    "job_key": key,
                    "stage": "generation",
                    "pair_key": row["pair_key"],
                    "system": system,
                    "args": (row, system, api_key),
                }
            )

generation_failures = run_jobs(
    "GENERATION",
    generation_jobs,
    execute_generation,
    progress,
)

# ------------------------------------------------------------------
# Run / resume judge
# ------------------------------------------------------------------

judge_jobs = []

for row in inputs.to_dict("records"):
    for system in ("closure_aware", "binary_state"):
        gen_key = generation_job_key(row["pair_key"], system)
        judge_key = judge_job_key(row["pair_key"], system)

        generation = progress.get(gen_key)
        if generation and judge_key not in progress:
            judge_jobs.append(
                {
                    "job_key": judge_key,
                    "stage": "judge",
                    "pair_key": row["pair_key"],
                    "system": system,
                    "args": (
                        row,
                        system,
                        generation["response"],
                        api_key,
                    ),
                }
            )

judge_failures = run_jobs(
    "JUDGE",
    judge_jobs,
    execute_judge,
    progress,
)

expected_each = len(inputs) * 2

complete_generations = sum(
    generation_job_key(row["pair_key"], system) in progress
    for row in inputs.to_dict("records")
    for system in ("closure_aware", "binary_state")
)

complete_judges = sum(
    judge_job_key(row["pair_key"], system) in progress
    for row in inputs.to_dict("records")
    for system in ("closure_aware", "binary_state")
)

print(
    f"\nCompletion: generations {complete_generations}/{expected_each}; "
    f"judges {complete_judges}/{expected_each}"
)

if complete_generations != expected_each or complete_judges != expected_each:
    print(
        "\nRUN INCOMPLETE. Progress is saved. Rerun the same script; "
        "successful jobs will be reused."
    )
    raise SystemExit(2)

# ------------------------------------------------------------------
# Build response/judgment table
# ------------------------------------------------------------------

response_rows = []

for row in inputs.to_dict("records"):
    for system in ("closure_aware", "binary_state"):
        gen = progress[generation_job_key(row["pair_key"], system)]
        judge = progress[judge_job_key(row["pair_key"], system)]
        j = judge["judgment"]

        out = dict(row)
        out.update(
            {
                "system": system,
                "generation_model_returned": gen["model_returned"],
                "response": gen["response"],
                "judge_model_returned": judge["model_returned"],
                "judge_faithfulness": j["faithfulness"],
                "judge_hallucination": j["hallucination"],
                "judge_status_correct": j["status_correct"],
                "judge_specificity": j["specificity"],
                "judge_usefulness": j["usefulness"],
                "judge_empathy": j["empathy"],
                "judge_actionability": j["actionability"],
                "judge_relevant_to_review": j["relevant_to_review"],
                "judge_reasoning": j["reasoning"],
                "generation_usage_json": json.dumps(gen.get("usage", {})),
                "judge_usage_json": json.dumps(judge.get("usage", {})),
            }
        )
        response_rows.append(out)

responses = pd.DataFrame(response_rows)
responses.to_csv(RESPONSES_PATH, index=False)

# ------------------------------------------------------------------
# E2E decomposition
# ------------------------------------------------------------------

per_case = responses.copy()

per_case["known_positive_gated_status_success"] = (
    per_case["known_positive_hit_at_1"].astype(bool)
    & per_case["judge_status_correct"].astype(bool)
)

per_case["known_positive_gated_safe_success"] = (
    per_case["known_positive_hit_at_1"].astype(bool)
    & per_case["judge_status_correct"].astype(bool)
    & ~per_case["judge_hallucination"].astype(bool)
)

per_case["known_positive_gated_strict_success"] = (
    per_case["known_positive_hit_at_1"].astype(bool)
    & per_case["judge_status_correct"].astype(bool)
    & ~per_case["judge_hallucination"].astype(bool)
    & per_case["judge_relevant_to_review"].astype(bool)
)

def failure_category(row):
    if not bool(row["known_positive_hit_at_1"]):
        return "not_originally_known_positive_at_top1"
    if not bool(row["judge_status_correct"]):
        return "generation_status_wrong"
    if bool(row["judge_hallucination"]):
        return "generation_hallucination"
    if not bool(row["judge_relevant_to_review"]):
        return "generation_not_relevant_to_review"
    return "known_positive_gated_strict_success"

per_case["failure_category"] = per_case.apply(failure_category, axis=1)
per_case.to_csv(PER_CASE_PATH, index=False)

# ------------------------------------------------------------------
# Headline metrics
# ------------------------------------------------------------------

metric_rows = []

metric_rows.extend(metrics_for(per_case, "all_82_retrieved_issues"))

known_mask = per_case["known_positive_hit_at_1"].astype(bool)
metric_rows.extend(
    metrics_for(
        per_case[known_mask],
        "9_originally_known_positive_top1_hits",
    )
)

nonresolved_mask = per_case["l1_class"].isin(
    ["REJECTED", "ABANDONED", "REDIRECTED"]
)
metric_rows.extend(
    metrics_for(
        per_case[nonresolved_mask],
        "45_nonresolved_closed_retrieved_issues",
    )
)

known_nonresolved_mask = known_mask & nonresolved_mask
metric_rows.extend(
    metrics_for(
        per_case[known_nonresolved_mask],
        "4_known_positive_nonresolved_closed_top1_hits",
    )
)

headline = pd.DataFrame(metric_rows)
headline.to_csv(HEADLINE_PATH, index=False)

# ------------------------------------------------------------------
# Per-outcome module metrics
# ------------------------------------------------------------------

outcome_rows = []

for closure_class in ("OPEN", "RESOLVED", "REJECTED", "ABANDONED", "REDIRECTED"):
    subset = per_case[per_case["l1_class"] == closure_class]
    for row in metrics_for(subset, f"closure_class={closure_class}"):
        row["closure_class"] = closure_class
        outcome_rows.append(row)

outcome = pd.DataFrame(outcome_rows)
outcome.to_csv(OUTCOME_PATH, index=False)

# ------------------------------------------------------------------
# Paired exact tests
# ------------------------------------------------------------------

paired_rows = []

subsets = [
    ("all_82", pd.Series(True, index=per_case.index)),
    (
        "45_nonresolved_closed",
        per_case["l1_class"].isin(["REJECTED", "ABANDONED", "REDIRECTED"]),
    ),
    (
        "9_known_positive_top1_hits",
        per_case["known_positive_hit_at_1"].astype(bool),
    ),
    (
        "4_known_positive_nonresolved_closed_top1_hits",
        per_case["known_positive_hit_at_1"].astype(bool)
        & per_case["l1_class"].isin(["REJECTED", "ABANDONED", "REDIRECTED"]),
    ),
]

for subset_name, mask in subsets:
    for field in (
        "judge_status_correct",
        "judge_hallucination",
        "judge_relevant_to_review",
    ):
        paired_rows.append(
            paired_binary_test(
                per_case,
                field,
                mask,
                subset_name,
            )
        )

paired = pd.DataFrame(paired_rows)
paired.to_csv(PAIRED_PATH, index=False)

# ------------------------------------------------------------------
# Blinded manual audit of the 9 benchmark-known-positive hits
# ------------------------------------------------------------------

known9 = per_case[per_case["known_positive_hit_at_1"].astype(bool)].copy()

if known9["pair_key"].nunique() != 9:
    raise AssertionError(
        f"Expected 9 known-positive pair keys, got {known9['pair_key'].nunique()}"
    )

rng = random.Random(42)
blind_rows = []
key_rows = []

for pair_key, group in known9.groupby("pair_key", sort=True):
    if set(group["system"]) != {"closure_aware", "binary_state"}:
        raise AssertionError(f"Missing system for pair {pair_key}")

    base = group.iloc[0]

    mapping = ["closure_aware", "binary_state"]
    rng.shuffle(mapping)

    sys_a, sys_b = mapping
    row_a = group[group["system"] == sys_a].iloc[0]
    row_b = group[group["system"] == sys_b].iloc[0]

    audit_id = f"HARING-{len(blind_rows)+1:02d}"

    blind_rows.append(
        {
            "audit_id": audit_id,
            "app": base["app"],
            "query_id": base["query_id"],
            "review_text": base["review_text"],
            "issue_id": base["display_issue_id"],
            "issue_title": base["issue_title"],
            "issue_body_excerpt": clean(base["issue_body"])[:1200],
            "binary_state": base["binary_state"],
            "resolution_signal": base["resolution_signal"],
            "labels": base["labels"],
            "closed_at": base["closed_at"],
            "authoritative_l1_class": base["l1_class"],
            "authoritative_subtype": base["subtype"],
            "authoritative_action": base["action_l1"],
            "response_A": row_a["response"],
            "response_B": row_b["response"],
            "human_A_status_correct": "",
            "human_A_hallucination": "",
            "human_A_faithful": "",
            "human_A_relevant_to_review": "",
            "human_B_status_correct": "",
            "human_B_hallucination": "",
            "human_B_faithful": "",
            "human_B_relevant_to_review": "",
            "human_preference_A_B_TIE": "",
            "human_notes": "",
        }
    )

    key_rows.append(
        {
            "audit_id": audit_id,
            "response_A_system": sys_a,
            "response_B_system": sys_b,
            "pair_key": pair_key,
        }
    )

pd.DataFrame(blind_rows).to_csv(MANUAL_BLIND_PATH, index=False)
pd.DataFrame(key_rows).to_csv(MANUAL_KEY_PATH, index=False)

# ------------------------------------------------------------------
# Optional but publication-useful semantic relevance audit sheet:
# all 82 top-1 review/issue pairs, without generation outputs.
# This addresses Häring's original pool incompleteness if manually annotated.
# ------------------------------------------------------------------

semantic_rows = []

for row in inputs.sort_values(["app", "query_id"]).to_dict("records"):
    semantic_rows.append(
        {
            "app": row["app"],
            "query_id": row["query_id"],
            "review_text": row["review_text"],
            "retrieved_issue_id": row["display_issue_id"],
            "retrieved_issue_title": row["issue_title"],
            "retrieved_issue_body_excerpt": clean(row["issue_body"])[:1500],
            "original_haring_known_positive_issue_ids": row["known_positive_issue_ids"],
            # Intentionally omit known_positive_hit_at_1 from the annotator-facing
            # sheet to avoid anchoring the semantic relevance decision.
            "human_same_feature": "",
            "human_same_behavior_or_problem": "",
            "human_semantically_relevant": "",
            "human_notes": "",
        }
    )

pd.DataFrame(semantic_rows).to_csv(SEMANTIC_AUDIT_PATH, index=False)

# ------------------------------------------------------------------
# Usage totals + run summary
# ------------------------------------------------------------------

def usage_total(stage):
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for record in progress.values():
        if record.get("stage") != stage or record.get("ok") is not True:
            continue
        usage = record.get("usage") or {}
        for k in total:
            try:
                total[k] += int(usage.get(k) or 0)
            except Exception:
                pass

    return total


summary = {
    "created_at_utc": utc_now(),
    "status": "complete",
    "rows": 82,
    "systems": ["closure_aware", "binary_state"],
    "responses": int(len(responses)),
    "judgments": int(len(responses)),
    "retriever": "frozen BGE-FT epoch 2",
    "known_positive_hit_at_1": 9,
    "known_positive_hit_at_1_rate": 9 / 82,
    "benchmark_caveat": (
        "Häring judgments are pool-incomplete; 9/82 is a known-positive "
        "full-corpus rank diagnostic, not a complete semantic Hit@1 estimate."
    ),
    "closure_distribution": class_counts,
    "generation_model_requested": OPENAI_MODEL,
    "generation_models_returned": sorted(
        set(responses["generation_model_returned"].astype(str))
    ),
    "judge_model_requested": OPENAI_MODEL,
    "judge_models_returned": sorted(
        set(responses["judge_model_returned"].astype(str))
    ),
    "generation_temperature": GENERATION_TEMPERATURE,
    "judge_temperature": JUDGE_TEMPERATURE,
    "generation_usage": usage_total("generation"),
    "judge_usage": usage_total("judge"),
    "outputs": {
        "responses": str(RESPONSES_PATH),
        "per_case": str(PER_CASE_PATH),
        "headline": str(HEADLINE_PATH),
        "outcomes": str(OUTCOME_PATH),
        "paired_tests": str(PAIRED_PATH),
        "manual_audit_9_blinded": str(MANUAL_BLIND_PATH),
        "manual_audit_9_key": str(MANUAL_KEY_PATH),
        "semantic_top1_audit_82": str(SEMANTIC_AUDIT_PATH),
        "prompts": str(PROMPTS_PATH),
    },
}

SUMMARY_PATH.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

# ------------------------------------------------------------------
# Print compact results
# ------------------------------------------------------------------

print("\n" + "=" * 110)
print("HÄRING BGE-FT FROZEN END-TO-END RUN COMPLETE")
print("=" * 110)
print("Cases: 82")
print("Responses: 164")
print("Judgments: 164")
print("Original Häring known-positive Hit@1: 9/82")
print(
    "NOTE: the other 73 are UNJUDGED/NOT-KNOWN-POSITIVE at top-1, "
    "not automatically semantically wrong."
)

cols = [
    "subset",
    "system",
    "n",
    "status_correct_rate",
    "hallucination_rate",
    "relevant_to_review_rate",
    "mean_faithfulness",
    "known_positive_gated_safe_success_rate",
    "known_positive_gated_strict_success_rate",
]

print("\nHEADLINE METRICS")
print(headline[cols].to_string(index=False))

print("\nPAIRED EXACT TESTS")
print(paired.to_string(index=False))

print("\nSaved:")
for path in (
    RESPONSES_PATH,
    PER_CASE_PATH,
    HEADLINE_PATH,
    OUTCOME_PATH,
    PAIRED_PATH,
    MANUAL_BLIND_PATH,
    MANUAL_KEY_PATH,
    SEMANTIC_AUDIT_PATH,
    PROMPTS_PATH,
    SUMMARY_PATH,
):
    print(" ", path)

print(
    "\nNEXT: send headline_metrics.csv + paired_tests.csv. "
    "Then we interpret the E2E result before doing any additional experiment."
)
