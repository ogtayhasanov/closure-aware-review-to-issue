#!/usr/bin/env python3
"""Who labelled it, and who closed it? A closure-provenance check for GitHub issues.

For every closed issue in a repository (or for each row of the taxonomy
annotation pack) this pulls, from the GitHub GraphQL API:
  * the final close event: who closed the issue (person or bot), and whether a
    commit or pull request closed it (a linked fix);
  * who added each label (for example, whether "wontfix" came from a bot).

It then compares two Level-1 mappings:
  v1  the label-based mapping used in the paper:
      REDIRECTED > explicit REJECTED > ABANDONED > fallback REJECTED > RESOLVED
  v2  the same, plus one rule placed right after REDIRECTED:
      closed by a bot with no linked fix  ->  ABANDONED

Setup
  export GITHUB_TOKEN=...   (a classic token with no scopes is enough)
  pip install openpyxl      (only needed for the "pack" command)

Run
  python closure_provenance.py scan --repos signalapp/Signal-Android
  python closure_provenance.py scan                  # all default repositories
  python closure_provenance.py summarize
  python closure_provenance.py pack --xlsx taxonomy_annotation_pack_FORMATTED.xlsx

Output goes to ./provenance_out/. "scan" can be stopped and restarted;
it continues from where it stopped.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

OUT = "provenance_out"
API = "https://api.github.com/graphql"

# Check that these are the repositories used in the prevalence crawl (Fig. 1).
DEFAULT_REPOS = [
    "signalapp/Signal-Android",
    "ankidroid/Anki-Android",
    "nextcloud/android",
    "thunderbird/thunderbird-android",  # K-9 Mail
    "jitsi/jitsi-meet",
    "hrydgard/ppsspp",
    "brave/brave-browser",              # large: tens of thousands of closed issues
]

PACK_APP_REPOS = {
    "Signal": "signalapp/Signal-Android",
    "AnkiDroid": "ankidroid/Anki-Android",
}

# Label patterns for the Level-1 mapping. Edit them to match your Level-2
# tables if they differ. Matching is case-insensitive, anywhere in the label.
RX_DUPLICATE = re.compile(r"duplicate", re.I)
RX_REJECT = re.compile(
    r"won'?t[\s_-]?fix|invalid|by[\s_-]?design|works[\s_-]?as[\s_-]?intended|"
    r"not[\s_-]?a[\s_-]?bug|not[\s_-]?actionable|rejected|declined|out[\s_-]?of[\s_-]?scope",
    re.I)
RX_ABANDON = re.compile(
    r"stale|inactiv|needs?[\s_-]?(more[\s_-]?)?info|needs?[\s_-]?author[\s_-]?reply|"
    r"waiting[\s_-]?for|no[\s_-]?response|can'?t[\s_-]?reproduce|cannot[\s_-]?reproduce|"
    r"unable[\s_-]?to[\s_-]?reproduce|works[\s_-]?for[\s_-]?me|upstream|incomplete|"
    r"abandoned|obsolete|outdated",
    re.I)

CLASSES = ["RESOLVED", "REJECTED", "ABANDONED", "REDIRECTED"]

ISSUE_FIELDS = """
fragment IssueFields on Issue {
  number
  url
  title
  stateReason
  createdAt
  closedAt
  labels(first: 50) { nodes { name } }
  timelineItems(last: 60, itemTypes: [CLOSED_EVENT, REOPENED_EVENT, LABELED_EVENT,
                                      UNLABELED_EVENT, MARKED_AS_DUPLICATE_EVENT]) {
    nodes {
      __typename
      ... on ClosedEvent {
        createdAt
        actor { __typename login }
        closer {
          __typename
          ... on Commit { oid }
          ... on PullRequest { number merged }
        }
      }
      ... on ReopenedEvent { createdAt actor { __typename login } }
      ... on LabeledEvent { createdAt label { name } actor { __typename login } }
      ... on UnlabeledEvent { createdAt label { name } actor { __typename login } }
      ... on MarkedAsDuplicateEvent { createdAt actor { __typename login } }
    }
  }
}
"""

SCAN_QUERY = """
query($owner: String!, $name: String!, $cursor: String, $size: Int!) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    issues(states: CLOSED, first: $size, after: $cursor,
           orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { ...IssueFields }
    }
  }
}
""" + ISSUE_FIELDS


def pack_query(owner, name, numbers):
    comments = ("comments(last: 4) { nodes { author { __typename login } "
                "authorAssociation createdAt body } }")
    aliases = " ".join(
        "i%d: issue(number: %d) { ...IssueFields %s }" % (n, n, comments) for n in numbers)
    return ("query { rateLimit { cost remaining resetAt } repository(owner: %s, name: %s) { %s } }"
            % (json.dumps(owner), json.dumps(name), aliases)) + ISSUE_FIELDS


# --------------------------------------------------------------------------- API

class HeavyQuery(Exception):
    """GitHub timed out on the query; retry with a smaller page."""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def gql(token, query, variables=None, allow_not_found=False):
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for attempt in range(8):
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "closure-provenance/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 401:
                sys.exit("GitHub rejected the token (HTTP 401). Check GITHUB_TOKEN.")
            if e.code in (502, 503, 504):
                raise HeavyQuery("HTTP %d" % e.code)
            if e.code == 429 or (e.code == 403 and "rate limit" in text.lower()):
                wait = int(e.headers.get("Retry-After") or 60)
                log("Rate limited (HTTP %d); waiting %ds" % (e.code, wait))
                time.sleep(wait)
                continue
            raise RuntimeError("HTTP %d: %s" % (e.code, text[:300]))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            wait = min(120, 5 * 2 ** attempt)
            log("Network error (%s); retrying in %ds" % (e, wait))
            time.sleep(wait)
            continue

        errors = data.get("errors") or []
        if errors:
            msgs = " | ".join(str(x.get("message", "")) for x in errors)
            types = {x.get("type") for x in errors}
            if "RATE_LIMITED" in types:
                log("Rate limit reached; waiting 5 minutes")
                time.sleep(300)
                continue
            if allow_not_found and types <= {"NOT_FOUND"} and data.get("data"):
                log("Some issues were not found and are skipped: " + msgs[:200])
            elif data.get("data") is None or "timeout" in msgs.lower() \
                    or "something went wrong" in msgs.lower():
                raise HeavyQuery(msgs[:200])
            else:
                raise RuntimeError("GraphQL error: " + msgs[:500])

        d = data["data"]
        rl = d.get("rateLimit") or {}
        if rl.get("remaining") is not None and rl["remaining"] < 50:
            reset = datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
            wait = max(0.0, (reset - datetime.now(timezone.utc)).total_seconds()) + 5
            log("Rate budget low (%s left); sleeping %.0fs" % (rl["remaining"], wait))
            time.sleep(wait)
        return d
    raise RuntimeError("Gave up after repeated failures")


# ----------------------------------------------------------------------- records

def actor(a):
    if not a:
        return "ghost", "Deleted"
    return a.get("login") or "", a.get("__typename") or ""


def to_record(repo, node, with_comments=False):
    closes, label_events, dup_by, reopens = [], [], [], 0
    for ev in ((node.get("timelineItems") or {}).get("nodes") or []):
        if not ev:
            continue
        kind = ev.get("__typename")
        if kind == "ClosedEvent":
            login, typ = actor(ev.get("actor"))
            closer = ev.get("closer") or {}
            ctype = closer.get("__typename") or ""
            if ctype == "Commit":
                ref = (closer.get("oid") or "")[:10]
            elif ctype == "PullRequest":
                ref = "PR#%s%s" % (closer.get("number"), "" if closer.get("merged") else " (unmerged)")
            else:
                ref = ""
            closes.append({"at": ev.get("createdAt") or "", "by": login, "by_type": typ,
                           "closer": ctype, "ref": ref})
        elif kind == "ReopenedEvent":
            reopens += 1
        elif kind in ("LabeledEvent", "UnlabeledEvent"):
            login, typ = actor(ev.get("actor"))
            label_events.append({"at": ev.get("createdAt") or "",
                                 "label": (ev.get("label") or {}).get("name", ""),
                                 "by": login, "by_type": typ,
                                 "op": "+" if kind == "LabeledEvent" else "-"})
        elif kind == "MarkedAsDuplicateEvent":
            dup_by.append(actor(ev.get("actor"))[0])

    closes.sort(key=lambda c: c["at"])
    final = closes[-1] if closes else {}
    rec = {
        "repo": repo,
        "number": node["number"],
        "url": node.get("url"),
        "title": node.get("title"),
        "state_reason": node.get("stateReason"),
        "created_at": node.get("createdAt"),
        "closed_at": node.get("closedAt"),
        "labels": [l["name"] for l in ((node.get("labels") or {}).get("nodes") or []) if l],
        "closed_by": final.get("by", ""),
        "closed_by_type": final.get("by_type", ""),
        "closer": final.get("closer", ""),
        "closer_ref": final.get("ref", ""),
        "n_closes": len(closes),
        "n_reopens": reopens,
        "label_events": label_events,
        "marked_duplicate_by": dup_by,
    }
    if with_comments:
        parts = []
        for c in ((node.get("comments") or {}).get("nodes") or []):
            if not c:
                continue
            login, typ = actor(c.get("author"))
            text = re.sub(r"\s+", " ", c.get("body") or "").strip()
            tag = c.get("authorAssociation", "") + (", bot" if typ == "Bot" else "")
            parts.append("%s [%s]: %s" % (login, tag, text[:280]))
        rec["last_comments"] = " || ".join(parts)
    return rec


# ---------------------------------------------------------------- classification

def is_bot(login, typ, extra_bots):
    name = (login or "").lower()
    return typ == "Bot" or name.endswith("[bot]") or name in extra_bots


def first_match(labels, rx):
    for label in labels:
        if rx.search(label):
            return label
    return None


def label_added_by(rec, label):
    """(login, type) of whoever last added this label, or ('?', '') if not in the timeline."""
    adds = [e for e in rec["label_events"] if e["op"] == "+" and e["label"].lower() == label.lower()]
    if not adds:
        return "?", ""
    last = max(adds, key=lambda e: e["at"])
    return last["by"], last["by_type"]


def bot_closed_without_fix(rec, extra_bots):
    return is_bot(rec.get("closed_by"), rec.get("closed_by_type"), extra_bots) and not rec.get("closer")


def classify(rec, extra_bots, bot_rule):
    labels = rec.get("labels") or []
    reason = (rec.get("state_reason") or "").upper()
    if reason == "DUPLICATE" or first_match(labels, RX_DUPLICATE) or rec.get("marked_duplicate_by"):
        return "REDIRECTED", "duplicate"
    if bot_rule and bot_closed_without_fix(rec, extra_bots):
        return "ABANDONED", "bot-closed:" + (rec.get("closed_by") or "")
    hit = first_match(labels, RX_REJECT)
    if hit:
        return "REJECTED", "label:" + hit
    hit = first_match(labels, RX_ABANDON)
    if hit:
        return "ABANDONED", "label:" + hit
    if reason == "NOT_PLANNED":
        return "REJECTED", "fallback:not_planned"
    return "RESOLVED", "completed"


def pct(a, b):
    return "%.1f%%" % (100.0 * a / b) if b else "n/a"


# -------------------------------------------------------------------------- scan

def run_scan(token, repos, max_issues, page_size, fresh):
    os.makedirs(OUT, exist_ok=True)
    for repo in repos:
        owner, name = repo.split("/", 1)
        base = os.path.join(OUT, "scan_" + repo.replace("/", "__"))
        jsonl, cursor_file = base + ".jsonl", base + ".cursor"
        if fresh:
            for f in (jsonl, cursor_file):
                if os.path.exists(f):
                    os.remove(f)
        cursor = None
        if os.path.exists(cursor_file):
            with open(cursor_file, encoding="utf-8") as f:
                cursor = f.read().strip() or None
        if cursor == "DONE":
            log("%s: already complete (use --fresh to redo)" % repo)
            continue
        done = 0
        if os.path.exists(jsonl):
            with open(jsonl, encoding="utf-8") as f:
                done = sum(1 for _ in f)
        size, started, fetched = page_size, time.time(), 0
        with open(jsonl, "a", encoding="utf-8") as out:
            while not (max_issues and done >= max_issues):
                try:
                    d = gql(token, SCAN_QUERY, {"owner": owner, "name": name,
                                                "cursor": cursor, "size": size})
                except HeavyQuery as e:
                    if size <= 5:
                        raise RuntimeError("%s: still timing out at page size 5 (%s)" % (repo, e))
                    size = max(5, size // 2)
                    log("%s: GitHub timed out (%s); page size -> %d" % (repo, e, size))
                    continue
                repo_data = d.get("repository")
                if repo_data is None:
                    sys.exit("Repository not found: %s" % repo)
                issues = repo_data["issues"]
                for node in issues["nodes"] or []:
                    if node:
                        out.write(json.dumps(to_record(repo, node), ensure_ascii=False) + "\n")
                        done += 1
                        fetched += 1
                out.flush()
                cursor = issues["pageInfo"]["endCursor"]
                has_next = issues["pageInfo"]["hasNextPage"]
                with open(cursor_file, "w", encoding="utf-8") as f:
                    f.write("DONE" if not has_next else (cursor or ""))
                total = issues["totalCount"]
                rate = fetched / max(1e-9, time.time() - started)
                eta = (total - done) / rate / 60 if rate else 0
                log("%s: %s / %s closed issues (about %.0f min left)" % (repo, format(done, ","), format(total, ","), eta))
                if not has_next:
                    break
                if size < page_size:
                    size = min(page_size, size * 2)
    log("Scan finished. Next: python %s summarize" % os.path.basename(sys.argv[0]))


# --------------------------------------------------------------------- summarize

def load_scans():
    by_repo = defaultdict(dict)
    if not os.path.isdir(OUT):
        sys.exit("No %s/ folder. Run the scan first." % OUT)
    for fn in sorted(os.listdir(OUT)):
        if fn.startswith("scan_") and fn.endswith(".jsonl"):
            with open(os.path.join(OUT, fn), encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        by_repo[r["repo"]][r["number"]] = r  # de-duplicates resumed pages
    if not by_repo:
        sys.exit("No scan files in %s/. Run the scan first." % OUT)
    return {repo: list(recs.values()) for repo, recs in by_repo.items()}


def run_summarize(extra_bots):
    rows, transitions = [], []
    for repo, recs in sorted(load_scans().items()):
        n = len(recs)
        v1 = [classify(r, extra_bots, False) for r in recs]
        v2 = [classify(r, extra_bots, True) for r in recs]
        c1 = Counter(c for c, _ in v1)
        c2 = Counter(c for c, _ in v2)
        nonres1, nonres2 = n - c1["RESOLVED"], n - c2["RESOLVED"]

        rej_by_label = [(r, why[len("label:"):]) for r, (c, why) in zip(recs, v1)
                        if c == "REJECTED" and why.startswith("label:")]
        rej_label_bot = sum(1 for r, lab in rej_by_label if is_bot(*label_added_by(r, lab), extra_bots))
        rej_closed_bot = sum(1 for r, _ in rej_by_label if bot_closed_without_fix(r, extra_bots))

        resolved = [r for r, (c, _) in zip(recs, v1) if c == "RESOLVED"]
        res_fix = sum(1 for r in resolved if r.get("closer"))
        res_bot = sum(1 for r in resolved if bot_closed_without_fix(r, extra_bots))

        moves = Counter((a, b) for (a, _), (b, _) in zip(v1, v2) if a != b)
        changed = sum(moves.values())
        closers = Counter((r.get("closed_by") or "?", r.get("closed_by_type") or "") for r in recs)

        print("\n== %s  (%s closed issues)" % (repo, format(n, ",")))
        print("  Non-resolved: v1 %s (%s) -> v2 %s (%s)" % (
            format(nonres1, ","), pct(nonres1, n), format(nonres2, ","), pct(nonres2, n)))
        print("  v1: " + " | ".join("%s %s" % (k, format(c1[k], ",")) for k in CLASSES))
        print("  v2: " + " | ".join("%s %s" % (k, format(c2[k], ",")) for k in CLASSES))
        print("  Explicit reject label (v1 REJECTED by label): %s" % format(len(rej_by_label), ","))
        print("     label added by a bot: %s (%s); closed by a bot with no linked fix: %s (%s)" % (
            format(rej_label_bot, ","), pct(rej_label_bot, len(rej_by_label)),
            format(rej_closed_bot, ","), pct(rej_closed_bot, len(rej_by_label))))
        print("  v1 RESOLVED: %s; linked commit/PR: %s (%s); closed by a bot, no fix: %s (%s)" % (
            format(len(resolved), ","), format(res_fix, ","), pct(res_fix, len(resolved)),
            format(res_bot, ","), pct(res_bot, len(resolved))))
        print("  Labels changed by v2: %s (%s)" % (format(changed, ","), pct(changed, n)))
        for (a, b), k in moves.most_common():
            print("     %s -> %s: %s" % (a, b, format(k, ",")))
            transitions.append({"repo": repo, "from_v1": a, "to_v2": b, "count": k})
        print("  Top closers: " + "; ".join(
            "%s (%s%s) %s" % (login, typ or "?", ", bot" if is_bot(login, typ, extra_bots) else "",
                              format(k, ","))
            for (login, typ), k in closers.most_common(8)))

        row = {"repo": repo, "closed": n,
               "nonres_v1": nonres1, "nonres_v1_pct": round(100.0 * nonres1 / n, 2) if n else "",
               "nonres_v2": nonres2, "nonres_v2_pct": round(100.0 * nonres2 / n, 2) if n else "",
               "reject_by_label": len(rej_by_label), "reject_label_added_by_bot": rej_label_bot,
               "reject_closed_by_bot_no_fix": rej_closed_bot,
               "resolved_v1": len(resolved), "resolved_with_linked_fix": res_fix,
               "resolved_closed_by_bot_no_fix": res_bot, "changed_v1_to_v2": changed}
        for k in CLASSES:
            row["v1_" + k] = c1[k]
            row["v2_" + k] = c2[k]
        rows.append(row)

    write_csv(os.path.join(OUT, "summary_by_repo.csv"), rows)
    write_csv(os.path.join(OUT, "v1_to_v2_changes.csv"), transitions)
    print("\nSaved %s/summary_by_repo.csv and %s/v1_to_v2_changes.csv" % (OUT, OUT))
    print("Check the top closers: add any automation account that is not marked as a bot with "
          "--extra-bots name1,name2 and run summarize again.")


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0].keys())
    for r in rows[1:]:
        fields += [k for k in r if k not in fields]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# -------------------------------------------------------------------------- pack

def read_pack(xlsx):
    try:
        import openpyxl
    except ImportError:
        sys.exit("The pack command needs openpyxl: pip install openpyxl")
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["Annotation"] if "Annotation" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    col = {h: i for i, h in enumerate(header)}
    for need in ("app", "number", "human_l1"):
        if need not in col:
            sys.exit("Column %r not found in %s" % (need, xlsx))
    items = []
    for excel_row, row in enumerate(rows[1:], start=2):
        app, number = row[col["app"]], row[col["number"]]
        if app is None or number is None:
            continue
        items.append({"excel_row": excel_row, "app": str(app).strip(),
                      "number": int(str(number).strip()),
                      "human_l1": str(row[col["human_l1"]] or "").strip()})
    return items


def fetch_pack(token, repo, numbers):
    owner, name = repo.split("/", 1)
    found, size, i = {}, 20, 0
    while i < len(numbers):
        chunk = numbers[i:i + size]
        try:
            d = gql(token, pack_query(owner, name, chunk), allow_not_found=True)
        except HeavyQuery as e:
            if size <= 2:
                raise RuntimeError("%s: still timing out (%s)" % (repo, e))
            size = max(2, size // 2)
            log("%s: GitHub timed out; batch size -> %d" % (repo, size))
            continue
        repo_data = d.get("repository") or {}
        for n in chunk:
            node = repo_data.get("i%d" % n)
            found[n] = to_record(repo, node, with_comments=True) if node else None
        i += len(chunk)
        log("%s: fetched %d / %d" % (repo, i, len(numbers)))
    return found


def run_pack(token, xlsx, extra_bots, app_repos):
    os.makedirs(OUT, exist_ok=True)
    items = read_pack(xlsx)
    by_repo = defaultdict(list)
    for it in items:
        repo = app_repos.get(it["app"])
        if not repo:
            sys.exit("No repository for app %r. Add --app-repo %s=owner/name" % (it["app"], it["app"]))
        it["repo"] = repo
        by_repo[repo].append(it["number"])
    records = {}
    for repo, numbers in by_repo.items():
        for n, rec in fetch_pack(token, repo, sorted(set(numbers))).items():
            records[(repo, n)] = rec

    out_rows, agree1, agree2, missing = [], 0, 0, 0
    changed_rows = []
    for it in items:
        rec = records.get((it["repo"], it["number"]))
        if rec is None:
            missing += 1
            out_rows.append({"excel_row": it["excel_row"], "app": it["app"], "number": it["number"],
                             "human_l1": it["human_l1"], "v1_rule": "NOT FOUND"})
            continue
        (c1, why1), (c2, why2) = classify(rec, extra_bots, False), classify(rec, extra_bots, True)
        agree1 += c1 == it["human_l1"]
        agree2 += c2 == it["human_l1"]
        reject_label = first_match(rec["labels"], RX_REJECT)
        added_by = "%s (%s)" % label_added_by(rec, reject_label) if reject_label else ""
        row = {
            "excel_row": it["excel_row"], "app": it["app"], "number": it["number"], "url": rec["url"],
            "human_l1": it["human_l1"],
            "v1_rule": c1, "v1_why": why1, "v2_rule": c2, "v2_why": why2,
            "v2_differs_from_human": "YES" if c2 != it["human_l1"] else "",
            "state_reason": rec["state_reason"], "labels": ", ".join(rec["labels"]),
            "closed_by": rec["closed_by"], "closed_by_type": rec["closed_by_type"],
            "closed_by_bot": "YES" if is_bot(rec["closed_by"], rec["closed_by_type"], extra_bots) else "",
            "linked_fix": ("%s %s" % (rec["closer"], rec["closer_ref"])).strip(),
            "reject_label_added_by": added_by,
            "closed_at": rec["closed_at"],
            "last_comments": rec.get("last_comments", ""),
            "human_l1_v2": "", "notes": "",
        }
        out_rows.append(row)
        if c2 != it["human_l1"]:
            changed_rows.append(row)

    path = os.path.join(OUT, "pack_evidence.csv")
    write_csv(path, out_rows)
    n = len(items) - missing
    print("\nPack: %d issues fetched, %d not found" % (n, missing))
    print("v1 rule vs your labels: %d/%d (%s)  <- should match Table 1 if v1 equals your rule"
          % (agree1, n, pct(agree1, n)))
    print("v2 rule vs your labels: %d/%d (%s)" % (agree2, n, pct(agree2, n)))

    wontfix = [r for r in out_rows if re.search(r"won'?t[\s_-]?fix", r.get("labels", ""), re.I)]
    if wontfix:
        by_bot = sum(1 for r in wontfix if "Bot" in r["reject_label_added_by"]
                     or r["reject_label_added_by"].split(" ")[0].lower().endswith("[bot]"))
        closed_bot = sum(1 for r in wontfix if r["closed_by_bot"])
        print("wontfix rows: %d; label added by a bot: %d; closed by a bot: %d"
              % (len(wontfix), by_bot, closed_bot))

    print("\nRows where v2 disagrees with your label (%d) - re-check these first:" % len(changed_rows))
    for r in changed_rows:
        print("  row %-4s %-9s #%-6s yours=%-10s v2=%-10s %s; closed by %s%s" % (
            r["excel_row"], r["app"], r["number"], r["human_l1"], r["v2_rule"], r["v2_why"],
            r["closed_by"] or "?", " (bot)" if r["closed_by_bot"] else ""))
    print("\nSaved %s. Fill in human_l1_v2 using the evidence columns." % path)


# -------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Who labelled and who closed GitHub issues.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="fetch closed issues and their close/label history")
    s.add_argument("--repos", nargs="+", default=DEFAULT_REPOS, help="owner/name ...")
    s.add_argument("--max-issues", type=int, default=0, help="stop each repo after N issues (0 = all)")
    s.add_argument("--page-size", type=int, default=50)
    s.add_argument("--fresh", action="store_true", help="ignore saved progress and start over")

    m = sub.add_parser("summarize", help="per-repo bot provenance and v1 vs v2 counts")
    m.add_argument("--extra-bots", default="", help="comma-separated automation accounts")

    p = sub.add_parser("pack", help="pull evidence for the annotation pack rows")
    p.add_argument("--xlsx", required=True)
    p.add_argument("--extra-bots", default="")
    p.add_argument("--app-repo", action="append", default=[], help="App=owner/name (repeatable)")

    args = ap.parse_args()
    extra = {x.strip().lower() for x in getattr(args, "extra_bots", "").split(",") if x.strip()}

    if args.cmd == "summarize":
        run_summarize(extra)
        return
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN first (a classic token with no scopes is enough).")
    if args.cmd == "scan":
        run_scan(token, args.repos, args.max_issues, args.page_size, args.fresh)
    else:
        repos = dict(PACK_APP_REPOS)
        for pair in args.app_repo:
            app, _, repo = pair.partition("=")
            repos[app.strip()] = repo.strip()
        run_pack(token, args.xlsx, extra, repos)


if __name__ == "__main__":
    main()
