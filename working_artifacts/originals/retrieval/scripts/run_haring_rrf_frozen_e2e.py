#!/usr/bin/env python3
"""
LOCAL frozen RRF60 to closure-aware Häring end-to-end run.

Input is the downloaded RRF top-1 manifest ZIP or CSV in the user's Downloads
directory. The script resolves tracker closure metadata, runs the same
closure-aware generation/judge protocol as the earlier BGE-FT E2E experiment,
and computes known-positive-gated end-to-end success. If the old BGE-FT E2E
results are present, it also performs a paired strict-success comparison.
"""


from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from datetime import datetime, timezone
import ast
import getpass
import hashlib
import json
import math
import os
import re
import time
import zipfile

import numpy as np
import pandas as pd
import requests

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing package. Install once:\n"
        "  python -m pip install -U openai pandas numpy requests\n"
    ) from exc


# ------------------------------------------------------------------
# Frozen configuration
# ------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o-mini"
GENERATION_TEMPERATURE = 0
JUDGE_TEMPERATURE = 0
API_WORKERS = 3
API_MAX_ATTEMPTS = 5

GEN_PROMPT_VERSION = "haring-rrf60-e2e-generation-v1-2026-08-08"
JUDGE_PROMPT_VERSION = "haring-rrf60-e2e-judge-v1-2026-08-08"

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")

ZIP_PATH = DOWNLOADS / "haring_rrf_top1_e2e_manifest.zip"
CSV_PATH = DOWNLOADS / "rrf_top1_manifest_82.csv"

OUT = DOWNLOADS / "haring_rrf_e2e_generation_20260808"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS_PATH = OUT / "api_progress.jsonl"
CLOSURE_MANIFEST_PATH = OUT / "rrf_top1_manifest_82_CLOSURE_RESOLVED.csv"
CLOSURE_AUDIT_PATH = OUT / "closure_mapping_audit.csv"
RESPONSES_PATH = OUT / "rrf_closure_aware_responses_and_judgments.csv"
PER_CASE_PATH = OUT / "rrf_closure_aware_per_case_e2e.csv"
METRICS_PATH = OUT / "rrf_closure_aware_metrics.csv"
KNOWN16_PATH = OUT / "rrf_known_positive_top1_16.csv"
BGE_COMPARE_PATH = OUT / "rrf_vs_bge_ft_e2e_comparison.csv"
PROTOCOL_PATH = OUT / "prompts_and_protocol.json"
SUMMARY_PATH = OUT / "run_summary.json"

OLD_BGE_RESULTS = (
    DOWNLOADS
    / "haring_e2e_generation_20260808"
    / "responses_and_judgments.csv"
)

GITHUB_REPO = "nextcloud/android"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

RAW_DIR = OUT / "nextcloud_api_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

thread_local = local()


# ------------------------------------------------------------------
# Generic helpers
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


def norm_id(x):
    s = clean(x)
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


def as_bool(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return clean(x).lower() in {"true", "1", "yes", "y"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_time(x):
    s = clean(x)
    if not s:
        return ""
    try:
        return pd.to_datetime(s, utc=True).isoformat()
    except Exception:
        return s


def parse_labels(value):
    s = clean(value)
    if not s:
        return []

    if not s.startswith("[") and ";" in s:
        return [x.strip() for x in s.split(";") if x.strip()]

    if not s.startswith("["):
        return [s]

    for parser in (ast.literal_eval, json.loads):
        try:
            obj = parser(s)
            if isinstance(obj, list):
                out = []
                for item in obj:
                    if isinstance(item, dict) and clean(item.get("name")):
                        out.append(clean(item["name"]))
                    elif isinstance(item, str) and clean(item):
                        out.append(clean(item))
                return out
        except Exception:
            pass

    return re.findall(
        r"""['"]name['"]\s*:\s*['"]([^'"]+)['"]""",
        s,
    )


def pair_key_for(row):
    material = "\n".join(
        [
            clean(row.get("app")),
            clean(row.get("query_id")),
            norm_id(row.get("rrf_top1_issue_id")),
            clean(row.get("review_text")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def repository_label(app):
    if app == "Firefox":
        return "Mozilla Firefox (Bugzilla)"
    if app == "VLC":
        return "VLC Android (Trac)"
    if app == "Nextcloud":
        return "nextcloud/android (GitHub)"
    return app


def normalized_binary_state(app, raw_status):
    raw = clean(raw_status).lower()

    if app == "Firefox":
        up = raw.upper()
        if up in {"RESOLVED", "VERIFIED"}:
            return "closed"
        if up in {"NEW", "REOPENED", "UNCONFIRMED", "ASSIGNED"}:
            return "open"

    if app == "VLC":
        if raw == "closed":
            return "closed"
        if raw in {"new", "reopened", "assigned"}:
            return "open"

    if app == "Nextcloud":
        if raw in {"open", "closed"}:
            return raw

    raise ValueError(f"Cannot normalize binary state: app={app}, status={raw_status!r}")


# ------------------------------------------------------------------
# Load RRF top1 manifest
# ------------------------------------------------------------------

if CSV_PATH.exists():
    src = pd.read_csv(CSV_PATH, low_memory=False)
elif ZIP_PATH.exists():
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        target = next(
            (n for n in zf.namelist() if n.endswith("rrf_top1_manifest_82.csv")),
            None,
        )
        if target is None:
            raise FileNotFoundError("rrf_top1_manifest_82.csv not found inside ZIP")
        with zf.open(target) as f:
            src = pd.read_csv(f, low_memory=False)
else:
    raise FileNotFoundError(
        "Missing haring_rrf_top1_e2e_manifest.zip or rrf_top1_manifest_82.csv "
        "from Downloads."
    )

if len(src) != 82:
    raise AssertionError(f"Expected 82 rows, got {len(src)}")

app_counts = src.groupby("app").size().astype(int).to_dict()
if app_counts != {"Firefox": 28, "Nextcloud": 33, "VLC": 21}:
    raise AssertionError(f"Unexpected app counts: {app_counts}")

if int(src["known_positive_hit_at_1"].map(as_bool).sum()) != 16:
    raise AssertionError(
        "RRF retrieval invariant failed: expected 16 known-positive top-1 hits."
    )

if set(src["retrieval_model"].astype(str)) != {"RRF60-BGE-ZS+BM25-TITLE"}:
    raise AssertionError("Unexpected retrieval model in manifest")

if set(src["retrieval_document_representation"].astype(str)) != {"issue_title_only"}:
    raise AssertionError("Unexpected retrieval document representation")


# ------------------------------------------------------------------
# Closure taxonomy mapping
# ------------------------------------------------------------------

REJECTED_PATTERNS = (
    "wontfix", "won't-fix", "won't fix", "wont fix", "wont-fix",
    "by-design", "by design", "invalid", "not-a-bug", "not a bug",
    "not planned", "not-planned",
)

STALE_PATTERNS = (
    "stale", "auto-closed", "auto closed", "inactive",
)

NEEDS_INFO_PATTERNS = (
    "needs author reply", "needs-info", "needs info", "more info",
    "needs reproduction", "needs repro", "can't reproduce",
    "cannot reproduce", "cant reproduce", "unable to reproduce",
    "unconfirmed",
)

UPSTREAM_PATTERNS = (
    "upstream", "third-party", "third party",
)


def parse_structured(value):
    s = clean(value)
    if not s:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(s)
        except Exception:
            pass
    return None


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from iter_dicts(item)


def firefox_resolution_from_history(history_value):
    obj = parse_structured(history_value)
    if obj is None:
        return "", "history_parse_failed_or_empty"

    current = None
    seen = []

    for d in iter_dicts(obj):
        field = clean(
            d.get("field_name", d.get("field", d.get("name", "")))
        ).lower()

        if field == "resolution":
            added = clean(
                d.get(
                    "added",
                    d.get(
                        "new",
                        d.get("new_value", d.get("to", d.get("value", ""))),
                    ),
                )
            ).upper()
            removed = clean(
                d.get(
                    "removed",
                    d.get("old", d.get("old_value", d.get("from", ""))),
                )
            ).upper()

            current = added
            seen.append({"removed": removed, "added": added})

    if current is None:
        direct = []
        for d in iter_dicts(obj):
            for key, value in d.items():
                if clean(key).lower() == "resolution":
                    val = clean(value).upper()
                    if val and not isinstance(value, (dict, list, tuple)):
                        direct.append(val)
        if direct:
            current = direct[-1]
            seen.append({"direct": current})

    return clean(current), json.dumps(seen, ensure_ascii=False)


def map_firefox(status, history_value):
    st = clean(status).upper()

    if st in {"NEW", "REOPENED", "UNCONFIRMED", "ASSIGNED"}:
        return (
            "OPEN", "OPEN", "KNOWN_ISSUE",
            f"Bugzilla status={st}",
            "local_bugzilla_status",
        )

    if st not in {"RESOLVED", "VERIFIED"}:
        return (
            "OPEN", "OPEN", "KNOWN_ISSUE",
            f"Bugzilla non-closed status={st or '<missing>'}",
            "conservative_open_status",
        )

    resolution, trace = firefox_resolution_from_history(history_value)

    if resolution == "FIXED":
        return "RESOLVED", "fixed", "RESOLVED", "Bugzilla resolution=FIXED", trace

    if resolution in {"DUPLICATE", "MOVED"}:
        return (
            "REDIRECTED",
            "duplicate" if resolution == "DUPLICATE" else "moved",
            "REDIRECTED",
            f"Bugzilla resolution={resolution}",
            trace,
        )

    if resolution in {"WONTFIX", "INVALID"}:
        return (
            "REJECTED",
            resolution.lower(),
            "REJECTED",
            f"Bugzilla resolution={resolution}",
            trace,
        )

    if resolution in {"INCOMPLETE", "WORKSFORME"}:
        return (
            "ABANDONED",
            "NEEDS_INFO",
            "ABANDONED_NEEDS_INFO",
            f"Bugzilla resolution={resolution}",
            trace,
        )

    if resolution in {"EXPIRED", "INACTIVE"}:
        return (
            "ABANDONED",
            "STALE",
            "ABANDONED",
            f"Bugzilla resolution={resolution}",
            trace,
        )

    if resolution in {"LATER", "REMIND"}:
        return (
            "ABANDONED",
            "OTHER",
            "ABANDONED",
            f"Bugzilla resolution={resolution}",
            trace,
        )

    # Existing paper-aligned conservative fallback:
    # closed but no confirmed resolution -> ABANDONED/OTHER.
    return (
        "ABANDONED",
        "OTHER",
        "ABANDONED",
        f"Bugzilla closed without classifiable confirmed resolution; "
        f"resolution={resolution or '<missing>'}",
        trace,
    )


def map_vlc(status, resolution):
    st = clean(status).lower()
    res = clean(resolution).lower()

    if st in {"new", "reopened", "assigned"}:
        return "OPEN", "OPEN", "KNOWN_ISSUE", f"Trac status={st}", "local_trac_status"

    if st != "closed":
        return (
            "OPEN", "OPEN", "KNOWN_ISSUE",
            f"Trac non-closed status={st or '<missing>'}",
            "conservative_open_status",
        )

    if res == "fixed":
        return "RESOLVED", "fixed", "RESOLVED", "Trac resolution=fixed", "local_trac_resolution"

    if res == "duplicate":
        return "REDIRECTED", "duplicate", "REDIRECTED", "Trac resolution=duplicate", "local_trac_resolution"

    if res in {"wontfix", "invalid", "notvlc"}:
        return "REJECTED", res, "REJECTED", f"Trac resolution={res}", "local_trac_resolution"

    if res in {"incomplete", "worksforme"}:
        return (
            "ABANDONED",
            "NEEDS_INFO",
            "ABANDONED_NEEDS_INFO",
            f"Trac resolution={res}",
            "local_trac_resolution",
        )

    return (
        "ABANDONED",
        "OTHER",
        "ABANDONED",
        f"Trac closed without classifiable confirmed resolution; "
        f"resolution={res or '<missing>'}",
        "conservative_closed_fallback",
    )


def classify_specific_github_labels(labels):
    labels_lower = [
        re.sub(r"\s+", " ", clean(x).lower())
        for x in labels
        if clean(x)
    ]

    if any("duplicate" in label for label in labels_lower):
        return "REDIRECTED", "duplicate", "REDIRECTED", "duplicate label"

    for label in labels_lower:
        if any(pattern in label for pattern in REJECTED_PATTERNS):
            return "REJECTED", "wontfix", "REJECTED", f"rejection label={label}"

    for label in labels_lower:
        if any(pattern in label for pattern in STALE_PATTERNS):
            return "ABANDONED", "STALE", "ABANDONED", f"stale label={label}"

    for label in labels_lower:
        if any(pattern in label for pattern in NEEDS_INFO_PATTERNS):
            return (
                "ABANDONED",
                "NEEDS_INFO",
                "ABANDONED_NEEDS_INFO",
                f"needs-info/cannot-reproduce label={label}",
            )

    for label in labels_lower:
        if any(pattern in label for pattern in UPSTREAM_PATTERNS):
            return (
                "ABANDONED",
                "UPSTREAM",
                "ABANDONED_UPSTREAM",
                f"upstream label={label}",
            )

    return None


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "haring-rrf-e2e-closure-audit",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def fetch_github_issue(issue_number):
    cache = RAW_DIR / f"issue_{issue_number}.json"

    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), "cache"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}"
    response = requests.get(
        url,
        headers=github_headers(),
        timeout=45,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API {response.status_code} for #{issue_number}; "
            f"remaining={response.headers.get('X-RateLimit-Remaining')}; "
            f"body={response.text[:200]!r}"
        )

    payload = response.json()
    cache.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload, "github_rest_api"


def map_nextcloud(row):
    state = clean(row.get("status")).lower()
    labels = parse_labels(row.get("labels"))

    if state == "open":
        return (
            "OPEN", "OPEN", "KNOWN_ISSUE",
            "GitHub snapshot state=open",
            "local_github_snapshot",
            "",
        )

    if state != "closed":
        return (
            "OPEN", "OPEN", "KNOWN_ISSUE",
            f"GitHub snapshot non-closed state={state or '<missing>'}",
            "conservative_open_status",
            "",
        )

    # Historical labels are safe to use and have priority.
    specific = classify_specific_github_labels(labels)
    if specific is not None:
        l1, subtype, action, signal = specific
        return (
            l1, subtype, action, signal,
            "local_historical_labels",
            "",
        )

    issue_number = norm_id(row.get("issue_number"))
    if not issue_number:
        m = re.search(r"/issues/(\d+)(?:$|[/?#])", clean(row.get("issue_url")))
        if m:
            issue_number = m.group(1)

    if not issue_number:
        return (
            "ABANDONED", "OTHER", "ABANDONED",
            "Historical snapshot closed; no issue number available for "
            "temporally safe state_reason enrichment.",
            "conservative_closed_fallback",
            "",
        )

    try:
        payload, source = fetch_github_issue(issue_number)
    except Exception as exc:
        return (
            "ABANDONED", "OTHER", "ABANDONED",
            f"Historical snapshot closed; GitHub enrichment unavailable ({exc}); "
            "no confirmed resolution in historical evidence.",
            "conservative_closed_fallback_api_failure",
            issue_number,
        )

    current_state = clean(payload.get("state")).lower()
    current_reason = clean(payload.get("state_reason")).lower().replace("-", "_")
    current_closed_at = clean(payload.get("closed_at"))
    local_closed_at = clean(row.get("closed_at"))

    temporal_match = (
        current_state == "closed"
        and bool(local_closed_at)
        and normalize_time(current_closed_at) == normalize_time(local_closed_at)
    )

    if temporal_match:
        if current_reason == "duplicate":
            return (
                "REDIRECTED", "duplicate", "REDIRECTED",
                "state_reason=duplicate",
                f"{source}_temporally_matched",
                issue_number,
            )
        if current_reason == "not_planned":
            return (
                "REJECTED", "not_planned", "REJECTED",
                "state_reason=not_planned",
                f"{source}_temporally_matched",
                issue_number,
            )
        if current_reason == "completed":
            return (
                "RESOLVED", "fixed", "RESOLVED",
                "state_reason=completed",
                f"{source}_temporally_matched",
                issue_number,
            )

    # Same conservative historical rule used in the prior final manifest:
    # do not project a later/current GitHub closure backward.
    return (
        "ABANDONED",
        "OTHER",
        "ABANDONED",
        (
            "Historical snapshot is closed but no temporally safe confirmed "
            f"resolution is available; current_state={current_state or '<missing>'}; "
            f"current_reason={current_reason or '<missing>'}; "
            f"snapshot_closed_at={local_closed_at or '<missing>'}; "
            f"current_closed_at={current_closed_at or '<missing>'}"
        ),
        "conservative_historical_closed_fallback",
        issue_number,
    )


# ------------------------------------------------------------------
# Resolve every RRF top1 issue
# ------------------------------------------------------------------

resolved_rows = []
audit_rows = []

for raw in src.to_dict("records"):
    app_name = clean(raw.get("app"))

    if app_name == "Firefox":
        l1, subtype, action, evidence, source = map_firefox(
            raw.get("status"),
            raw.get("history"),
        )
        display_issue_id = norm_id(raw.get("rrf_top1_issue_id"))

    elif app_name == "VLC":
        l1, subtype, action, evidence, source = map_vlc(
            raw.get("status"),
            raw.get("resolution"),
        )
        display_issue_id = norm_id(raw.get("rrf_top1_issue_id"))

    elif app_name == "Nextcloud":
        l1, subtype, action, evidence, source, issue_number = map_nextcloud(raw)
        display_issue_id = issue_number or norm_id(raw.get("rrf_top1_issue_id"))

    else:
        raise AssertionError(f"Unexpected app: {app_name}")

    row = dict(raw)
    row.update(
        {
            "closure_class": l1,
            "closure_subtype": subtype,
            "closure_action": action,
            "closure_evidence": evidence,
            "closure_mapping_source": source,
            "display_issue_id": display_issue_id,
        }
    )
    resolved_rows.append(row)

    audit_rows.append(
        {
            "app": app_name,
            "query_id": norm_id(raw.get("query_id")),
            "rrf_top1_issue_id": norm_id(raw.get("rrf_top1_issue_id")),
            "display_issue_id": display_issue_id,
            "known_positive_hit_at_1": as_bool(raw.get("known_positive_hit_at_1")),
            "closure_class": l1,
            "closure_subtype": subtype,
            "closure_action": action,
            "closure_mapping_source": source,
            "closure_evidence": evidence,
        }
    )

resolved = pd.DataFrame(resolved_rows)
audit = pd.DataFrame(audit_rows)

if len(resolved) != 82:
    raise AssertionError("Closure manifest no longer has 82 rows")

if resolved["closure_class"].isin(["", "UNRESOLVED"]).any():
    raise AssertionError("Unexpected unresolved closure case")

if int(resolved["known_positive_hit_at_1"].map(as_bool).sum()) != 16:
    raise AssertionError("Retrieval invariant changed during closure mapping")

resolved.to_csv(CLOSURE_MANIFEST_PATH, index=False)
audit.to_csv(CLOSURE_AUDIT_PATH, index=False)


# ------------------------------------------------------------------
# Same closure-aware generation protocol as previous E2E
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

GENERATION_SYSTEM = """You are a developer-support assistant.
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


def historical_closed_at(row):
    app_name = clean(row.get("app"))
    if app_name == "Firefox":
        return clean(row.get("cf_last_resolved"))
    if app_name == "Nextcloud":
        return clean(row.get("closed_at"))
    return ""


def generation_row(raw):
    app_name = clean(raw.get("app"))
    return {
        "pair_key": pair_key_for(raw),
        "app": app_name,
        "query_id": norm_id(raw.get("query_id")),
        "review_text": clean(raw.get("review_text")),
        "known_positive_issue_ids": clean(raw.get("known_positive_issue_ids")),
        "known_positive_hit_at_1": as_bool(raw.get("known_positive_hit_at_1")),
        "retrieved_corpus_issue_id": norm_id(raw.get("rrf_top1_issue_id")),
        "display_issue_id": clean(raw.get("display_issue_id")),
        "repository": repository_label(app_name),
        "issue_title": clean(raw.get("issue_title")),
        "issue_body": clean(raw.get("issue_body")),
        "binary_state": normalized_binary_state(app_name, raw.get("status")),
        "issue_url": clean(raw.get("issue_url")),
        "resolution_signal": clean(raw.get("closure_evidence")),
        "labels": clean(raw.get("labels")),
        "closed_at": historical_closed_at(raw),
        "l1_class": clean(raw.get("closure_class")),
        "subtype": clean(raw.get("closure_subtype")),
        "action_l1": clean(raw.get("closure_action")),
        "closure_mapping_source": clean(raw.get("closure_mapping_source")),
        "closure_evidence": clean(raw.get("closure_evidence")),
        "rrf_top1_score": raw.get("rrf_top1_score"),
        "bge_rank_of_rrf_top1": raw.get("bge_rank_of_rrf_top1"),
        "bm25_rank_of_rrf_top1": raw.get("bm25_rank_of_rrf_top1"),
    }


inputs = pd.DataFrame(
    [generation_row(r) for r in resolved.to_dict("records")]
)

if inputs["pair_key"].duplicated().any():
    raise AssertionError("Duplicate pair_key")

if int(inputs["known_positive_hit_at_1"].astype(bool).sum()) != 16:
    raise AssertionError("Expected 16 RRF known-positive top1 hits")


def generation_user_prompt(row):
    labels = ", ".join(parse_labels(row.get("labels"))) or "none"
    action = clean(row.get("action_l1"))

    if action not in ACTION_INSTRUCTIONS:
        raise KeyError(f"Unknown action_l1={action!r}")

    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

RETRIEVED ISSUE:
- Tracker: {clean(row.get('repository'))}
- Issue #{clean(row.get('display_issue_id'))}: {clean(row.get('issue_title'))}
- Binary state: {clean(row.get('binary_state'))}
- URL: {clean(row.get('issue_url')) or 'not supplied'}
- Issue body excerpt: {clean(row.get('issue_body'))[:1200]}

AUTHORITATIVE CLOSURE METADATA:
- resolution_signal: {clean(row.get('resolution_signal')) or 'none'}
- labels: {labels}
- closed_at: {clean(row.get('closed_at')) or 'not supplied'}
- l1_class: {clean(row.get('l1_class'))}
- subtype: {clean(row.get('subtype'))}
- action_l1: {action}

ACTION-SPECIFIC GUIDANCE:
{ACTION_INSTRUCTIONS[action]}

Write the closure-reason-aware response."""


def judge_user_prompt(row, response_text):
    labels = ", ".join(parse_labels(row.get("labels"))) or "none"

    return f"""REAL USER REVIEW:
{clean(row.get('review_text'))}

GENERATED SYSTEM:
closure_aware

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
                raise RuntimeError("API returned an empty response")

            usage = {}
            if getattr(response, "usage", None) is not None and hasattr(response.usage, "model_dump"):
                usage = response.usage.model_dump()

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
        f"OpenAI call failed after {API_MAX_ATTEMPTS}: {last_error}"
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
            raise ValueError("Judge output did not contain JSON")
        obj = json.loads(m.group(0))

    if not isinstance(obj, dict):
        raise ValueError("Judge output was not an object")

    return obj


def strict_bool(value, field):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{field} is not boolean: {value!r}")


def strict_score(value, field):
    x = float(value)
    if not math.isfinite(x) or not (0.0 <= x <= 1.0):
        raise ValueError(f"{field} outside [0,1]: {value!r}")
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
            f"Judge schema mismatch: expected {sorted(exact_fields)}, "
            f"got {sorted(raw.keys())}"
        )

    return {
        "faithfulness": strict_score(raw["faithfulness"], "faithfulness"),
        "hallucination": strict_bool(raw["hallucination"], "hallucination"),
        "status_correct": strict_bool(raw["status_correct"], "status_correct"),
        "specificity": strict_score(raw["specificity"], "specificity"),
        "usefulness": strict_score(raw["usefulness"], "usefulness"),
        "empathy": strict_score(raw["empathy"], "empathy"),
        "actionability": strict_score(raw["actionability"], "actionability"),
        "relevant_to_review": strict_bool(
            raw["relevant_to_review"],
            "relevant_to_review",
        ),
        "reasoning": clean(raw["reasoning"]),
    }


def generation_job_key(pair_key):
    return f"generation::{GEN_PROMPT_VERSION}::{OPENAI_MODEL}::closure_aware::{pair_key}"


def judge_job_key(pair_key):
    return f"judge::{JUDGE_PROMPT_VERSION}::{OPENAI_MODEL}::closure_aware::{pair_key}"


def load_progress():
    progress = {}

    if not PROGRESS_PATH.exists():
        return progress

    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("ok") is True and rec.get("job_key"):
                progress[rec["job_key"]] = rec

    return progress


def append_progress(record):
    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def execute_generation(row, api_key):
    result = call_openai(
        api_key,
        GENERATION_SYSTEM,
        generation_user_prompt(row),
        max_tokens=220,
        temperature=GENERATION_TEMPERATURE,
        json_mode=False,
    )

    return {
        "job_key": generation_job_key(row["pair_key"]),
        "stage": "generation",
        "ok": True,
        "pair_key": row["pair_key"],
        "model_returned": result["model_returned"],
        "response": result["content"],
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def execute_judge(row, response_text, api_key):
    result = call_openai(
        api_key,
        JUDGE_SYSTEM,
        judge_user_prompt(row, response_text),
        max_tokens=300,
        temperature=JUDGE_TEMPERATURE,
        json_mode=True,
    )

    judgment = validate_judgment(parse_json_object(result["content"]))

    return {
        "job_key": judge_job_key(row["pair_key"]),
        "stage": "judge",
        "ok": True,
        "pair_key": row["pair_key"],
        "model_returned": result["model_returned"],
        "judgment": judgment,
        "usage": result["usage"],
        "completed_at_utc": utc_now(),
    }


def run_parallel(label, jobs, fn, progress):
    if not jobs:
        print(f"{label}: already complete")
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
                append_progress(rec)
            except Exception as exc:
                fail = {
                    "ok": False,
                    "job_key": meta["job_key"],
                    "stage": meta["stage"],
                    "pair_key": meta["pair_key"],
                    "error": str(exc),
                    "completed_at_utc": utc_now(),
                }
                append_progress(fail)
                failures.append(fail)
                print("FAILED:", fail, flush=True)

            if done % 20 == 0 or done == len(jobs):
                print(
                    f"  {done}/{len(jobs)}; failures={len(failures)}",
                    flush=True,
                )


# Save protocol BEFORE calls.
PROTOCOL_PATH.write_text(
    json.dumps(
        {
            "created_at_utc": utc_now(),
            "retriever": "RRF60-BGE-ZS+BM25-TITLE",
            "rrf_k": 60,
            "retrieval_document_representation": "title-only",
            "generation_evidence_after_retrieval": (
                "full retrieved issue title/body + tracker metadata; "
                "title-only restriction applies to retrieval indexing, not generation."
            ),
            "retrieval_scope": (
                "82 real Häring reviews with >=1 original human-judged positive; "
                "top1 ranked against each app full tracker corpus"
            ),
            "known_positive_hit_at_1": 16,
            "benchmark_note": (
                "Original Häring judgments are pool-incomplete. "
                "known_positive_hit_at_1=False does not prove semantic irrelevance."
            ),
            "generation_system": "closure_aware only",
            "model_requested": OPENAI_MODEL,
            "generation_temperature": GENERATION_TEMPERATURE,
            "judge_temperature": JUDGE_TEMPERATURE,
            "generation_prompt_version": GEN_PROMPT_VERSION,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "generation_system_prompt": GENERATION_SYSTEM,
            "judge_system_prompt": JUDGE_SYSTEM,
            "action_instructions": ACTION_INSTRUCTIONS,
            "closure_mapping_note": (
                "Firefox uses local Bugzilla status/history; VLC uses local Trac "
                "status/resolution; Nextcloud uses historical labels and temporally "
                "matched GitHub state_reason when safe. Historical closed cases with "
                "no confirmed resolution use conservative ABANDONED/OTHER fallback."
            ),
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)


# ------------------------------------------------------------------
# Run generation + judge
# ------------------------------------------------------------------

api_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not api_key:
    api_key = getpass.getpass(
        "OPENAI_API_KEY not found. Paste key here (hidden): "
    ).strip()

if not api_key:
    raise SystemExit("No OpenAI API key supplied")

progress = load_progress()

gen_jobs = []
for row in inputs.to_dict("records"):
    key = generation_job_key(row["pair_key"])
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

run_parallel("RRF CLOSURE-AWARE GENERATION", gen_jobs, execute_generation, progress)

judge_jobs = []
for row in inputs.to_dict("records"):
    gk = generation_job_key(row["pair_key"])
    jk = judge_job_key(row["pair_key"])

    if gk in progress and jk not in progress:
        judge_jobs.append(
            (
                (row, progress[gk]["response"], api_key),
                {
                    "job_key": jk,
                    "stage": "judge",
                    "pair_key": row["pair_key"],
                },
            )
        )

run_parallel("RRF CLOSURE-AWARE JUDGE", judge_jobs, execute_judge, progress)

complete_gen = sum(
    generation_job_key(pk) in progress
    for pk in inputs["pair_key"]
)
complete_judge = sum(
    judge_job_key(pk) in progress
    for pk in inputs["pair_key"]
)

print(
    f"\nCompletion: generation {complete_gen}/82; judge {complete_judge}/82"
)

if complete_gen != 82 or complete_judge != 82:
    print("Incomplete. Rerun same script; completed jobs will be reused.")
    raise SystemExit(2)


# ------------------------------------------------------------------
# Build outputs
# ------------------------------------------------------------------

rows = []

for row in inputs.to_dict("records"):
    gen = progress[generation_job_key(row["pair_key"])]
    judge = progress[judge_job_key(row["pair_key"])]
    j = judge["judgment"]

    out = dict(row)
    out.update(
        {
            "system": "closure_aware",
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
        }
    )
    rows.append(out)

responses = pd.DataFrame(rows)

responses["known_positive_gated_status_success"] = (
    responses["known_positive_hit_at_1"].astype(bool)
    & responses["judge_status_correct"].astype(bool)
)

responses["known_positive_gated_safe_success"] = (
    responses["known_positive_hit_at_1"].astype(bool)
    & responses["judge_status_correct"].astype(bool)
    & ~responses["judge_hallucination"].astype(bool)
)

responses["known_positive_gated_strict_success"] = (
    responses["known_positive_hit_at_1"].astype(bool)
    & responses["judge_status_correct"].astype(bool)
    & ~responses["judge_hallucination"].astype(bool)
    & responses["judge_relevant_to_review"].astype(bool)
)

responses.to_csv(RESPONSES_PATH, index=False)
responses.to_csv(PER_CASE_PATH, index=False)

known16 = responses[
    responses["known_positive_hit_at_1"].astype(bool)
].copy()

if len(known16) != 16:
    raise AssertionError(f"Expected 16 known-positive top1 rows, got {len(known16)}")

known16.to_csv(KNOWN16_PATH, index=False)


def metric_row(df, subset):
    return {
        "subset": subset,
        "n": int(len(df)),
        "status_correct_rate": float(df["judge_status_correct"].astype(bool).mean()),
        "hallucination_rate": float(df["judge_hallucination"].astype(bool).mean()),
        "relevant_to_review_rate": float(df["judge_relevant_to_review"].astype(bool).mean()),
        "mean_faithfulness": float(df["judge_faithfulness"].astype(float).mean()),
        "mean_specificity": float(df["judge_specificity"].astype(float).mean()),
        "mean_usefulness": float(df["judge_usefulness"].astype(float).mean()),
        "mean_empathy": float(df["judge_empathy"].astype(float).mean()),
        "mean_actionability": float(df["judge_actionability"].astype(float).mean()),
        "known_positive_gated_status_success_rate": float(
            df["known_positive_gated_status_success"].astype(bool).mean()
        ),
        "known_positive_gated_safe_success_rate": float(
            df["known_positive_gated_safe_success"].astype(bool).mean()
        ),
        "known_positive_gated_strict_success_rate": float(
            df["known_positive_gated_strict_success"].astype(bool).mean()
        ),
    }


metrics = pd.DataFrame(
    [
        metric_row(responses, "all_82_rrf_top1"),
        metric_row(known16, "16_originally_known_positive_rrf_top1_hits"),
    ]
)

nonresolved = responses[
    responses["l1_class"].isin(
        ["REJECTED", "ABANDONED", "REDIRECTED"]
    )
]
if len(nonresolved):
    metrics = pd.concat(
        [
            metrics,
            pd.DataFrame(
                [metric_row(nonresolved, "nonresolved_closed_rrf_top1")]
            ),
        ],
        ignore_index=True,
    )

metrics.to_csv(METRICS_PATH, index=False)


# ------------------------------------------------------------------
# Optional direct RRF-vs-old-BGE E2E strict-success comparison
# ------------------------------------------------------------------

def exact_mcnemar_p(a_only, b_only):
    n = int(a_only + b_only)
    if n == 0:
        return 1.0
    k = min(int(a_only), int(b_only))
    lower = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * lower)


comparison = None

if OLD_BGE_RESULTS.exists():
    old = pd.read_csv(OLD_BGE_RESULTS, low_memory=False)
    old = old[old["system"].astype(str) == "closure_aware"].copy()

    if len(old) == 82:
        old["app"] = old["app"].astype(str)
        old["query_id"] = old["query_id"].map(norm_id)

        old["old_strict"] = (
            old["known_positive_hit_at_1"].map(as_bool)
            & old["judge_status_correct"].map(as_bool)
            & ~old["judge_hallucination"].map(as_bool)
            & old["judge_relevant_to_review"].map(as_bool)
        )

        new = responses[
            ["app", "query_id", "known_positive_gated_strict_success"]
        ].copy()
        new["query_id"] = new["query_id"].map(norm_id)

        paired = old[
            ["app", "query_id", "old_strict"]
        ].merge(
            new,
            on=["app", "query_id"],
            how="inner",
            validate="one_to_one",
        )

        if len(paired) != 82:
            raise AssertionError(
                f"Old-vs-new E2E comparison merged {len(paired)} rows, expected 82"
            )

        old_s = paired["old_strict"].astype(bool)
        new_s = paired["known_positive_gated_strict_success"].astype(bool)

        new_only = int((new_s & ~old_s).sum())
        old_only = int((~new_s & old_s).sum())

        comparison = pd.DataFrame(
            [
                {
                    "comparison": "RRF60_closure_aware_vs_BGE-FT_closure_aware",
                    "pairs": 82,
                    "old_bge_ft_strict_successes": int(old_s.sum()),
                    "new_rrf_strict_successes": int(new_s.sum()),
                    "rrf_only_successes": new_only,
                    "bge_ft_only_successes": old_only,
                    "exact_mcnemar_p": exact_mcnemar_p(new_only, old_only),
                    "interpretation": (
                        "Known-positive-gated strict success; incomplete Häring "
                        "labels mean this is a conservative benchmark-gated E2E diagnostic."
                    ),
                }
            ]
        )

        comparison.to_csv(BGE_COMPARE_PATH, index=False)


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

summary = {
    "created_at_utc": utc_now(),
    "status": "complete",
    "rows": 82,
    "retriever": "RRF60-BGE-ZS+BM25-TITLE",
    "retrieval_document_representation": "title-only",
    "known_positive_hit_at_1": 16,
    "known_positive_hit_at_1_rate": 16 / 82,
    "generation_system": "closure_aware",
    "metrics": metrics.to_dict("records"),
    "old_bge_ft_e2e_comparison": (
        comparison.to_dict("records")
        if comparison is not None
        else None
    ),
    "benchmark_caveat": (
        "Häring judgments are pool-incomplete. The known-positive-gated E2E "
        "metrics are conservative diagnostics, not complete semantic pipeline accuracy."
    ),
}

SUMMARY_PATH.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n" + "=" * 108)
print("HÄRING RRF60 -> CLOSURE-AWARE END-TO-END RUN COMPLETE")
print("=" * 108)
print("Known-positive RRF Hit@1: 16/82 = 0.195122")
print("\nMETRICS")
print(metrics.to_string(index=False))

if comparison is not None:
    print("\nRRF vs OLD BGE-FT — KNOWN-POSITIVE-GATED STRICT E2E")
    print(comparison.to_string(index=False))
else:
    print(
        "\nOld BGE-FT responses file not found; skipped direct E2E comparison."
    )

print("\nSaved:")
for p in (
    CLOSURE_MANIFEST_PATH,
    CLOSURE_AUDIT_PATH,
    RESPONSES_PATH,
    PER_CASE_PATH,
    METRICS_PATH,
    KNOWN16_PATH,
    BGE_COMPARE_PATH if comparison is not None else None,
    PROTOCOL_PATH,
    SUMMARY_PATH,
):
    if p is not None:
        print(" ", p)
