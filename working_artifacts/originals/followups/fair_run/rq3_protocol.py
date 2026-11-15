"""Versioned, frozen prompt and case rendering for TOSEM fair RQ3.

One identical system message for all three conditions. Only the evidence block
in the user message changes. No arm-specific instructions, policies or directives.
"""
from __future__ import annotations
import hashlib
import json

VERSION = 'fair-rq3-v1-2026-10-20'
ARMS = ('binary_state', 'raw_metadata', 'closure_aware')
SYSTEM_PROMPT = '''You are a developer-support assistant. Write a concise, empathetic response to a real app review using only the supplied issue evidence.

Tell the user accurately what happened to the issue, using only the supplied information.
Do not claim the issue was fixed unless the supplied information says so.
If it was closed because more information was needed, ask for reproduction steps, app version, device, and logs.
If it was closed as a duplicate or is tracked elsewhere, say that it is tracked elsewhere.

If the issue is open, say that it is open and tracked; do not claim anyone is working on it without explicit evidence.
Cite the retrieved issue number, and include its URL when one is supplied.
Do not invent versions, releases, dates, commits, causes, fixes, issue numbers, or developer promises.
Keep the response under 100 words.'''
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest()


def canon(v):
    if v is None or v == '' or v == []:
        return 'not supplied'
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return str(v)


def raw_fields(row):
    fields = row.get('raw_tracker_fields')
    if not isinstance(fields, dict) or not fields:
        raise ValueError(f"{row.get('case_id')}: raw_tracker_fields must be a nonempty JSON object of unmodified native fields")
    # Native fields must be exactly reproduced, not post-processed or interpreted.
    return fields


def render(row, arm):
    if arm not in ARMS:
        raise ValueError(f'unknown arm: {arm}')
    state = str(row['binary_state']).lower()
    body = str(row.get('issue_body') or '')[:1200]
    common = (
        f"REAL USER REVIEW:\n{row['review_text']}\n\n"
        "RETRIEVED ISSUE:\n"
        f"- Tracker: {canon(row.get('repository'))}\n"
        f"- Issue #{row['display_issue_id']}: {row['issue_title']}\n"
        f"- Binary state: {state}\n"
        f"- URL: {canon(row.get('issue_url'))}\n"
        f"- Issue body excerpt: {canon(body)}"
    )
    if arm != 'binary_state':
        raw = raw_fields(row)
        common += '\n\nRAW TRACKER CLOSURE FIELDS:\n'
        for key in sorted(raw):
            common += f'- {key}: {canon(raw[key])}\n'
        common = common.rstrip()
    if arm == 'closure_aware':
        # Same raw metadata plus its deterministic normalization. The taxonomy
        # is provided as data, not supplemented with bespoke prompt commands.
        common += ('\n\nNORMALIZED TAXONOMY FIELDS:\n'
                   f"- l1_class: {canon(row.get('l1_class'))}\n"
                   f"- subtype: {canon(row.get('subtype'))}\n"
                   f"- action_l1: {canon(row.get('action_l1'))}")
    return [{'role':'system','content':SYSTEM_PROMPT},
            {'role':'user','content':common+'\n\nWrite a response to the review.'}]


def validate(rows, expected_cases=82, expected_audit=36):
    if len(rows) != expected_cases:
        raise ValueError(f'Expected {expected_cases} unique cases, got {len(rows)}')
    ids = [r.get('case_id') for r in rows]
    if any(not i or not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('case_id must be nonempty, unique strings')
    n_audit = 0
    for r in rows:
        ident = r['case_id']
        for f in ['review_text','repository','display_issue_id','issue_title','binary_state','l1_class','subtype','action_l1']:
            if f not in r or str(r[f]).strip() == '':
                raise ValueError(f'{ident}: required field missing: {f}')
        if r['binary_state'].lower() not in ('open','closed'):
            raise ValueError(f'{ident}: bad binary_state')
        raw_fields(r)
        is_audit = r['binary_state'].lower() == 'closed' and r['l1_class'] in {'REJECTED','ABANDONED','REDIRECTED'}
        if is_audit:
            n_audit += 1
        if 'audit36' in r and bool(r['audit36']) != is_audit:
            raise ValueError(f'{ident}: audit36 disagrees with closed non-resolved selection')
        for a in ARMS:
            render(r,a)
    if n_audit != expected_audit:
        raise ValueError(f'Expected {expected_audit} closed non-resolved audit cases; found {n_audit}')
    return {'cases':len(rows), 'audit_cases':n_audit, 'requests':3*len(rows), 'protocol':VERSION, 'system_sha256':PROMPT_SHA256}


def audit(row):
    return row['binary_state'].lower() == 'closed' and row['l1_class'] in {'REJECTED','ABANDONED','REDIRECTED'}
