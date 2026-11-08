# ============================================================
# CLEAN CROSS-TRACKER TAXONOMY AUDIT — AUTOMATIC, BLINDED
# ============================================================
#
# Purpose
# -------
# Repair the circular 90-case audit.
#
# The LLM annotator sees ONLY tracker-native evidence:
#
# Firefox / Bugzilla
#   - title
#   - description excerpt
#   - current native status
#   - raw Bugzilla history changes involving status/resolution/cf_last_resolved
#   - NEVER the builder's pre-extracted raw_resolution
#   - NEVER the deterministic taxonomy prediction
#
# VLC / Trac
#   - title
#   - description excerpt
#   - native status
#   - native Trac resolution
#
# Nextcloud / GitHub
#   - title
#   - body excerpt
#   - historical snapshot state/labels/closed_at
#   - native GitHub state_reason ONLY when the current closed_at matches the
#     historical snapshot closed_at (same temporal guard as the E2E work)
#
# The annotator is given ONLY the semantic definitions of:
#   RESOLVED / REJECTED / ABANDONED / REDIRECTED
# plus UNRESOLVED when native evidence is insufficient.
#
# IMPORTANT
# ---------
# All LLM annotations are completed and frozen to disk BEFORE rule predictions
# are computed/scored.
#
# This is an independent *LLM* audit, NOT independent human validation.
#
# Inputs expected on your machine:
#
# C:\Users\Ogtay\Downloads\haring_taxonomy_transfer_audit\
#   taxonomy_transfer_90_BLINDED.csv
#
# C:\Users\Ogtay\Downloads\haring_verified_tmp\
#   df_firefox_issues_android.csv
#   df_vlc_issues.csv
#   df_nextcloud_issues.csv
#
# Existing Nextcloud API cache is reused when present.
#
# Outputs:
#
# C:\Users\Ogtay\Downloads\haring_taxonomy_transfer_clean_audit\
#   CLEAN_native_evidence_90.csv
#   CLEAN_llm_annotations_FROZEN.csv
#   CLEAN_llm_progress.jsonl
#   CLEAN_scored_90.csv
#   CLEAN_score_by_tracker.csv
#   CLEAN_confusion_matrix.csv
#   CLEAN_protocol.json
#   CLEAN_summary.json
#
# API key is never printed or saved.
# ============================================================

from __future__ import annotations

from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from datetime import datetime, timezone
import ast
import getpass
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd
import requests

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing openai package. Install once:\n"
        "  python -m pip install -U openai pandas numpy requests\n"
    ) from exc


# ------------------------------------------------------------------
# Frozen setup
# ------------------------------------------------------------------

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
API_WORKERS = 3
API_MAX_ATTEMPTS = 5
PROMPT_VERSION = "cross-tracker-native-evidence-blind-audit-v1-2026-08-08"

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")

OLD_AUDIT_DIR = DOWNLOADS / "haring_taxonomy_transfer_audit"
SAMPLE_PATH = OLD_AUDIT_DIR / "taxonomy_transfer_90_BLINDED.csv"
OLD_API_CACHE = OLD_AUDIT_DIR / "nextcloud_api_raw"

DATA = DOWNLOADS / "haring_verified_tmp"
FF_PATH = DATA / "df_firefox_issues_android.csv"
VLC_PATH = DATA / "df_vlc_issues.csv"
NC_PATH = DATA / "df_nextcloud_issues.csv"

OUT = DOWNLOADS / "haring_taxonomy_transfer_clean_audit"
OUT.mkdir(parents=True, exist_ok=True)
API_CACHE = OUT / "nextcloud_api_raw"
API_CACHE.mkdir(parents=True, exist_ok=True)

EVIDENCE_PATH = OUT / "CLEAN_native_evidence_90.csv"
FROZEN_ANNOTATIONS = OUT / "CLEAN_llm_annotations_FROZEN.csv"
PROGRESS_PATH = OUT / "CLEAN_llm_progress.jsonl"
SCORED_PATH = OUT / "CLEAN_scored_90.csv"
TRACKER_SCORE_PATH = OUT / "CLEAN_score_by_tracker.csv"
CONFUSION_PATH = OUT / "CLEAN_confusion_matrix.csv"
PROTOCOL_PATH = OUT / "CLEAN_protocol.json"
SUMMARY_PATH = OUT / "CLEAN_summary.json"

GITHUB_REPO = "nextcloud/android"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

thread_local = local()

VALID_CLASSES = {
    "RESOLVED",
    "REJECTED",
    "ABANDONED",
    "REDIRECTED",
    "UNRESOLVED",
}

TAXONOMY_SYSTEM = """You are independently adjudicating closure outcomes of
software issues from heterogeneous issue trackers.

You are NOT evaluating a generated response and you are NOT reproducing a
provided mapping. You will receive only tracker-native evidence.

Assign exactly one Level-1 outcome:

RESOLVED:
  The available tracker evidence confirms the issue was fixed, resolved, or
  completed as an actual resolution.

REJECTED:
  The issue was deliberately closed without a planned fix, such as invalid,
  wontfix, by-design, not-a-bug, or not-planned.

ABANDONED:
  The issue was closed without confirmed resolution, including stale/inactive,
  insufficient information, unable/cannot reproduce, no-response, or
  upstream/third-party dependency.

REDIRECTED:
  The issue was closed because it is a duplicate or explicitly tracked/moved
  elsewhere.

UNRESOLVED:
  The supplied native evidence is insufficient or genuinely contradictory, so
  none of the four outcomes can be assigned confidently.

Important:
- Do not infer that CLOSED by itself means fixed.
- Use only the supplied native evidence.
- Do not invent facts.
- Do not assume any tracker-specific mapping beyond the meanings visible in
  the evidence itself.

Return one JSON object exactly:
{"l1_class":"RESOLVED|REJECTED|ABANDONED|REDIRECTED|UNRESOLVED",
 "subtype":"brief subtype or empty",
 "confidence":0.0,
 "rationale":"brief evidence-based explanation"}
"""


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
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass

    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))

    s = str(x).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


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


def parse_labels(value):
    s = clean(value)
    if not s:
        return []

    if not s.startswith("[") and ";" in s:
        return [x.strip() for x in s.split(";") if x.strip()]

    if not s.startswith("["):
        return [s]

    try:
        obj = ast.literal_eval(s)
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


# ------------------------------------------------------------------
# Firefox native evidence extraction
# ------------------------------------------------------------------

def firefox_closure_history_native(history_value):
    """
    Extract only NATIVE Bugzilla history changes related to closure.
    This is evidence filtering, NOT taxonomy mapping.

    We return raw event/change records. We do not return a derived resolution
    label or taxonomy class.
    """
    obj = parse_structured(history_value)
    if not isinstance(obj, list):
        return []

    events = []

    for event in obj:
        if not isinstance(event, dict):
            continue

        selected_changes = []
        for ch in event.get("changes", []):
            if not isinstance(ch, dict):
                continue

            field = clean(ch.get("field_name")).lower()
            if field in {"status", "resolution", "cf_last_resolved"}:
                selected_changes.append(
                    {
                        "field_name": clean(ch.get("field_name")),
                        "removed": clean(ch.get("removed")),
                        "added": clean(ch.get("added")),
                    }
                )

        if selected_changes:
            events.append(
                {
                    "when": clean(event.get("when")),
                    "who": clean(event.get("who")),
                    "changes": selected_changes,
                }
            )

    return events


# ------------------------------------------------------------------
# GitHub native evidence, with temporal guard
# ------------------------------------------------------------------

def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "haring-clean-taxonomy-audit",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def fetch_nextcloud(issue_number):
    filename = f"issue_{issue_number}.json"

    new_cache = API_CACHE / filename
    old_cache = OLD_API_CACHE / filename

    for cache in (new_cache, old_cache):
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
            if cache != new_cache:
                new_cache.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            return payload, "cache"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}"
    response = requests.get(
        url,
        headers=github_headers(),
        timeout=45,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API {response.status_code} for Nextcloud #{issue_number}; "
            f"rate_remaining={response.headers.get('X-RateLimit-Remaining')}"
        )

    payload = response.json()
    new_cache.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return payload, "github_rest_api"


# ------------------------------------------------------------------
# Build the CLEAN evidence packet from original native corpora
# ------------------------------------------------------------------

for path in (SAMPLE_PATH, FF_PATH, VLC_PATH, NC_PATH):
    if not path.exists():
        raise FileNotFoundError(path)

sample = pd.read_csv(SAMPLE_PATH, low_memory=False)

if len(sample) != 90:
    raise AssertionError(f"Expected 90 sampled cases, got {len(sample)}")

expected_counts = sample.groupby("tracker").size().astype(int).to_dict()
if expected_counts != {"Firefox": 30, "Nextcloud": 30, "VLC": 30}:
    raise AssertionError(f"Unexpected sample counts: {expected_counts}")

ff = pd.read_csv(FF_PATH, low_memory=False)
vlc = pd.read_csv(VLC_PATH, low_memory=False)
nc = pd.read_csv(NC_PATH, low_memory=False)

if len(ff) != 29941:
    raise AssertionError(f"Firefox corpus changed: {len(ff)}")
if len(vlc) != 553:
    raise AssertionError(f"VLC corpus changed: {len(vlc)}")
if len(nc) != 2462:
    raise AssertionError(f"Nextcloud corpus changed: {len(nc)}")

ff["_norm_id"] = ff["id"].map(norm_id)
vlc["_norm_id"] = vlc["id"].map(norm_id)
nc["_norm_id"] = nc["id"].map(norm_id)
nc["_norm_number"] = nc["number"].map(norm_id)

if ff["_norm_id"].duplicated().any():
    ff = ff.drop_duplicates("_norm_id", keep="first")
if vlc["_norm_id"].duplicated().any():
    vlc = vlc.drop_duplicates("_norm_id", keep="first")
if nc["_norm_id"].duplicated().any():
    nc = nc.drop_duplicates("_norm_id", keep="first")

ff_lookup = ff.set_index("_norm_id", drop=False)
vlc_lookup = vlc.set_index("_norm_id", drop=False)
nc_lookup = nc.set_index("_norm_id", drop=False)

evidence_rows = []
nextcloud_api_failures = []

for sampled in sample.to_dict("records"):
    audit_id = clean(sampled["audit_id"])
    tracker = clean(sampled["tracker"])
    issue_id = norm_id(sampled["issue_id"])

    if tracker == "Firefox":
        if issue_id not in ff_lookup.index:
            raise AssertionError(f"{audit_id}: Firefox issue {issue_id} absent")

        row = ff_lookup.loc[issue_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        native_events = firefox_closure_history_native(row.get("history"))

        evidence = {
            "tracker": "Firefox / Bugzilla",
            "issue_id": issue_id,
            "title": clean(row.get("summary")),
            "description_excerpt": clean(row.get("description"))[:1600],
            "native_status": clean(row.get("status")),
            "native_closure_history_events": native_events,
        }

    elif tracker == "VLC":
        if issue_id not in vlc_lookup.index:
            raise AssertionError(f"{audit_id}: VLC issue {issue_id} absent")

        row = vlc_lookup.loc[issue_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        evidence = {
            "tracker": "VLC / Trac",
            "issue_id": issue_id,
            "title": clean(row.get("summary")),
            "description_excerpt": clean(row.get("description"))[:1600],
            "native_status": clean(row.get("status")),
            "native_resolution": clean(row.get("resolution")),
        }

    elif tracker == "Nextcloud":
        if issue_id not in nc_lookup.index:
            raise AssertionError(
                f"{audit_id}: Nextcloud issue global ID {issue_id} absent"
            )

        row = nc_lookup.loc[issue_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        issue_number = norm_id(row.get("number"))
        local_closed_at = clean(row.get("closed_at"))
        local_state = clean(row.get("state"))
        local_labels = parse_labels(row.get("labels"))

        try:
            payload, api_source = fetch_nextcloud(issue_number)
        except Exception as exc:
            nextcloud_api_failures.append(
                {
                    "audit_id": audit_id,
                    "issue_number": issue_number,
                    "error": str(exc),
                }
            )
            payload = {}
            api_source = "failed"

        current_state = clean(payload.get("state"))
        current_closed_at = clean(payload.get("closed_at"))

        same_closure_event = (
            current_state.lower() == "closed"
            and bool(local_closed_at)
            and normalize_time(current_closed_at)
            == normalize_time(local_closed_at)
        )

        # Crucial: current state_reason is visible ONLY for the same historical
        # closure event. Otherwise it is hidden as temporally unsafe.
        safe_state_reason = (
            clean(payload.get("state_reason"))
            if same_closure_event
            else ""
        )

        evidence = {
            "tracker": "Nextcloud / GitHub",
            "issue_global_id": issue_id,
            "issue_number": issue_number,
            "title": clean(row.get("title")),
            "body_excerpt": clean(row.get("body"))[:1600],
            "historical_snapshot_state": local_state,
            "historical_snapshot_labels": local_labels,
            "historical_snapshot_closed_at": local_closed_at,
            "native_state_reason_for_same_closure_event": safe_state_reason,
            "temporal_match_for_state_reason": same_closure_event,
            "api_source": api_source,
        }

    else:
        raise AssertionError(f"{audit_id}: unknown tracker {tracker!r}")

    evidence_rows.append(
        {
            "audit_id": audit_id,
            "tracker": tracker,
            "issue_id": issue_id,
            "native_evidence_json": json.dumps(
                evidence,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    )

evidence_df = pd.DataFrame(evidence_rows)

if len(evidence_df) != 90:
    raise AssertionError(f"Evidence packet has {len(evidence_df)} rows")

if evidence_df["audit_id"].duplicated().any():
    raise AssertionError("Duplicate audit IDs in clean evidence packet")

evidence_df.to_csv(EVIDENCE_PATH, index=False)


# ------------------------------------------------------------------
# Independent LLM annotator
# ------------------------------------------------------------------

def annotator_prompt(row):
    return f"""CASE ID: {row['audit_id']}

TRACKER-NATIVE EVIDENCE:
{row['native_evidence_json']}

Assign the Level-1 closure outcome using only that evidence."""


def get_client(api_key):
    if not hasattr(thread_local, "client"):
        thread_local.client = OpenAI(
            api_key=api_key,
            timeout=60,
            max_retries=0,
        )
    return thread_local.client


def call_annotator(api_key, row):
    last_error = None

    for attempt in range(API_MAX_ATTEMPTS):
        try:
            response = get_client(api_key).chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": TAXONOMY_SYSTEM},
                    {"role": "user", "content": annotator_prompt(row)},
                ],
                temperature=TEMPERATURE,
                max_tokens=220,
                response_format={"type": "json_object"},
            )

            text = clean(response.choices[0].message.content)
            if not text:
                raise RuntimeError("Empty annotation response")

            obj = json.loads(text)

            expected = {
                "l1_class",
                "subtype",
                "confidence",
                "rationale",
            }

            if set(obj) != expected:
                raise ValueError(
                    f"Wrong JSON keys: expected {sorted(expected)}, "
                    f"got {sorted(obj)}"
                )

            l1 = clean(obj["l1_class"]).upper()
            if l1 not in VALID_CLASSES:
                raise ValueError(f"Invalid l1_class: {l1!r}")

            confidence = float(obj["confidence"])
            if (
                not math.isfinite(confidence)
                or confidence < 0.0
                or confidence > 1.0
            ):
                raise ValueError(f"Invalid confidence: {confidence}")

            rationale = clean(obj["rationale"])
            if not rationale:
                raise ValueError("Empty rationale")

            return {
                "audit_id": row["audit_id"],
                "tracker": row["tracker"],
                "issue_id": row["issue_id"],
                "llm_l1_class": l1,
                "llm_subtype": clean(obj["subtype"]),
                "llm_confidence": confidence,
                "llm_rationale": rationale,
                "model_requested": MODEL,
                "model_returned": clean(
                    getattr(response, "model", MODEL)
                ),
                "prompt_version": PROMPT_VERSION,
                "completed_at_utc": utc_now(),
            }

        except Exception as exc:
            last_error = exc
            if attempt + 1 < API_MAX_ATTEMPTS:
                time.sleep(min(30, 2 ** (attempt + 1)))

    raise RuntimeError(
        f"Annotation failed after {API_MAX_ATTEMPTS}: {last_error}"
    )


def load_progress():
    done = {}

    if not PROGRESS_PATH.exists():
        return done

    with PROGRESS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("ok") is True:
                done[record["audit_id"]] = record["annotation"]

    return done


def save_progress(annotation):
    record = {
        "ok": True,
        "audit_id": annotation["audit_id"],
        "annotation": annotation,
    }

    with PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


# Never reuse the contaminated old annotation file.
api_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not api_key:
    api_key = getpass.getpass(
        "OPENAI_API_KEY not found. Paste key here (hidden): "
    ).strip()

if not api_key:
    raise SystemExit("No OpenAI API key supplied.")

progress = load_progress()

jobs = [
    row
    for row in evidence_df.to_dict("records")
    if row["audit_id"] not in progress
]

if jobs:
    print(f"CLEAN BLINDED LLM ANNOTATION: {len(jobs)} remaining cases")

    failures = []

    with ThreadPoolExecutor(
        max_workers=min(API_WORKERS, len(jobs))
    ) as pool:
        futures = {
            pool.submit(call_annotator, api_key, row): row
            for row in jobs
        }

        for completed, future in enumerate(
            as_completed(futures),
            start=1,
        ):
            row = futures[future]

            try:
                annotation = future.result()
                progress[annotation["audit_id"]] = annotation
                save_progress(annotation)
            except Exception as exc:
                failures.append(
                    {
                        "audit_id": row["audit_id"],
                        "error": str(exc),
                    }
                )
                print(
                    f"FAILED {row['audit_id']}: {exc}",
                    flush=True,
                )

            if completed % 15 == 0 or completed == len(jobs):
                print(
                    f"  {completed}/{len(jobs)}; "
                    f"failures={len(failures)}",
                    flush=True,
                )

else:
    print("CLEAN BLINDED LLM ANNOTATION: already complete")

if len(progress) != 90:
    print(
        f"\nOnly {len(progress)}/90 annotations are complete. "
        "Rerun the same script; completed cases will be reused."
    )
    raise SystemExit(2)


# ------------------------------------------------------------------
# FREEZE annotations BEFORE rule scoring
# ------------------------------------------------------------------

annotation_rows = [
    progress[audit_id]
    for audit_id in evidence_df["audit_id"]
]

annotations_df = pd.DataFrame(annotation_rows)

if len(annotations_df) != 90:
    raise AssertionError("Frozen annotation frame is not 90 rows")

# This write happens BEFORE any rule-prediction function below is called.
annotations_df.to_csv(FROZEN_ANNOTATIONS, index=False)

print(
    "\nAll 90 clean annotations frozen BEFORE deterministic rule scoring:",
    FROZEN_ANNOTATIONS,
    flush=True,
)


# ==================================================================
# RULE SCORING STARTS ONLY HERE
# ==================================================================

REJECTED_PATTERNS = (
    "wontfix",
    "won't-fix",
    "won't fix",
    "wont fix",
    "wont-fix",
    "by-design",
    "by design",
    "invalid",
    "not-a-bug",
    "not a bug",
    "not planned",
    "not-planned",
)

STALE_PATTERNS = (
    "stale",
    "auto-closed",
    "auto closed",
    "inactive",
)

NEEDS_INFO_PATTERNS = (
    "needs author reply",
    "needs-info",
    "needs info",
    "more info",
    "needs reproduction",
    "needs repro",
    "can't reproduce",
    "cannot reproduce",
    "cant reproduce",
    "unable to reproduce",
    "unconfirmed",
)

UPSTREAM_PATTERNS = (
    "upstream",
    "third-party",
    "third party",
)


def final_firefox_resolution(history_value):
    """
    Deterministic rule-side extraction. This function is called ONLY after
    clean LLM annotations have been frozen.
    """
    events = firefox_closure_history_native(history_value)

    current = ""

    for event in events:
        for change in event["changes"]:
            if clean(change["field_name"]).lower() == "resolution":
                current = clean(change["added"]).upper()

    return current


def rule_firefox(row):
    status = clean(row.get("status")).upper()

    if status not in {"RESOLVED", "VERIFIED"}:
        return "UNRESOLVED"

    resolution = final_firefox_resolution(row.get("history"))

    if resolution == "FIXED":
        return "RESOLVED"

    if resolution in {"DUPLICATE", "MOVED"}:
        return "REDIRECTED"

    if resolution in {"WONTFIX", "INVALID"}:
        return "REJECTED"

    if resolution in {
        "INCOMPLETE",
        "WORKSFORME",
        "EXPIRED",
        "INACTIVE",
        "LATER",
        "REMIND",
    }:
        return "ABANDONED"

    return "UNRESOLVED"


def rule_vlc(row):
    status = clean(row.get("status")).lower()
    resolution = clean(row.get("resolution")).lower()

    if status != "closed":
        return "UNRESOLVED"

    if resolution == "fixed":
        return "RESOLVED"

    if resolution == "duplicate":
        return "REDIRECTED"

    if resolution in {"wontfix", "invalid", "notvlc"}:
        return "REJECTED"

    if resolution in {"incomplete", "worksforme"}:
        return "ABANDONED"

    return "UNRESOLVED"


def rule_github_from_clean_evidence(evidence):
    reason = clean(
        evidence.get(
            "native_state_reason_for_same_closure_event"
        )
    ).lower().replace("-", "_")

    labels = [
        re.sub(r"\s+", " ", clean(x).lower())
        for x in evidence.get("historical_snapshot_labels", [])
        if clean(x)
    ]

    if reason == "duplicate" or any(
        "duplicate" in label
        for label in labels
    ):
        return "REDIRECTED"

    for label in labels:
        if any(
            pattern in label
            for pattern in REJECTED_PATTERNS
        ):
            return "REJECTED"

    for label in labels:
        if any(
            pattern in label
            for pattern in STALE_PATTERNS
        ):
            return "ABANDONED"

    for label in labels:
        if any(
            pattern in label
            for pattern in NEEDS_INFO_PATTERNS
        ):
            return "ABANDONED"

    for label in labels:
        if any(
            pattern in label
            for pattern in UPSTREAM_PATTERNS
        ):
            return "ABANDONED"

    if reason == "not_planned":
        return "REJECTED"

    if reason == "completed":
        return "RESOLVED"

    return "UNRESOLVED"


rule_rows = []

for sampled in sample.to_dict("records"):
    audit_id = clean(sampled["audit_id"])
    tracker = clean(sampled["tracker"])
    issue_id = norm_id(sampled["issue_id"])

    if tracker == "Firefox":
        native = ff_lookup.loc[issue_id]
        if isinstance(native, pd.DataFrame):
            native = native.iloc[0]
        prediction = rule_firefox(native)

    elif tracker == "VLC":
        native = vlc_lookup.loc[issue_id]
        if isinstance(native, pd.DataFrame):
            native = native.iloc[0]
        prediction = rule_vlc(native)

    else:
        clean_evidence = json.loads(
            evidence_df.loc[
                evidence_df["audit_id"] == audit_id,
                "native_evidence_json",
            ].iloc[0]
        )
        prediction = rule_github_from_clean_evidence(
            clean_evidence
        )

    rule_rows.append(
        {
            "audit_id": audit_id,
            "rule_l1_class": prediction,
        }
    )

rule_df = pd.DataFrame(rule_rows)

scored = (
    evidence_df
    .merge(annotations_df, on=["audit_id", "tracker", "issue_id"], how="inner")
    .merge(rule_df, on="audit_id", how="inner")
)

if len(scored) != 90:
    raise AssertionError(
        f"Scored merge produced {len(scored)} rows"
    )

scored["llm_adjudicable"] = (
    scored["llm_l1_class"] != "UNRESOLVED"
)

scored["rule_adjudicable"] = (
    scored["rule_l1_class"] != "UNRESOLVED"
)

scored["both_adjudicable"] = (
    scored["llm_adjudicable"]
    & scored["rule_adjudicable"]
)

scored["agreement"] = (
    scored["llm_l1_class"]
    == scored["rule_l1_class"]
)

scored.to_csv(SCORED_PATH, index=False)


# ------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------

FOUR = [
    "ABANDONED",
    "REDIRECTED",
    "REJECTED",
    "RESOLVED",
]


def accuracy(y_true, y_pred):
    if not y_true:
        return float("nan")

    return float(
        np.mean(
            np.asarray(y_true, dtype=object)
            == np.asarray(y_pred, dtype=object)
        )
    )


def macro_f1(y_true, y_pred, labels):
    values = []

    for label in labels:
        tp = sum(
            t == label and p == label
            for t, p in zip(y_true, y_pred)
        )
        fp = sum(
            t != label and p == label
            for t, p in zip(y_true, y_pred)
        )
        fn = sum(
            t == label and p != label
            for t, p in zip(y_true, y_pred)
        )

        if tp == 0 and fp == 0 and fn == 0:
            continue

        precision = (
            tp / (tp + fp)
            if tp + fp
            else 0.0
        )
        recall = (
            tp / (tp + fn)
            if tp + fn
            else 0.0
        )

        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )

        values.append(f1)

    return float(np.mean(values)) if values else float("nan")


def cohen_kappa(y_true, y_pred):
    n = len(y_true)

    if n == 0:
        return float("nan")

    po = accuracy(y_true, y_pred)

    true_counts = Counter(y_true)
    pred_counts = Counter(y_pred)

    pe = sum(
        (true_counts[label] / n)
        * (pred_counts[label] / n)
        for label in set(true_counts) | set(pred_counts)
    )

    if pe == 1:
        return 1.0

    return float((po - pe) / (1 - pe))


score_rows = []

for tracker in ["Firefox", "Nextcloud", "VLC", "POOLED"]:
    g = (
        scored
        if tracker == "POOLED"
        else scored[scored["tracker"] == tracker]
    )

    both = g[g["both_adjudicable"]].copy()

    y_llm = both["llm_l1_class"].tolist()
    y_rule = both["rule_l1_class"].tolist()

    observed_labels = sorted(
        (set(y_llm) | set(y_rule)) - {"UNRESOLVED"}
    )

    score_rows.append(
        {
            "tracker": tracker,
            "n_total": int(len(g)),
            "llm_adjudicable_n": int(
                g["llm_adjudicable"].sum()
            ),
            "rule_adjudicable_n": int(
                g["rule_adjudicable"].sum()
            ),
            "both_adjudicable_n": int(len(both)),
            "both_adjudicable_coverage": float(
                len(both) / len(g)
            ),
            "agreement_on_both_adjudicable": accuracy(
                y_llm,
                y_rule,
            ),
            "macro_f1_observed_classes": macro_f1(
                y_llm,
                y_rule,
                observed_labels,
            ),
            "cohen_kappa": cohen_kappa(
                y_llm,
                y_rule,
            ),
            "conservative_all_case_exact_agreement": float(
                g["agreement"].mean()
            ),
            "discordant_cases": int(
                (~g["agreement"]).sum()
            ),
            "llm_unresolved": int(
                (g["llm_l1_class"] == "UNRESOLVED").sum()
            ),
            "rule_unresolved": int(
                (g["rule_l1_class"] == "UNRESOLVED").sum()
            ),
            "observed_classes": "|".join(
                observed_labels
            ),
        }
    )

scores = pd.DataFrame(score_rows)
scores.to_csv(TRACKER_SCORE_PATH, index=False)

# Confusion matrix on pooled jointly-adjudicable cases.
pooled = scored[scored["both_adjudicable"]].copy()

labels = sorted(
    (
        set(pooled["llm_l1_class"])
        | set(pooled["rule_l1_class"])
    )
    - {"UNRESOLVED"}
)

matrix = []

for llm_label in labels:
    row = []
    for rule_label in labels:
        row.append(
            int(
                (
                    (pooled["llm_l1_class"] == llm_label)
                    & (pooled["rule_l1_class"] == rule_label)
                ).sum()
            )
        )
    matrix.append(row)

confusion = pd.DataFrame(
    matrix,
    index=[f"llm_{x}" for x in labels],
    columns=[f"rule_{x}" for x in labels],
)

confusion.to_csv(CONFUSION_PATH)


# ------------------------------------------------------------------
# Protocol + final summary
# ------------------------------------------------------------------

PROTOCOL_PATH.write_text(
    json.dumps(
        {
            "created_at_utc": utc_now(),
            "n_cases": 90,
            "sampling": (
                "Same preselected 30 Firefox + 30 VLC + 30 Nextcloud "
                "cases from the prior audit; annotations were regenerated "
                "from original tracker-native corpora."
            ),
            "annotator": "isolated OpenAI LLM call",
            "model_requested": MODEL,
            "temperature": TEMPERATURE,
            "prompt_version": PROMPT_VERSION,
            "annotation_blinding": {
                "taxonomy_prediction_visible": False,
                "action_template_visible": False,
                "old_annotation_visible": False,
                "firefox_preextracted_resolution_visible": False,
                "rule_predictions_computed_after_annotations_frozen": True,
            },
            "native_evidence": {
                "Firefox": [
                    "title",
                    "description excerpt",
                    "native status",
                    "raw Bugzilla closure-related history changes",
                ],
                "VLC": [
                    "title",
                    "description excerpt",
                    "native status",
                    "native Trac resolution",
                ],
                "Nextcloud": [
                    "title",
                    "body excerpt",
                    "historical state",
                    "historical labels",
                    "historical closed_at",
                    "native state_reason only for same closure event",
                ],
            },
            "taxonomy_system_prompt": TAXONOMY_SYSTEM,
            "nextcloud_api_failures": nextcloud_api_failures,
            "github_token_used": bool(GITHUB_TOKEN),
            "important_limitation": (
                "This is blinded LLM verification, not independent human "
                "validation. Do not report it as human annotation."
            ),
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

summary = {
    "created_at_utc": utc_now(),
    "scores": scores.to_dict("records"),
    "llm_class_distribution": (
        scored["llm_l1_class"]
        .value_counts()
        .sort_index()
        .to_dict()
    ),
    "rule_class_distribution": (
        scored["rule_l1_class"]
        .value_counts()
        .sort_index()
        .to_dict()
    ),
    "discordant_cases": scored.loc[
        ~scored["agreement"],
        [
            "audit_id",
            "tracker",
            "issue_id",
            "llm_l1_class",
            "rule_l1_class",
            "llm_confidence",
            "llm_rationale",
        ],
    ].to_dict("records"),
    "important_limitation": (
        "Blinded LLM-vs-deterministic-mapping audit; "
        "not human validation."
    ),
}

SUMMARY_PATH.write_text(
    json.dumps(
        summary,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print("\n" + "=" * 112)
print("CLEAN BLINDED CROSS-TRACKER TAXONOMY AUDIT COMPLETE")
print("=" * 112)
print("\nThe annotator saw tracker-native evidence only.")
print("Predicted taxonomy classes were computed only AFTER all 90 annotations were frozen.")
print("\nSCORES")
print(scores.to_string(index=False))

discordant = scored[~scored["agreement"]]

print("\nDISCORDANT CASES:", len(discordant))
if len(discordant):
    print(
        discordant[
            [
                "audit_id",
                "tracker",
                "issue_id",
                "llm_l1_class",
                "rule_l1_class",
                "llm_confidence",
                "llm_rationale",
            ]
        ].to_string(index=False)
    )

print("\nSaved:")
for p in (
    EVIDENCE_PATH,
    FROZEN_ANNOTATIONS,
    SCORED_PATH,
    TRACKER_SCORE_PATH,
    CONFUSION_PATH,
    PROTOCOL_PATH,
    SUMMARY_PATH,
):
    print(" ", p)

print(
    "\nINTERPRETATION GUARD: this is blinded LLM verification, "
    "not independent human validation."
)
