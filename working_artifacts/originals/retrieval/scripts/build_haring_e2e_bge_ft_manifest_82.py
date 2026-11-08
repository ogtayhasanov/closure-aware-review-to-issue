# ============================================================
# BUILD HÄRING 82-CASE BGE-FT END-TO-END MANIFEST
# ============================================================
#
# READ-ONLY inputs:
#   C:\Users\Ogtay\Downloads\haring_verified_tmp\
#       ICSE2021-Coding - Resolved.csv
#       df_firefox_issues_android.csv
#       df_vlc_issues.csv
#       df_nextcloud_issues.csv
#
#   C:\Users\Ogtay\Downloads\haring_bge_ft_modal_results.zip
#
# OUTPUTS:
#   C:\Users\Ogtay\Downloads\haring_e2e_manifest\
#       haring_e2e_bge_ft_manifest_82.csv
#       firefox_history_to_resolve.csv
#       nextcloud_to_enrich.csv
#       vlc_needs_manual_review.csv
#       haring_e2e_manifest_summary.json
#
# This script performs NO model inference, NO API calls, NO generation.
# ============================================================

from pathlib import Path
import zipfile
import json
import re
import ast

import numpy as np
import pandas as pd


DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
ROOT = DOWNLOADS / "haring_verified_tmp"
RESULT_ZIP = DOWNLOADS / "haring_bge_ft_modal_results.zip"
OUT = DOWNLOADS / "haring_e2e_manifest"
OUT.mkdir(parents=True, exist_ok=True)

MODEL = "BGE-FT-E2-NOPREFIX-TITLE"

APP_PACKAGE = {
    "Firefox": "org.mozilla.firefox",
    "VLC": "org.videolan.vlc",
    "Nextcloud": "com.nextcloud.client",
}

EXPECTED_POSITIVE_QUERIES = {
    "Firefox": 28,
    "VLC": 21,
    "Nextcloud": 33,
}

# From the already completed full-corpus BGE-FT evaluation:
EXPECTED_FT_H1_HITS = {
    "Firefox": 3,
    "VLC": 5,
    "Nextcloud": 1,
}

CORPUS_CONFIG = {
    "Firefox": {
        "path": ROOT / "df_firefox_issues_android.csv",
        "raw_rows": 29941,
        "id": "id",
        "title": "summary",
        "body": "description",
    },
    "VLC": {
        "path": ROOT / "df_vlc_issues.csv",
        "raw_rows": 553,
        "id": "id",
        "title": "summary",
        "body": "description",
    },
    "Nextcloud": {
        "path": ROOT / "df_nextcloud_issues.csv",
        "raw_rows": 2462,
        "id": "id",
        "title": "title",
        "body": "body",
    },
}


def clean(x):
    return "" if pd.isna(x) else str(x).strip()


def norm_id(x):
    if pd.isna(x):
        return ""
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))
    s = str(x).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


def bool_value(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "1", "yes", "y", "relevant"}:
        return True
    if s in {"false", "0", "no", "n", "irrelevant"}:
        return False
    raise ValueError(f"Cannot interpret fitting_issue value: {x!r}")


def parse_label_names(x):
    """Best-effort extraction of GitHub label names; never used as ground truth."""
    s = clean(x)
    if not s:
        return []
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, list):
            names = []
            for item in obj:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]).strip())
            return names
    except Exception:
        pass

    # Fallback for slightly malformed repr strings.
    return re.findall(r"""['"]name['"]\s*:\s*['"]([^'"]+)['"]""", s)


def vlc_closure(status, resolution):
    """
    Conservative deterministic mapping.
    Only unambiguous Trac resolution values are auto-assigned.
    """
    st = clean(status).lower()
    res = clean(resolution).lower()

    if st != "closed":
        return "OPEN", "AUTO_HIGH", f"VLC status={st or '<missing>'}"

    if res == "fixed":
        return "RESOLVED", "AUTO_HIGH", "VLC resolution=fixed"
    if res == "duplicate":
        return "REDIRECTED", "AUTO_HIGH", "VLC resolution=duplicate"
    if res in {"wontfix", "invalid", "notvlc"}:
        return "REJECTED", "AUTO_HIGH", f"VLC resolution={res}"

    if res == "incomplete":
        return (
            "NEEDS_MANUAL",
            "MANUAL",
            "VLC resolution=incomplete; likely abandonment/insufficient information, verify manually",
        )
    if res == "worksforme":
        return (
            "NEEDS_MANUAL",
            "MANUAL",
            "VLC resolution=worksforme; do not force into REJECTED without checking context",
        )

    return (
        "NEEDS_MANUAL",
        "MANUAL",
        f"VLC closed issue with unresolved/unknown resolution={res or '<missing>'}",
    )


# ------------------------------------------------------------
# 1. Validate inputs
# ------------------------------------------------------------

required_paths = [
    ROOT / "ICSE2021-Coding - Resolved.csv",
    RESULT_ZIP,
] + [cfg["path"] for cfg in CORPUS_CONFIG.values()]

missing = [str(p) for p in required_paths if not p.exists()]
if missing:
    raise FileNotFoundError(
        "Missing required input(s):\n  " + "\n  ".join(missing)
    )

# ------------------------------------------------------------
# 2. Read Häring coding and identify the 82 known-positive reviews
# ------------------------------------------------------------

coding_path = ROOT / "ICSE2021-Coding - Resolved.csv"
coding = pd.read_csv(coding_path, low_memory=False)

required_coding_cols = {
    "app", "user_feedback_id", "issue_id", "fitting_issue"
}
absent = sorted(required_coding_cols - set(coding.columns))
if absent:
    raise KeyError(f"Coding CSV missing columns: {absent}")

package_to_app = {v: k for k, v in APP_PACKAGE.items()}
coding = coding[coding["app"].astype(str).isin(package_to_app)].copy()
coding["_app_name"] = coding["app"].astype(str).map(package_to_app)
coding["_query_id"] = coding["user_feedback_id"].map(norm_id)
coding["_issue_id"] = coding["issue_id"].map(norm_id)
coding["_relevant"] = coding["fitting_issue"].map(bool_value)

if len(coding) != 450:
    raise AssertionError(
        f"Expected 450 non-Signal Häring judgments, got {len(coding)}."
    )

pair_counts = coding.groupby(["_app_name", "_query_id"]).size()
if len(pair_counts) != 150 or not (pair_counts == 3).all():
    raise AssertionError(
        "Expected exactly 150 reviews with 3 original Häring judgments each."
    )

positive = coding[coding["_relevant"]].copy()

gold_series = (
    positive.groupby(["_app_name", "_query_id"])["_issue_id"]
    .agg(lambda s: tuple(dict.fromkeys(map(str, s))))
)

positive_query_keys = set(gold_series.index)

observed_counts = {}
for app in APP_PACKAGE:
    observed_counts[app] = sum(1 for a, _ in positive_query_keys if a == app)

if observed_counts != EXPECTED_POSITIVE_QUERIES:
    raise AssertionError(
        f"Known-positive subset mismatch. Expected {EXPECTED_POSITIVE_QUERIES}, "
        f"got {observed_counts}."
    )

if len(positive_query_keys) != 82:
    raise AssertionError(
        f"Expected 82 known-positive reviews, got {len(positive_query_keys)}."
    )

# Review text: prefer coding file because it is exactly tied to the published judgments.
if "user_feedback" in coding.columns:
    review_lookup = (
        coding.groupby(["_app_name", "_query_id"])["user_feedback"]
        .first()
        .map(clean)
        .to_dict()
    )
else:
    review_lookup = {}

# ------------------------------------------------------------
# 3. Read the VALIDATED Modal top-3 output and select BGE-FT rank 1
# ------------------------------------------------------------

with zipfile.ZipFile(RESULT_ZIP) as zf:
    names = set(zf.namelist())
    if "bge_modal_top3_all_pairs.csv" not in names:
        raise FileNotFoundError(
            "Result ZIP lacks bge_modal_top3_all_pairs.csv"
        )
    if "corpus_validation.csv" not in names:
        raise FileNotFoundError(
            "Result ZIP lacks corpus_validation.csv"
        )

    with zf.open("bge_modal_top3_all_pairs.csv") as f:
        retrieved = pd.read_csv(f, low_memory=False)

    with zf.open("corpus_validation.csv") as f:
        corpus_validation = pd.read_csv(f, low_memory=False)

# Reject an old/bad retrieval ZIP.
expected_candidate_counts = {
    "Firefox": 29941,
    "VLC": 553,
    # raw Nextcloud=2462, evaluator drops 100 duplicate IDs -> 2362 candidates
    "Nextcloud": 2362,
}
got_candidate_counts = dict(
    zip(
        corpus_validation["app"].astype(str),
        corpus_validation["candidate_bug_reports_used"].astype(int),
    )
)
if got_candidate_counts != expected_candidate_counts:
    raise AssertionError(
        "This is not the validated exact-corpus BGE retrieval ZIP. "
        f"Expected candidate counts {expected_candidate_counts}, "
        f"got {got_candidate_counts}."
    )

required_retrieval_cols = {
    "app", "model", "query_id", "review_text", "rank",
    "candidate_issue_id", "candidate_title", "candidate_body", "score",
}
absent = sorted(required_retrieval_cols - set(retrieved.columns))
if absent:
    raise KeyError(f"Retrieval CSV missing columns: {absent}")

ft = retrieved[retrieved["model"].astype(str) == MODEL].copy()
ft["rank"] = pd.to_numeric(ft["rank"], errors="raise").astype(int)
ft["query_id"] = ft["query_id"].map(norm_id)
ft["candidate_issue_id"] = ft["candidate_issue_id"].map(norm_id)

if len(ft) != 450:
    raise AssertionError(
        f"Expected 450 BGE-FT top-3 rows (150 x 3), got {len(ft)}."
    )

rank1 = ft[ft["rank"] == 1].copy()

if len(rank1) != 150:
    raise AssertionError(
        f"Expected exactly 150 BGE-FT rank-1 rows, got {len(rank1)}."
    )

if rank1.duplicated(["app", "query_id"]).any():
    raise AssertionError("Duplicate BGE-FT rank-1 app/query rows found.")

# Keep only the 82 queries with >=1 known Häring-positive issue.
rank1["_key"] = list(zip(rank1["app"].astype(str), rank1["query_id"].astype(str)))
rank1_82 = rank1[rank1["_key"].isin(positive_query_keys)].copy()

if len(rank1_82) != 82:
    raise AssertionError(
        f"Expected 82 BGE-FT rank-1 rows on known-positive queries, got {len(rank1_82)}."
    )

# ------------------------------------------------------------
# 4. Load exact issue corpora and join metadata for each retrieved top-1 issue
# ------------------------------------------------------------

corpora = {}

for app, cfg in CORPUS_CONFIG.items():
    df = pd.read_csv(cfg["path"], low_memory=False)

    if len(df) != cfg["raw_rows"]:
        raise AssertionError(
            f"{app}: expected {cfg['raw_rows']:,} raw rows, got {len(df):,}."
        )

    if cfg["id"] not in df.columns:
        raise KeyError(f"{app}: missing ID column {cfg['id']!r}")

    df = df.copy()
    df["_issue_id"] = df[cfg["id"]].map(norm_id)

    # Match the retrieval evaluator's duplicate policy.
    duplicate_ids = int(df["_issue_id"].duplicated().sum())
    df = df.drop_duplicates("_issue_id", keep="first").reset_index(drop=True)

    corpora[app] = {
        "df": df,
        "lookup": df.set_index("_issue_id", drop=False),
        "duplicate_ids_dropped": duplicate_ids,
    }

# ------------------------------------------------------------
# 5. Build the 82-row manifest
# ------------------------------------------------------------

rows = []

for r in rank1_82.itertuples(index=False):
    app = str(r.app)
    qid = str(r.query_id)
    issue_id = str(r.candidate_issue_id)

    gold_ids = tuple(gold_series.loc[(app, qid)])
    retrieval_correct = issue_id in set(gold_ids)

    lookup = corpora[app]["lookup"]
    if issue_id not in lookup.index:
        raise AssertionError(
            f"{app}/{qid}: BGE-FT top-1 issue {issue_id} missing from exact corpus."
        )

    issue = lookup.loc[issue_id]
    if isinstance(issue, pd.DataFrame):
        # Should not occur after duplicate dropping.
        issue = issue.iloc[0]

    review_text = clean(getattr(r, "review_text", ""))
    if not review_text:
        review_text = review_lookup.get((app, qid), "")

    base = {
        "app": app,
        "tracker": {
            "Firefox": "Bugzilla",
            "VLC": "Trac",
            "Nextcloud": "GitHub",
        }[app],
        "query_id": qid,
        "review_text": review_text,
        "gold_issue_ids": ";".join(gold_ids),
        "n_known_positive_issues": len(gold_ids),
        "bge_model": MODEL,
        "bge_top1_issue_id": issue_id,
        "bge_top1_score": float(r.score),
        "retrieval_correct_at_1": bool(retrieval_correct),
        "issue_title": clean(issue.get(CORPUS_CONFIG[app]["title"], "")),
        "issue_body": clean(issue.get(CORPUS_CONFIG[app]["body"], "")),
        "closure_class": "",
        "closure_class_source": "",
        "closure_evidence": "",
        "needs_external_enrichment": False,
        "needs_manual_closure_review": False,
    }

    if app == "VLC":
        status = clean(issue.get("status", ""))
        resolution = clean(issue.get("resolution", ""))

        cc, src, evidence = vlc_closure(status, resolution)

        base.update({
            "status": status,
            "resolution": resolution,
            "history": "",
            "labels": "",
            "closed_at": "",
            "issue_url": "",
            "closure_class": cc,
            "closure_class_source": src,
            "closure_evidence": evidence,
            "needs_external_enrichment": False,
            "needs_manual_closure_review": (cc == "NEEDS_MANUAL"),
        })

    elif app == "Firefox":
        status = clean(issue.get("status", ""))
        history = clean(issue.get("history", ""))
        last_resolved = clean(issue.get("cf_last_resolved", ""))

        if status in {"NEW", "REOPENED", "UNCONFIRMED", "ASSIGNED"}:
            closure_class = "OPEN"
            source = "AUTO_HIGH"
            evidence = f"Bugzilla status={status}"
            manual = False
        else:
            # RESOLVED/VERIFIED require the historical resolution reason.
            closure_class = "NEEDS_FIREFOX_HISTORY"
            source = "LOCAL_HISTORY"
            evidence = (
                f"Bugzilla status={status}; inspect history for resolution reason"
            )
            manual = True

        base.update({
            "status": status,
            "resolution": "",
            "history": history,
            "cf_last_resolved": last_resolved,
            "labels": "",
            "closed_at": "",
            "issue_url": f"https://bugzilla.mozilla.org/show_bug.cgi?id={issue_id}",
            "closure_class": closure_class,
            "closure_class_source": source,
            "closure_evidence": evidence,
            "needs_external_enrichment": False,
            "needs_manual_closure_review": manual,
        })

    elif app == "Nextcloud":
        state = clean(issue.get("state", ""))
        labels_raw = clean(issue.get("labels", ""))
        label_names = parse_label_names(labels_raw)
        closed_at = clean(issue.get("closed_at", ""))
        html_url = clean(issue.get("html_url", ""))

        if state.lower() == "open":
            closure_class = "OPEN"
            source = "AUTO_HIGH"
            evidence = "GitHub state=open"
            enrich = False
            manual = False
        else:
            closure_class = "NEEDS_NEXTCLOUD_ENRICHMENT"
            source = "GITHUB_EVENTS_COMMENTS_REQUIRED"
            evidence = (
                "GitHub state=closed; local snapshot lacks reliable closure reason. "
                f"Labels={label_names}"
            )
            enrich = True
            manual = True

        base.update({
            "status": state,
            "resolution": "",
            "history": "",
            "labels": ";".join(label_names),
            "closed_at": closed_at,
            "issue_url": html_url,
            "closure_class": closure_class,
            "closure_class_source": source,
            "closure_evidence": evidence,
            "needs_external_enrichment": enrich,
            "needs_manual_closure_review": manual,
        })

    rows.append(base)

manifest = pd.DataFrame(rows).sort_values(
    ["app", "query_id"],
    kind="stable"
).reset_index(drop=True)

# ------------------------------------------------------------
# 6. Hard checks against the already observed BGE-FT H@1 result
# ------------------------------------------------------------

manifest_counts = manifest.groupby("app").size().astype(int).to_dict()
if manifest_counts != EXPECTED_POSITIVE_QUERIES:
    raise AssertionError(
        f"Manifest app counts wrong: expected {EXPECTED_POSITIVE_QUERIES}, "
        f"got {manifest_counts}."
    )

observed_h1_hits = (
    manifest.groupby("app")["retrieval_correct_at_1"].sum().astype(int).to_dict()
)

if observed_h1_hits != EXPECTED_FT_H1_HITS:
    raise AssertionError(
        "BGE-FT H@1 hit counts do not match the already validated full-rank run. "
        f"Expected {EXPECTED_FT_H1_HITS}, got {observed_h1_hits}. "
        "Refusing to build an inconsistent E2E manifest."
    )

if int(manifest["retrieval_correct_at_1"].sum()) != 9:
    raise AssertionError("Expected exactly 9/82 BGE-FT rank-1 known-positive hits.")

# ------------------------------------------------------------
# 7. Save focused queues + summary
# ------------------------------------------------------------

manifest_path = OUT / "haring_e2e_bge_ft_manifest_82.csv"
manifest.to_csv(manifest_path, index=False)

firefox_queue = manifest[
    (manifest["app"] == "Firefox")
    & (manifest["closure_class"] == "NEEDS_FIREFOX_HISTORY")
].copy()
firefox_queue.to_csv(
    OUT / "firefox_history_to_resolve.csv",
    index=False,
)

nextcloud_queue = manifest[
    (manifest["app"] == "Nextcloud")
    & (manifest["closure_class"] == "NEEDS_NEXTCLOUD_ENRICHMENT")
].copy()
nextcloud_queue.to_csv(
    OUT / "nextcloud_to_enrich.csv",
    index=False,
)

vlc_manual = manifest[
    (manifest["app"] == "VLC")
    & (manifest["closure_class"] == "NEEDS_MANUAL")
].copy()
vlc_manual.to_csv(
    OUT / "vlc_needs_manual_review.csv",
    index=False,
)

closure_counts = (
    manifest.groupby(["app", "closure_class"])
    .size()
    .rename("n")
    .reset_index()
)

summary = {
    "manifest_rows": int(len(manifest)),
    "positive_query_counts": manifest_counts,
    "bge_ft_h1_hits_by_app": observed_h1_hits,
    "bge_ft_h1_hits_total": int(manifest["retrieval_correct_at_1"].sum()),
    "bge_ft_h1_rate_total": float(manifest["retrieval_correct_at_1"].mean()),
    "closure_counts": closure_counts.to_dict("records"),
    "firefox_history_cases": int(len(firefox_queue)),
    "nextcloud_enrichment_cases": int(len(nextcloud_queue)),
    "vlc_manual_cases": int(len(vlc_manual)),
    "corpus_duplicate_ids_dropped": {
        app: int(corpora[app]["duplicate_ids_dropped"])
        for app in corpora
    },
    "guard": (
        "This manifest is the 82-query known-positive Häring subset with "
        "frozen BGE-FT epoch-2 top-1 retrieval. Closure classification is "
        "conservative; Firefox closed cases and Nextcloud closed cases are "
        "not force-mapped without evidence."
    ),
}

summary_path = OUT / "haring_e2e_manifest_summary.json"
summary_path.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\n" + "=" * 100)
print("HÄRING BGE-FT E2E MANIFEST BUILT")
print("=" * 100)
print("Rows:", len(manifest))
print("Per app:", manifest_counts)
print("BGE-FT correct@1:", observed_h1_hits, "TOTAL=9/82")
print("\nClosure counts:")
print(closure_counts.to_string(index=False))
print("\nQueues:")
print(" Firefox history:", len(firefox_queue))
print(" Nextcloud enrichment:", len(nextcloud_queue))
print(" VLC manual:", len(vlc_manual))
print("\nSaved:")
print(" ", manifest_path)
print(" ", OUT / "firefox_history_to_resolve.csv")
print(" ", OUT / "nextcloud_to_enrich.csv")
print(" ", OUT / "vlc_needs_manual_review.csv")
print(" ", summary_path)
