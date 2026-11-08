#!/usr/bin/env python3
"""Convert original 2026-08 Häring 82- or 246-row private CSV to fair-RQ3 JSONL.

Drops ALL previous model outputs and judgments, retaining only the fixed input
case data. Prefer --native-fields when native resolution/state_reason columns
exist; use --allow-legacy-signal explicitly otherwise, with provenance warning.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from rq3_protocol import validate

BASE=['pair_key','review_text','repository','display_issue_id','issue_title','issue_body',
      'binary_state','issue_url','l1_class','subtype','action_l1']
NATIVE=['resolution','state_reason','stateReason','status_reason','closed_by','closing_actor']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,help='Original PRIVATE rrf_threeway_responses_and_judgments.csv or rrf_closure_aware_responses_and_judgments.csv')
    p.add_argument('--output',required=True)
    p.add_argument('--expected-cases',type=int,default=82)
    p.add_argument('--expected-audit',type=int,default=36)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--native-fields',action='store_true',help='Use unmodified native status/resolution field columns')
    group.add_argument('--allow-legacy-signal',action='store_true',help='Use historical resolution_signal; not guaranteed to be raw native metadata')
    a=p.parse_args()
    with open(a.input,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if not rows: raise ValueError('Empty input')
    missing=set(BASE)-set(rows[0]);
    if missing: raise ValueError(f'Missing original paper columns: {sorted(missing)}')
    by_id={}
    for row in rows:
        ident=row['pair_key']
        if not ident: raise ValueError('Empty pair_key')
        existing=by_id.get(ident)
        if existing:
            # Reject inconsistent source case values across original arms.
            for key in BASE[1:]+['resolution_signal','labels','closed_at']:
                if key in row and row[key]!=existing[key]:
                    raise ValueError(f'Inconsistent {key} for {ident} across original arm rows')
        else: by_id[ident]=row
    results=[]
    for ident,r in sorted(by_id.items()):
        raw={key:r[key] for key in NATIVE if key in r and r[key].strip()}
        for key in ('labels','closed_at'):
            if key in r: raw[key]=r[key]
        if a.native_fields:
            if not any(k in raw for k in ('resolution','state_reason','stateReason','status_reason')):
                raise ValueError(f'{ident}: no unmodified native status/resolution column found. Re-export original tracker data or explicitly choose --allow-legacy-signal.')
            source='native_tracker_fields'
        else:
            if 'resolution_signal' not in r: raise ValueError('legacy resolution_signal column missing')
            raw['resolution_signal_from_old_export']=r['resolution_signal']
            source='legacy_resolution_signal_verify_provenance'
        results.append({'case_id':ident,'review_text':r['review_text'],'repository':r['repository'],
            'display_issue_id':r['display_issue_id'],'issue_title':r['issue_title'],
            'issue_body':r['issue_body'],'binary_state':r['binary_state'].strip().lower(),
            'issue_url':r['issue_url'],'l1_class':r['l1_class'],'subtype':r['subtype'],
            'action_l1':r['action_l1'],'raw_tracker_fields':raw,
            'raw_source_provenance':source,
            'reference_evidence':''}) # manually verify/complete before blinding
    print(json.dumps(validate(results,a.expected_cases,a.expected_audit),indent=2))
    Path(a.output).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf-8')
    print(f'Exported {len(results)} fixed pairs to {a.output} (no historical responses or judgments copied).')
    if a.allow_legacy_signal:
        print('WARNING: legacy resolution_signal may be interpreted/derived. Verify against original tracker fields before making native-raw claims.',file=sys.stderr)
    print('WARNING: reference_evidence fields are blank; independently verify these from original issue evidence before blinding.',file=sys.stderr)

if __name__=='__main__':main()
