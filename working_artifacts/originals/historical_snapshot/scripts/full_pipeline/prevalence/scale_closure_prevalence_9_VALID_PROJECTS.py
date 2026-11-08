#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
SCALE CLOSURE PREVALENCE TO 10 PROJECTS

Selection rule (frozen before seeing expanded results)
-------------------------------------------------------
Use the ten distinct software projects already present elsewhere in the study:

  Existing full-snapshot tracker corpora:
    - Firefox        (Bugzilla)
    - VLC            (Trac)

  Full GitHub repositories fetched now:
    - Nextcloud      nextcloud/android
    - Signal         signalapp/Signal-Android
    - AnkiDroid      ankidroid/Anki-Android
    - K-9 Mail       thunderbird/thunderbird-android
    - Brave          brave/brave-browser
    - Dolphin        dolphin-emu/dolphin
    - Jitsi          jitsi/jitsi-meet
    - PPSSPP         hrydgard/ppsspp

This rule avoids choosing repositories after seeing prevalence results:
every project is already a training, candidate-pool, or external-evaluation
project in the manuscript.

Method
------
- Firefox and VLC reuse the already completed verified full-snapshot prevalence
  audit from the Modal volume.
- The eight GitHub projects are fetched from GitHub's GraphQL API using the
  repository `issues` connection with `states:CLOSED` and cursor pagination.
- Pull requests are excluded by construction because the GraphQL `issues`
  connection returns Issue objects rather than the mixed REST /issues feed.
- GitHub Level-1 mapping is the same conservative mapping used in the manuscript:
    REDIRECTED > explicit REJECTED > ABANDONED >
    state_reason=not_planned > state_reason=completed
- Closed issues with no classifiable state_reason and no strong label remain
  UNCLASSIFIED_CLOSED; they are never silently counted as resolved.
- Headline prevalence is a conservative lower bound:
    (REJECTED + ABANDONED + REDIRECTED) / ALL CLOSED ISSUES

Requirements
------------
  python -m pip install -U requests pandas

A GitHub token is required for GraphQL pagination. The script reads GITHUB_TOKEN /
GH_TOKEN, or asks for one interactively. A token is needed for practical
pagination across large repositories.

Outputs
-------
C:\Users\Ogtay\Downloads\closure_prevalence_10_projects_20260808\
  github_raw\*.jsonl
  github_issue_level_classifications.csv
  project_closure_prevalence_10.csv
  tracker_closure_prevalence_10.csv
  pooled_summary_10.json
  selection_protocol.json
  RUN_SUMMARY.txt

The script is resumable: each fully fetched GitHub repository is cached.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import getpass
import json
import math
import os
import re
import subprocess
import time
import zipfile

import pandas as pd
import requests


# ---------------------------------------------------------------------
# Frozen project selection
# ---------------------------------------------------------------------

DOWNLOADS = Path(r"C:\Users\Ogtay\Downloads")
OUT = DOWNLOADS / "closure_prevalence_10_projects_20260808"
RAW = OUT / "github_raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

BASE_AUDIT_ZIP = DOWNLOADS / "closure_prevalence_audit_results.zip"

GITHUB_PROJECTS = {
    "Nextcloud": "nextcloud/android",
    "Signal": "signalapp/Signal-Android",
    "AnkiDroid": "ankidroid/Anki-Android",
    "K-9 Mail": "thunderbird/thunderbird-android",
    "Brave": "brave/brave-browser",
    # Dolphin Emulator is intentionally NOT collected through GitHub:
    # dolphin-emu/dolphin has no GitHub Issues corpus; the project uses its
    # separate Redmine tracker. Treating GitHub's empty IssueConnection as a
    # zero-issue project would be invalid.
    "Jitsi": "jitsi/jitsi-meet",
    "PPSSPP": "hrydgard/ppsspp",
}

BASE_PROJECTS_REQUIRED = {"Firefox", "VLC"}

SELECTION_NOTE = (
    "Ten projects were selected before expanded prevalence was inspected: "
    "Firefox, VLC, Nextcloud, Signal, AnkiDroid, K-9 Mail, Brave, Dolphin "
    "Emulator, Jitsi, and PPSSPP. Dolphin is excluded from the automated "
    "prevalence aggregation because its official issue corpus is hosted on a "
    "separate Redmine tracker rather than GitHub Issues; the GitHub repository "
    "has an empty IssueConnection. The resulting automated audit therefore "
    "contains nine valid full-corpus projects, without substituting a new "
    "project after observing results."
)


# ---------------------------------------------------------------------
# Taxonomy: identical conservative GitHub Level-1 semantics
# ---------------------------------------------------------------------

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
    "unconfirmed", "insufficient information", "insufficient-information",
    "no response", "no-response",
)

UPSTREAM_PATTERNS = (
    "upstream", "third-party", "third party",
)

NONRESOLVED = {"REJECTED", "ABANDONED", "REDIRECTED"}
CLASSIFIED = {"RESOLVED", "REJECTED", "ABANDONED", "REDIRECTED"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean(x):
    if x is None:
        return ""
    return str(x).strip()


def label_names(issue):
    out = []
    for item in issue.get("labels") or []:
        if isinstance(item, dict):
            name = clean(item.get("name"))
        else:
            name = clean(item)
        if name:
            out.append(re.sub(r"\s+", " ", name.lower()))
    return out


def classify_github(issue):
    if clean(issue.get("state")).lower() != "closed":
        raise ValueError("Expanded audit expects closed issues only.")

    reason = clean(issue.get("state_reason")).lower().replace("-", "_")
    labels = label_names(issue)

    # REDIRECTED first.
    if reason == "duplicate" or any("duplicate" in lab for lab in labels):
        return "REDIRECTED", "DUPLICATE", "duplicate state_reason/label"

    # Explicit rejections override generic completed.
    for lab in labels:
        if any(p in lab for p in REJECTED_PATTERNS):
            return "REJECTED", "EXPLICIT_REJECTION", f"rejection label={lab}"

    # Abandonment signals.
    for lab in labels:
        if any(p in lab for p in STALE_PATTERNS):
            return "ABANDONED", "STALE", f"stale/inactive label={lab}"

    for lab in labels:
        if any(p in lab for p in NEEDS_INFO_PATTERNS):
            return "ABANDONED", "NEEDS_INFO", f"needs-info/cannot-reproduce label={lab}"

    for lab in labels:
        if any(p in lab for p in UPSTREAM_PATTERNS):
            return "ABANDONED", "UPSTREAM", f"upstream label={lab}"

    if reason == "not_planned":
        return "REJECTED", "NOT_PLANNED", "state_reason=not_planned"

    if reason == "completed":
        return "RESOLVED", "COMPLETED", "state_reason=completed"

    return (
        "UNCLASSIFIED_CLOSED",
        "",
        f"closed issue lacks classifiable state_reason; value={reason or '<missing>'}",
    )


# ---------------------------------------------------------------------
# Existing Firefox/VLC full-snapshot result
# ---------------------------------------------------------------------

def ensure_base_audit_zip():
    if BASE_AUDIT_ZIP.exists():
        return

    remote = "closure_prevalence_audit/closure_prevalence_audit_results.zip"
    commands = [
        [
            "modal", "volume", "get", "-e", "main",
            "splade-data", remote, str(BASE_AUDIT_ZIP),
        ],
        [
            "modal", "volume", "get", "--force",
            "splade-data", remote, str(BASE_AUDIT_ZIP),
        ],
    ]

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    errors = []
    for cmd in commands:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

        # Modal on Windows can finish the file and then choke while printing ✓.
        if BASE_AUDIT_ZIP.exists():
            try:
                with zipfile.ZipFile(BASE_AUDIT_ZIP) as z:
                    z.testzip()
                return
            except zipfile.BadZipFile:
                BASE_AUDIT_ZIP.unlink(missing_ok=True)

        errors.append(
            "COMMAND: " + " ".join(cmd)
            + "\nSTDOUT:\n" + stdout
            + "\nSTDERR:\n" + stderr
        )

    raise RuntimeError(
        "Could not download the completed three-project prevalence archive.\n\n"
        + "\n\n".join(errors)
    )


def load_base_project_rows():
    ensure_base_audit_zip()

    with zipfile.ZipFile(BASE_AUDIT_ZIP) as z:
        matches = [
            name for name in z.namelist()
            if name.endswith("project_closure_prevalence.csv")
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one project_closure_prevalence.csv in {BASE_AUDIT_ZIP}; "
                f"found {matches}"
            )
        with z.open(matches[0]) as f:
            df = pd.read_csv(f)

    # Preserve only Firefox/VLC. Nextcloud will be re-fetched from GitHub under
    # the same current-API protocol as the other seven GitHub projects.
    df = df[df["project"].isin(BASE_PROJECTS_REQUIRED)].copy()
    if set(df["project"]) != BASE_PROJECTS_REQUIRED:
        raise AssertionError(
            f"Base audit does not contain both {BASE_PROJECTS_REQUIRED}; "
            f"got {set(df['project'])}"
        )

    # Standardize the ORIGINAL prevalence-audit schema to the expanded schema.
    #
    # The original file uses:
    #   closed_issues
    #   nonresolved_share_classifiable
    #   unclassified_closed_rate
    #
    # Earlier versions of this expansion script incorrectly expected shorter
    # aliases (closed / nonresolved_share_among_classifiable /
    # unclassified_rate). Resolve by explicit schema aliases and fail loudly
    # if neither spelling exists.
    def pick(record, *names):
        for name in names:
            if name in record and pd.notna(record[name]):
                return record[name]
        raise KeyError(
            f"None of {names} found in original prevalence row. "
            f"Available columns={sorted(record.keys())}"
        )

    rows = []
    for r in df.to_dict("records"):
        closed = int(pick(r, "closed_issues", "closed"))
        classifiable = int(pick(r, "classifiable_closed"))
        resolved = int(pick(r, "RESOLVED"))
        rejected = int(pick(r, "REJECTED"))
        abandoned = int(pick(r, "ABANDONED"))
        redirected = int(pick(r, "REDIRECTED"))
        unclassified = int(pick(r, "UNCLASSIFIED_CLOSED"))
        nonresolved = int(pick(r, "confirmed_nonresolved"))

        # Hard consistency checks against the verified base audit.
        if closed != classifiable + unclassified:
            raise AssertionError(
                f"{r['project']}: closed != classifiable + unclassified "
                f"({closed} != {classifiable} + {unclassified})"
            )
        if nonresolved != rejected + abandoned + redirected:
            raise AssertionError(
                f"{r['project']}: nonresolved category sum mismatch"
            )
        if classifiable != resolved + nonresolved:
            raise AssertionError(
                f"{r['project']}: classifiable category sum mismatch"
            )

        rows.append({
            "project": r["project"],
            "tracker": r.get(
                "tracker",
                "Bugzilla" if r["project"] == "Firefox" else "Trac",
            ),
            "source": "verified_existing_full_snapshot",
            "snapshot_time_utc": "",
            "closed": closed,
            "classifiable_closed": classifiable,
            "RESOLVED": resolved,
            "REJECTED": rejected,
            "ABANDONED": abandoned,
            "REDIRECTED": redirected,
            "UNCLASSIFIED_CLOSED": unclassified,
            "confirmed_nonresolved": nonresolved,
            "confirmed_nonresolved_lower_bound_all_closed": float(
                pick(r, "confirmed_nonresolved_lower_bound_all_closed")
            ),
            "nonresolved_share_among_classifiable": float(
                pick(
                    r,
                    "nonresolved_share_classifiable",
                    "nonresolved_share_among_classifiable",
                )
            ),
            "unclassified_rate": float(
                pick(r, "unclassified_closed_rate", "unclassified_rate")
            ),
        })

    # Reproduce the already verified base counts before touching GitHub.
    expected = {
        "Firefox": {"closed": 25060, "confirmed_nonresolved": 13399},
        "VLC": {"closed": 356, "confirmed_nonresolved": 171},
    }
    by_project = {row["project"]: row for row in rows}
    for project, exp in expected.items():
        got = by_project[project]
        if got["closed"] != exp["closed"]:
            raise AssertionError(
                f"{project}: expected closed={exp['closed']}, got {got['closed']}"
            )
        if got["confirmed_nonresolved"] != exp["confirmed_nonresolved"]:
            raise AssertionError(
                f"{project}: expected confirmed_nonresolved="
                f"{exp['confirmed_nonresolved']}, "
                f"got {got['confirmed_nonresolved']}"
            )

    print(
        "Verified base prevalence reproduced: "
        "Firefox 13,399/25,060; VLC 171/356."
    )
    return rows


# ---------------------------------------------------------------------
# GitHub fetching
# ---------------------------------------------------------------------

def get_token():
    token = (
        os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip()
    )
    if token:
        return token

    token = getpass.getpass(
        "GitHub token not found in GITHUB_TOKEN/GH_TOKEN. "
        "Paste token here (hidden; recommended for full pagination): "
    ).strip()

    if not token:
        raise SystemExit(
            "A GitHub token is required for this 8-repository full-corpus pull."
        )
    return token


def session_for(token):
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TOSEM-closure-prevalence-audit-2026-08-08",
    })
    return s


GRAPHQL_URL = "https://api.github.com/graphql"

GRAPHQL_QUERY = r"""
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100,
      after: $cursor,
      states: CLOSED,
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      totalCount
      pageInfo {
        endCursor
        hasNextPage
      }
      nodes {
        id
        databaseId
        number
        title
        state
        stateReason
        closedAt
        url
        labels(first: 100) {
          nodes {
            name
          }
        }
      }
    }
  }
}
"""


def cache_paths(project):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", project)
    return (
        RAW / f"{safe}.graphql.jsonl",
        RAW / f"{safe}.graphql.checkpoint.json",
        RAW / f"{safe}.graphql.complete.json",
    )


def graphql_request(session, variables):
    last_exc = None
    for attempt in range(6):
        try:
            response = session.post(
                GRAPHQL_URL,
                json={"query": GRAPHQL_QUERY, "variables": variables},
                timeout=60,
            )
        except Exception as exc:
            last_exc = exc
            time.sleep(min(30, 2 ** attempt))
            continue

        if response.status_code in {500, 502, 503, 504}:
            time.sleep(min(30, 2 ** attempt))
            continue

        if response.status_code == 403:
            raise RuntimeError(
                "GitHub GraphQL returned 403. "
                f"remaining={response.headers.get('X-RateLimit-Remaining')}, "
                f"reset={response.headers.get('X-RateLimit-Reset')}"
            )

        response.raise_for_status()
        payload = response.json()

        if payload.get("errors"):
            raise RuntimeError(
                "GitHub GraphQL errors: "
                + json.dumps(payload["errors"], ensure_ascii=False)
            )

        return payload

    raise RuntimeError(f"GitHub GraphQL request failed: {last_exc}")


def graphql_node_to_issue(node):
    """
    Convert the GraphQL Issue shape to the small REST-like shape used by the
    frozen classifier. This does NOT invent metadata.
    """
    labels = [
        {"name": clean(item.get("name"))}
        for item in ((node.get("labels") or {}).get("nodes") or [])
        if clean(item.get("name"))
    ]
    return {
        "id": node.get("databaseId") if node.get("databaseId") is not None else node.get("id"),
        "node_id": node.get("id"),
        "number": node.get("number"),
        "title": clean(node.get("title")),
        "state": clean(node.get("state")).lower(),
        "state_reason": clean(node.get("stateReason")).lower(),
        "closed_at": clean(node.get("closedAt")),
        "html_url": clean(node.get("url")),
        "labels": labels,
    }


def fetch_all_closed_issues(project, repo, session):
    """
    Cursor-paginate the repository's IssueConnection to completion.

    This replaces REST page-number pagination. It is resumable at the exact
    GraphQL cursor, so a network/API interruption does not restart a large repo.
    """
    jsonl_path, checkpoint_path, done_path = cache_paths(project)

    if jsonl_path.exists() and done_path.exists():
        meta = json.loads(done_path.read_text(encoding="utf-8"))
        if meta.get("repo") == repo and meta.get("complete") is True:
            issues = [
                json.loads(line)
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if len(issues) != int(meta["closed_issue_total"]):
                raise AssertionError(
                    f"{project}: completed cache count mismatch "
                    f"{len(issues)} != {meta['closed_issue_total']}"
                )
            print(
                f"{project}: using cached complete GraphQL pull "
                f"({len(issues):,} closed issues)."
            )
            return issues, meta

    # Ignore/delete the old REST partial cache from the failed page=100 run.
    old_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", project)
    for old_name in (
        RAW / f"{old_safe}.jsonl",
        RAW / f"{old_safe}.complete.json",
    ):
        if old_name.exists():
            old_name.unlink()

    owner, name = repo.split("/", 1)

    cursor = None
    expected_total = None
    observed_total_min = 0
    observed_total_max = 0
    fetched = 0
    request_count = 0

    if checkpoint_path.exists() and jsonl_path.exists():
        cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if cp.get("repo") == repo:
            cursor = cp.get("next_cursor")
            expected_total = cp.get("closed_issue_total")
            observed_total_min = int(cp.get("observed_total_min", expected_total or 0))
            observed_total_max = int(cp.get("observed_total_max", expected_total or 0))
            fetched = int(cp.get("fetched", 0))
            request_count = int(cp.get("api_requests", 0))

            line_count = sum(
                1
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if line_count != fetched:
                raise AssertionError(
                    f"{project}: checkpoint says fetched={fetched}, "
                    f"but cache has {line_count} rows"
                )

            print(
                f"{project}: resuming GraphQL cursor after "
                f"{fetched:,}/{expected_total or '?'} issues."
            )
        else:
            checkpoint_path.unlink(missing_ok=True)
            jsonl_path.unlink(missing_ok=True)

    while True:
        payload = graphql_request(
            session,
            {"owner": owner, "name": name, "cursor": cursor},
        )
        repository = (payload.get("data") or {}).get("repository")
        if repository is None:
            raise RuntimeError(f"GitHub repository not found: {repo}")

        conn = repository["issues"]
        total = int(conn["totalCount"])

        if expected_total is None:
            expected_total = total
            observed_total_min = total
            observed_total_max = total
            print(f"{project}: GitHub reports {expected_total:,} closed issues.")
        else:
            # GitHub is live: issues may close/reopen while a long repository
            # pull is running. A changing totalCount is therefore expected and
            # must not invalidate the entire cursor walk.
            #
            # We record the observed range instead of pretending the API gives
            # transaction-level snapshot isolation.
            if observed_total_min == 0:
                observed_total_min = int(expected_total)
            if observed_total_max == 0:
                observed_total_max = int(expected_total)
            observed_total_min = min(observed_total_min, total)
            observed_total_max = max(observed_total_max, total)
            if total != int(expected_total):
                print(
                    f"{project}: live totalCount changed "
                    f"{expected_total:,} -> {total:,}; continuing cursor walk "
                    f"(observed range {observed_total_min:,}-{observed_total_max:,}).",
                    flush=True,
                )
                expected_total = total

        nodes = conn.get("nodes") or []
        converted = [graphql_node_to_issue(node) for node in nodes]

        with jsonl_path.open("a", encoding="utf-8") as f:
            for issue in converted:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")

        fetched += len(converted)
        request_count += 1

        page_info = conn["pageInfo"]
        has_next = bool(page_info["hasNextPage"])
        next_cursor = page_info.get("endCursor")

        checkpoint = {
            "project": project,
            "repo": repo,
            "complete": False,
            "closed_issue_total": expected_total,
            "observed_total_min": observed_total_min,
            "observed_total_max": observed_total_max,
            "fetched": fetched,
            "next_cursor": next_cursor,
            "api_requests": request_count,
            "updated_at_utc": utc_now(),
        }
        checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2),
            encoding="utf-8",
        )

        if request_count % 25 == 0 or not has_next:
            print(
                f"{project}: fetched={fetched:,}/{expected_total:,}, "
                f"GraphQL pages={request_count}",
                flush=True,
            )

        if not has_next:
            break

        if not next_cursor:
            raise RuntimeError(
                f"{project}: hasNextPage=true but endCursor is empty"
            )
        cursor = next_cursor

    # A live repository is not transactionally frozen during pagination.
    # De-duplicate by repository-local issue number and report the exact number
    # actually observed during this completed cursor traversal.
    raw_issues = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_number = {}
    for issue in raw_issues:
        number = issue.get("number")
        if number is None:
            raise AssertionError(f"{project}: cached issue without number")
        by_number[int(number)] = issue
    unique_issues = [by_number[k] for k in sorted(by_number)]

    duplicate_rows = len(raw_issues) - len(unique_issues)
    observed_count = len(unique_issues)

    # Rewrite cache canonically after de-duplication so future resumes/loads are stable.
    with jsonl_path.open("w", encoding="utf-8") as f:
        for issue in unique_issues:
            f.write(json.dumps(issue, ensure_ascii=False) + "\n")

    meta = {
        "project": project,
        "repo": repo,
        "complete": True,
        "fetched_at_utc": utc_now(),
        "closed_issue_total": observed_count,
        "api_reported_total_at_end": expected_total,
        "observed_total_min": observed_total_min,
        "observed_total_max": observed_total_max,
        "duplicate_rows_removed": duplicate_rows,
        "api_requests": request_count,
        "pagination": "GitHub GraphQL cursor pagination over live repository",
        "snapshot_semantics": (
            "Completed cursor traversal during a bounded collection window; "
            "GitHub totalCount may change as issues close/reopen during collection."
        ),
    }
    done_path.write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    checkpoint_path.unlink(missing_ok=True)

    issues = unique_issues

    print(
        f"{project}: completed live cursor traversal with "
        f"{len(issues):,} unique closed issues observed; "
        f"API totalCount range={observed_total_min:,}-{observed_total_max:,}; "
        f"duplicates_removed={duplicate_rows}.",
        flush=True,
    )

    return issues, meta


# ---------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------

def classify_project(project, repo, issues, meta):
    rows = []
    for issue in issues:
        l1, subtype, evidence = classify_github(issue)
        rows.append({
            "project": project,
            "tracker": "GitHub",
            "repo": repo,
            "issue_number": issue.get("number"),
            "issue_id": issue.get("id"),
            "title": clean(issue.get("title")),
            "state_reason": clean(issue.get("state_reason")),
            "labels": json.dumps(label_names(issue), ensure_ascii=False),
            "closed_at": clean(issue.get("closed_at")),
            "html_url": clean(issue.get("html_url")),
            "l1": l1,
            "subtype": subtype,
            "evidence": evidence,
        })

    frame = pd.DataFrame(rows)
    counts = frame["l1"].value_counts().to_dict()

    closed = len(frame)
    resolved = int(counts.get("RESOLVED", 0))
    rejected = int(counts.get("REJECTED", 0))
    abandoned = int(counts.get("ABANDONED", 0))
    redirected = int(counts.get("REDIRECTED", 0))
    unclassified = int(counts.get("UNCLASSIFIED_CLOSED", 0))
    nonresolved = rejected + abandoned + redirected
    classifiable = resolved + nonresolved

    if closed != classifiable + unclassified:
        raise AssertionError(f"{project}: classification counts do not sum")

    summary = {
        "project": project,
        "tracker": "GitHub",
        "source": repo,
        "snapshot_time_utc": meta["fetched_at_utc"],
        "closed": closed,
        "classifiable_closed": classifiable,
        "RESOLVED": resolved,
        "REJECTED": rejected,
        "ABANDONED": abandoned,
        "REDIRECTED": redirected,
        "UNCLASSIFIED_CLOSED": unclassified,
        "confirmed_nonresolved": nonresolved,
        "confirmed_nonresolved_lower_bound_all_closed": (
            nonresolved / closed if closed else float("nan")
        ),
        "nonresolved_share_among_classifiable": (
            nonresolved / classifiable if classifiable else float("nan")
        ),
        "unclassified_rate": (
            unclassified / closed if closed else float("nan")
        ),
    }

    return frame, summary


def weighted_tracker_summary(project_df):
    rows = []
    for tracker, g in project_df.groupby("tracker", sort=True):
        closed = int(g["closed"].sum())
        classifiable = int(g["classifiable_closed"].sum())
        nonresolved = int(g["confirmed_nonresolved"].sum())
        unclassified = int(g["UNCLASSIFIED_CLOSED"].sum())
        rows.append({
            "tracker": tracker,
            "projects": int(len(g)),
            "closed": closed,
            "classifiable_closed": classifiable,
            "confirmed_nonresolved": nonresolved,
            "UNCLASSIFIED_CLOSED": unclassified,
            "confirmed_nonresolved_lower_bound_all_closed": nonresolved / closed,
            "nonresolved_share_among_classifiable": (
                nonresolved / classifiable if classifiable else float("nan")
            ),
            "unclassified_rate": unclassified / closed,
        })
    return pd.DataFrame(rows)


def main():
    protocol = {
        "created_at_utc": utc_now(),
        "selection_rule": SELECTION_NOTE,
        "selection_frozen_before_expanded_results": True,
        "projects_selected": 10,
        "projects_automatically_analyzed": 9,
        "excluded_selected_project": {
            "project": "Dolphin Emulator",
            "reason": "Official issues are on separate Redmine tracker; GitHub IssueConnection is empty.",
        },
        "tracker_ecosystems": ["Bugzilla", "Trac", "GitHub"],
        "github_repositories": GITHUB_PROJECTS,
        "pull_requests_excluded": True,
        "github_collection": "GraphQL repository issues connection; states=CLOSED; cursor pagination",
        "github_mapping_priority": (
            "REDIRECTED > explicit REJECTED > ABANDONED > "
            "state_reason=not_planned > state_reason=completed"
        ),
        "unmapped_closed_policy": "UNCLASSIFIED_CLOSED",
        "headline_statistic": (
            "(REJECTED + ABANDONED + REDIRECTED) / ALL CLOSED"
        ),
    }
    (OUT / "selection_protocol.json").write_text(
        json.dumps(protocol, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    base_rows = load_base_project_rows()
    token = get_token()
    session = session_for(token)

    issue_frames = []
    project_rows = list(base_rows)

    print("\nFROZEN 10-PROJECT SELECTION")
    print(SELECTION_NOTE)
    print("\nFetching 7 valid full GitHub repositories with GraphQL cursor pagination...\n")

    for project, repo in GITHUB_PROJECTS.items():
        issues, meta = fetch_all_closed_issues(project, repo, session)
        frame, summary = classify_project(project, repo, issues, meta)
        issue_frames.append(frame)
        project_rows.append(summary)

        print(
            f"{project}: closed={summary['closed']:,}; "
            f"nonresolved={summary['confirmed_nonresolved']:,}; "
            f"lower_bound={summary['confirmed_nonresolved_lower_bound_all_closed']:.1%}; "
            f"unclassified={summary['UNCLASSIFIED_CLOSED']:,}"
        )

    issue_level = pd.concat(issue_frames, ignore_index=True)
    issue_level.to_csv(
        OUT / "github_issue_level_classifications.csv",
        index=False,
    )

    project_df = pd.DataFrame(project_rows).sort_values("project").reset_index(drop=True)
    project_df.to_csv(
        OUT / "project_closure_prevalence_10.csv",
        index=False,
    )

    tracker_df = weighted_tracker_summary(project_df)
    tracker_df.to_csv(
        OUT / "tracker_closure_prevalence_10.csv",
        index=False,
    )

    closed = int(project_df["closed"].sum())
    classifiable = int(project_df["classifiable_closed"].sum())
    nonresolved = int(project_df["confirmed_nonresolved"].sum())
    unclassified = int(project_df["UNCLASSIFIED_CLOSED"].sum())

    pooled = {
        "created_at_utc": utc_now(),
        "projects": int(len(project_df)),
        "tracker_ecosystems": 3,
        "closed": closed,
        "classifiable_closed": classifiable,
        "confirmed_nonresolved": nonresolved,
        "UNCLASSIFIED_CLOSED": unclassified,
        "confirmed_nonresolved_lower_bound_all_closed": nonresolved / closed,
        "nonresolved_share_among_classifiable": (
            nonresolved / classifiable if classifiable else None
        ),
        "unclassified_rate": unclassified / closed,
        "selection_rule": SELECTION_NOTE,
    }

    (OUT / "pooled_summary_10.json").write_text(
        json.dumps(pooled, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "=" * 100,
        "9-PROJECT VALID-CORPUS CLOSURE PREVALENCE AUDIT COMPLETE",
        "=" * 100,
        "",
        f"Projects analyzed: {pooled['projects']} (9 of 10 preselected)",
        "Excluded preselected project: Dolphin Emulator (official Redmine tracker; GitHub Issues empty)",
        f"Tracker ecosystems: {pooled['tracker_ecosystems']}",
        f"Closed issues: {closed:,}",
        f"Confirmed non-resolved: {nonresolved:,}",
        (
            "Conservative lower bound: "
            f"{pooled['confirmed_nonresolved_lower_bound_all_closed']:.2%}"
        ),
        f"Unclassified closed: {unclassified:,} ({pooled['unclassified_rate']:.2%})",
        "",
        "PROJECT RESULTS",
        project_df[
            [
                "project", "tracker", "closed", "confirmed_nonresolved",
                "UNCLASSIFIED_CLOSED",
                "confirmed_nonresolved_lower_bound_all_closed",
            ]
        ].to_string(index=False),
        "",
        "TRACKER RESULTS",
        tracker_df.to_string(index=False),
        "",
        "Selection rule:",
        SELECTION_NOTE,
    ]

    report = "\n".join(lines)
    print("\n" + report)

    (OUT / "RUN_SUMMARY.txt").write_text(report, encoding="utf-8")

    print("\nSaved under:")
    print(" ", OUT)


if __name__ == "__main__":
    main()
