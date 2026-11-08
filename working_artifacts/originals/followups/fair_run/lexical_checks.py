#!/usr/bin/env python3
"""Deterministic action-realization lexical screens (secondary diagnostics only).

Important: These heuristics DO NOT infer status correctness or replace human
judgment. Full cases/answers are needed for the actual scientific metrics.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import re
from run_rq3 import read_jsonl
from rq3_protocol import ARMS, validate

# Require a request and diagnostic object: mentioning "logs" in an unrelated
# statement is not enough. This is a high-precision screen, not a classifier.
REQUEST=re.compile(r'\b(?:please|could you|can you|share|provide|send|submit|attach|include|upload|report|we need|help us by)\b',re.I)
DIAGNOSTICS=re.compile(r'\b(?:logs?|logcat|trace(?:s)?|stacktrace|reproduc(?:e|tion)|steps?|version(?:s)?|device(?:s)?|screenshot(?:s)?|operating system|OS version)\b',re.I)
# Require literal routing; "duplicate" alone does NOT satisfy this test.
ROUTE=re.compile(r'(?:tracked\s+(?:elsewhere|in|under|on|by|as)\b|tracking\s+(?:elsewhere|in|under|on)\b|(?:see|follow|refer to|check|continue in)\s+(?:the\s+)?(?:original|other|linked|existing|related|canonical)\s+(?:issue|ticket|thread|discussion)\b|redirected\s+(?:to|elsewhere)\b|(?:another|other|original|existing|upstream)\s+(?:issue|ticket|tracker)\b|duplicate\s+of\s+(?:issue|ticket|#)\s*#?\d+)',re.I)
WORK_CLAIM=re.compile(r'\b(?:team|developers?|maintainers?|we)\s+(?:is|are|have been|has been)\s+(?:actively\s+)?(?:investigating|working|fixing|addressing)\b|\bunder investigation\b',re.I)
FIX_WORDS=re.compile(r'\b(?:fixed|resolved|patched|corrected|implemented)\b',re.I)
NEGATION=re.compile(r'\b(?:not|never|no evidence (?:of|that)|cannot confirm|isn.t|wasn.t|hasn.t)\b',re.I)

def scan(text, subtype, l1, action):
    t=' '.join(text.split())
    need= l1=='ABANDONED' and subtype=='NEEDS_INFO'
    redir=l1=='REDIRECTED'
    known=action in {'KNOWN_BUG','KNOWN_ISSUE'}
    request=(bool(REQUEST.search(t)) and bool(DIAGNOSTICS.search(t))) if need else None
    redirected=bool(ROUTE.search(t)) if redir else None
    # This may flag an explicit factual quote; requires manual verification.
    unsupported_work=(bool(WORK_CLAIM.search(t))) if known else None
    # Separate screen, never count a false-fix error from lexical match alone.
    fix_language=bool(FIX_WORDS.search(t))
    return {'needs_info_request_screen':request,'redirected_route_screen':redirected,
            'unverified_work_claim_screen':unsupported_work,'fix_language_review_flag':fix_language,
            'word_count':len(t.split())}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--responses',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--expected-cases',type=int,default=82)
    p.add_argument('--expected-audit',type=int,default=36)
    a=p.parse_args()
    cases=read_jsonl(a.input)
    validate(cases,a.expected_cases,a.expected_audit)
    by_id={r['case_id']:r for r in cases}
    responses=read_jsonl(a.responses)
    expected={(r['case_id'],arm) for r in cases for arm in ARMS}
    actual=[(r['case_id'],r['arm']) for r in responses]
    if set(actual)!=expected or len(actual)!=len(expected): raise ValueError(f'Expected {len(expected)} uniquely paired responses, got {len(actual)}')
    out=[]
    for r in responses:
        if 'response' not in r: raise ValueError('Cannot evaluate dry-run requests as actual responses')
        c=by_id[r['case_id']]
        measures=scan(r['response'],c['subtype'],c['l1_class'],c['action_l1'])
        out.append({'case_id':r['case_id'],'arm':r['arm'],'l1_class':c['l1_class'],'subtype':c['subtype'],**measures})
    fields=list(out[0])
    with open(a.output,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    for flag in ('needs_info_request_screen','redirected_route_screen','unverified_work_claim_screen'):
        print(flag+':')
        for arm in ARMS:
            vals=[r[flag] for r in out if r['arm']==arm and r[flag] is not None]
            if vals: print(f'  {arm}: {sum(vals)}/{len(vals)} (LEXICAL SCREEN; not manually validated)')
    print('Metrics written. Do not report these as human status accuracy or as proven action correctness.')
if __name__=='__main__':main()
