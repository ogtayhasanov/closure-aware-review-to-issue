# ============================================================
# BUILD 90-CASE CROSS-TRACKER TAXONOMY TRANSFER AUDIT
# ============================================================
#
# 30 independently sampled CLOSED issues per tracker:
#   Firefox / Bugzilla
#   VLC / Trac
#   Nextcloud / GitHub
#
# This is independent of retrieval and therefore directly tests whether
# the same Level-1 closure taxonomy transfers across tracker ecosystems.
#
# Inputs:
#   C:\Users\Ogtay\Downloads\haring_verified_tmp\
#       df_firefox_issues_android.csv
#       df_vlc_issues.csv
#       df_nextcloud_issues.csv
#
# Outputs:
#   C:\Users\Ogtay\Downloads\haring_taxonomy_transfer_audit\
#       taxonomy_transfer_90_BLINDED.csv
#       taxonomy_transfer_90_KEY.csv
#       taxonomy_transfer_protocol.json
#       taxonomy_manual_instructions.txt
#       nextcloud_api_raw\issue_<number>.json
#
# Nextcloud:
#   uses local snapshot labels + current state_reason ONLY when current
#   closed_at matches snapshot closed_at, same temporal guard as E2E.
#
# Optional:
#   set GITHUB_TOKEN for a higher API rate limit.
# ============================================================

from pathlib import Path
import ast
import json
import os
import random
import re
from datetime import datetime, timezone

import pandas as pd
import requests

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
DATA = DOWNLOADS / "haring_verified_tmp"
FF_PATH = DATA / "df_firefox_issues_android.csv"
VLC_PATH = DATA / "df_vlc_issues.csv"
NC_PATH = DATA / "df_nextcloud_issues.csv"

OUT = DOWNLOADS / "haring_taxonomy_transfer_audit"
RAW = OUT / "nextcloud_api_raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

BLIND = OUT / "taxonomy_transfer_90_BLINDED.csv"
KEY = OUT / "taxonomy_transfer_90_KEY.csv"
PROTOCOL = OUT / "taxonomy_transfer_protocol.json"
INSTRUCTIONS = OUT / "taxonomy_manual_instructions.txt"

SEED = 42
N_PER_TRACKER = 30
GITHUB_REPO = "nextcloud/android"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


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


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
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


def map_firefox(status, history):
    st = clean(status).upper()
    if st not in {"RESOLVED", "VERIFIED"}:
        return None

    resolution, trace = firefox_resolution_from_history(history)

    if resolution == "FIXED":
        return ("RESOLVED", "fixed", "RESOLVED", resolution, trace)
    if resolution in {"DUPLICATE", "MOVED"}:
        return (
            "REDIRECTED",
            "duplicate" if resolution == "DUPLICATE" else "moved",
            "REDIRECTED",
            resolution,
            trace,
        )
    if resolution in {"WONTFIX", "INVALID"}:
        return ("REJECTED", resolution.lower(), "REJECTED", resolution, trace)
    if resolution == "INCOMPLETE":
        return ("ABANDONED", "NEEDS_INFO", "ABANDONED_NEEDS_INFO", resolution, trace)
    if resolution == "WORKSFORME":
        return ("ABANDONED", "NEEDS_INFO", "ABANDONED_NEEDS_INFO", resolution, trace)
    if resolution in {"EXPIRED", "INACTIVE"}:
        return ("ABANDONED", "STALE", "ABANDONED", resolution, trace)
    if resolution in {"LATER", "REMIND"}:
        return ("ABANDONED", "OTHER", "ABANDONED", resolution, trace)

    return None


def map_vlc(status, resolution):
    st = clean(status).lower()
    res = clean(resolution).lower()

    if st != "closed":
        return None

    if res == "fixed":
        return ("RESOLVED", "fixed", "RESOLVED", res)
    if res == "duplicate":
        return ("REDIRECTED", "duplicate", "REDIRECTED", res)
    if res in {"wontfix", "invalid", "notvlc"}:
        return ("REJECTED", res, "REJECTED", res)
    if res in {"incomplete", "worksforme"}:
        return ("ABANDONED", "NEEDS_INFO", "ABANDONED_NEEDS_INFO", res)

    return None


REJECTED_PATTERNS = (
    "wontfix", "won't-fix", "won't fix", "wont fix", "wont-fix",
    "by-design", "by design", "invalid", "not-a-bug", "not a bug",
    "not planned", "not-planned",
)
STALE_PATTERNS = ("stale", "auto-closed", "auto closed", "inactive")
NEEDS_INFO_PATTERNS = (
    "needs author reply", "needs-info", "needs info", "more info",
    "needs reproduction", "needs repro", "can't reproduce",
    "cannot reproduce", "cant reproduce", "unable to reproduce", "unconfirmed",
)
UPSTREAM_PATTERNS = ("upstream", "third-party", "third party")


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
                if isinstance(item, dict) and item.get("name"):
                    out.append(clean(item["name"]))
                elif isinstance(item, str) and clean(item):
                    out.append(clean(item))
            return out
    except Exception:
        pass

    return re.findall(r"""['"]name['"]\s*:\s*['"]([^'"]+)['"]""", s)


def classify_github(state_reason, labels):
    reason = clean(state_reason).lower().replace("-", "_")
    labs = [re.sub(r"\s+", " ", x.lower().strip()) for x in labels if clean(x)]

    if reason == "duplicate" or any("duplicate" in x for x in labs):
        return ("REDIRECTED", "duplicate", "REDIRECTED")

    for lab in labs:
        if any(p in lab for p in REJECTED_PATTERNS):
            return ("REJECTED", "wontfix", "REJECTED")

    for lab in labs:
        if any(p in lab for p in STALE_PATTERNS):
            return ("ABANDONED", "STALE", "ABANDONED")

    for lab in labs:
        if any(p in lab for p in NEEDS_INFO_PATTERNS):
            return ("ABANDONED", "NEEDS_INFO", "ABANDONED_NEEDS_INFO")

    for lab in labs:
        if any(p in lab for p in UPSTREAM_PATTERNS):
            return ("ABANDONED", "UPSTREAM", "ABANDONED_UPSTREAM")

    if reason == "not_planned":
        return ("REJECTED", "not_planned", "REJECTED")
    if reason == "completed":
        return ("RESOLVED", "fixed", "RESOLVED")

    return None


def github_headers():
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "haring-taxonomy-transfer-audit",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def fetch_nc(issue_number):
    cache = RAW / f"issue_{issue_number}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), "cache"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue_number}"
    r = requests.get(url, headers=github_headers(), timeout=45)

    if r.status_code != 200:
        raise RuntimeError(
            f"GitHub {r.status_code} for issue #{issue_number}; "
            f"remaining={r.headers.get('X-RateLimit-Remaining')}"
        )

    payload = r.json()
    cache.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return payload, "github_rest_api"


for p in (FF_PATH, VLC_PATH, NC_PATH):
    if not p.exists():
        raise FileNotFoundError(p)

ff = pd.read_csv(FF_PATH, low_memory=False)
vlc = pd.read_csv(VLC_PATH, low_memory=False)
nc = pd.read_csv(NC_PATH, low_memory=False)

if len(ff) != 29941:
    raise AssertionError(f"Firefox raw rows changed: {len(ff)}")
if len(vlc) != 553:
    raise AssertionError(f"VLC raw rows changed: {len(vlc)}")
if len(nc) != 2462:
    raise AssertionError(f"Nextcloud raw rows changed: {len(nc)}")

rng = random.Random(SEED)
records = []

# ---------------- Firefox: sample from all classifiable closed issues ----------
ff_pool = []
for idx, row in ff.iterrows():
    mapped = map_firefox(row.get("status"), row.get("history"))
    if mapped is None:
        continue

    l1, subtype, action, resolution, trace = mapped
    ff_pool.append(
        {
            "tracker": "Firefox",
            "row_index": int(idx),
            "issue_id": norm_id(row.get("id")),
            "title": clean(row.get("summary")),
            "raw_state": clean(row.get("status")),
            "raw_resolution": resolution,
            "raw_labels": "",
            "raw_closed_at": clean(row.get("cf_last_resolved")),
            "raw_history_excerpt": clean(row.get("history"))[:5000],
            "history_resolution_trace": trace,
            "predicted_l1_class": l1,
            "predicted_subtype": subtype,
            "predicted_action": action,
            "mapping_source": "Bugzilla history resolution",
        }
    )

if len(ff_pool) < N_PER_TRACKER:
    raise AssertionError(f"Only {len(ff_pool)} classifiable Firefox issues")

for item in rng.sample(ff_pool, N_PER_TRACKER):
    records.append(item)

# ---------------- VLC ----------------------------------------------------------
vlc_pool = []
for idx, row in vlc.iterrows():
    mapped = map_vlc(row.get("status"), row.get("resolution"))
    if mapped is None:
        continue

    l1, subtype, action, resolution = mapped
    vlc_pool.append(
        {
            "tracker": "VLC",
            "row_index": int(idx),
            "issue_id": norm_id(row.get("id")),
            "title": clean(row.get("summary")),
            "raw_state": clean(row.get("status")),
            "raw_resolution": resolution,
            "raw_labels": "",
            "raw_closed_at": "",
            "raw_history_excerpt": "",
            "history_resolution_trace": "",
            "predicted_l1_class": l1,
            "predicted_subtype": subtype,
            "predicted_action": action,
            "mapping_source": "Trac resolution field",
        }
    )

if len(vlc_pool) < N_PER_TRACKER:
    raise AssertionError(f"Only {len(vlc_pool)} classifiable VLC issues")

for item in rng.sample(vlc_pool, N_PER_TRACKER):
    records.append(item)

# ---------------- Nextcloud ----------------------------------------------------
# Randomize all snapshot-closed rows; process until 30 temporally valid,
# classifiable cases are obtained. Cap requests below unauthenticated 60/h.
nc_closed = nc[nc["state"].astype(str).str.lower() == "closed"].copy()

candidates = list(nc_closed.index)
rng.shuffle(candidates)

nc_records = []
attempts = 0
failures = []

for idx in candidates:
    if len(nc_records) >= N_PER_TRACKER:
        break
    if attempts >= 55:
        break

    row = nc.loc[idx]
    issue_number = norm_id(row.get("number"))
    if not issue_number:
        continue

    attempts += 1

    try:
        payload, source = fetch_nc(issue_number)
    except Exception as exc:
        failures.append({"issue_number": issue_number, "error": str(exc)})
        continue

    current_state = clean(payload.get("state")).lower()
    current_closed_at = clean(payload.get("closed_at"))
    current_reason = clean(payload.get("state_reason")).lower()
    local_closed_at = clean(row.get("closed_at"))

    temporal_match = (
        current_state == "closed"
        and bool(local_closed_at)
        and normalize_time(current_closed_at) == normalize_time(local_closed_at)
    )

    if not temporal_match:
        continue

    labels = parse_labels(row.get("labels"))
    mapped = classify_github(current_reason, labels)
    if mapped is None:
        continue

    l1, subtype, action = mapped
    nc_records.append(
        {
            "tracker": "Nextcloud",
            "row_index": int(idx),
            "issue_id": norm_id(row.get("id")),
            "issue_number": issue_number,
            "title": clean(row.get("title")),
            "raw_state": clean(row.get("state")),
            "raw_resolution": current_reason,
            "raw_labels": ";".join(labels),
            "raw_closed_at": local_closed_at,
            "raw_history_excerpt": "",
            "history_resolution_trace": "",
            "predicted_l1_class": l1,
            "predicted_subtype": subtype,
            "predicted_action": action,
            "mapping_source": (
                f"{source}: state_reason + local snapshot labels; "
                "closure timestamp matched"
            ),
        }
    )

if len(nc_records) != N_PER_TRACKER:
    raise RuntimeError(
        f"Could build only {len(nc_records)}/30 classifiable Nextcloud cases "
        f"after {attempts} API attempts. Set GITHUB_TOKEN and rerun; cache is reused."
    )

records.extend(nc_records)

df = pd.DataFrame(records)

if len(df) != 90:
    raise AssertionError(f"Expected 90 cases, got {len(df)}")

counts = df.groupby("tracker").size().astype(int).to_dict()
if counts != {"Firefox": 30, "Nextcloud": 30, "VLC": 30}:
    raise AssertionError(f"Bad tracker counts: {counts}")

# Randomize audit order across trackers and create IDs.
df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
df["audit_id"] = [f"TAX-{i:03d}" for i in range(1, len(df) + 1)]

blind_cols = [
    "audit_id",
    "tracker",
    "issue_id",
    "issue_number",
    "title",
    "raw_state",
    "raw_resolution",
    "raw_labels",
    "raw_closed_at",
    "raw_history_excerpt",
    "history_resolution_trace",
]

for col in blind_cols:
    if col not in df.columns:
        df[col] = ""

blind = df[blind_cols].copy()
blind["human_l1_class"] = ""
blind["human_subtype"] = ""
blind["human_confident_Y_N"] = ""
blind["human_notes"] = ""

key = df[
    [
        "audit_id",
        "tracker",
        "issue_id",
        "predicted_l1_class",
        "predicted_subtype",
        "predicted_action",
        "mapping_source",
    ]
].copy()

blind.to_csv(BLIND, index=False)
key.to_csv(KEY, index=False)

INSTRUCTIONS.write_text(
    """CROSS-TRACKER TAXONOMY MANUAL AUDIT

Do NOT open taxonomy_transfer_90_KEY.csv until all 90 rows are annotated.

For each row, assign exactly one Level-1 class:
- RESOLVED: fixed/resolved/completed.
- REJECTED: wontfix, invalid, by-design, not-a-bug, not planned.
- ABANDONED: stale/inactive, needs information, cannot reproduce,
  upstream/third-party, or otherwise closed without confirmed resolution.
- REDIRECTED: duplicate or tracked elsewhere.

Subtype is optional but useful:
- ABANDONED: STALE / NEEDS_INFO / UPSTREAM / OTHER
- REDIRECTED: duplicate / moved
- REJECTED: wontfix / invalid / not_planned / other
- RESOLVED: fixed

Use only the raw tracker evidence shown in the row.
Do not infer a fix merely because state=closed.
""",
    encoding="utf-8",
)

PROTOCOL.write_text(
    json.dumps(
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "seed": SEED,
            "n_per_tracker": N_PER_TRACKER,
            "total": 90,
            "sampling": (
                "Independent random sample from classifiable CLOSED issues "
                "in each verified full tracker corpus."
            ),
            "firefox_mapping": "Bugzilla history resolution",
            "vlc_mapping": "Trac status/resolution",
            "nextcloud_mapping": (
                "local snapshot labels + current state_reason only if current "
                "closure timestamp equals snapshot closure timestamp"
            ),
            "nextcloud_api_attempts": attempts,
            "nextcloud_api_failures": failures,
            "github_token_used": bool(GITHUB_TOKEN),
            "blinding": (
                "Predicted taxonomy labels are stored only in KEY; annotator "
                "sheet contains raw tracker evidence but not predicted class."
            ),
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print("\n" + "=" * 100)
print("CROSS-TRACKER TAXONOMY AUDIT BUILT")
print("=" * 100)
print("Cases:", len(df))
print("Per tracker:", counts)
print("Nextcloud API attempts:", attempts)
print("Nextcloud API failures:", len(failures))
print("GitHub token used:", bool(GITHUB_TOKEN))
print("\nPredicted class distribution (DO NOT inspect before human annotation):")
print(df.groupby(["tracker", "predicted_l1_class"]).size().to_string())
print("\nSaved:")
print(" ", BLIND)
print(" ", KEY)
print(" ", INSTRUCTIONS)
print(" ", PROTOCOL)
print("\nANNOTATE THE BLINDED FILE FIRST. DO NOT OPEN THE KEY.")
