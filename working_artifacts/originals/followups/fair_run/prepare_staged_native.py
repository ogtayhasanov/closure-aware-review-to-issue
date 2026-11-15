#!/usr/bin/env python3
"""Reconstruct *best-effort* native tracker fields from the archived three-arm CSV.

This conversion is deliberately conservative: never reconstruct an unobserved
state_reason from a historical taxonomy, and never manufacture a ground truth
synopsis. The staged file must be verified against original tracker snapshots
before being designated the final experiment evidence.

Generates private inputs and an audit/QA worklist. No calls to any language model.
"""
import argparse
import ast
import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from rq3_protocol import validate

KEYS = ['pair_key','review_text','repository','display_issue_id','issue_title',
        'issue_body','binary_state','issue_url','resolution_signal','labels',
        'closed_at','l1_class','subtype','action_l1']


def native_source(r):
    issues = []
    raw = {}
    signal = r.get('resolution_signal','').strip()
    repo = r['repository']
    if r['binary_state'].lower()=='closed':
        raw['state'] = 'closed'
    else:
        raw['state'] = 'open'
    if r.get('closed_at','').strip():
        raw['closed_at'] = r['closed_at'].strip()
    if 'Bugzilla' in repo:
        match = re.fullmatch(r'Bugzilla (resolution|status)=([A-Z_]+)',signal)
        if match:
            raw[match.group(1)] = match.group(2)
        else: issues.append('UNPARSEABLE_BUGZILLA_SIGNAL')
    elif 'Trac' in repo:
        match = re.fullmatch(r'Trac (resolution|status)=([a-zA-Z_]+)',signal)
        if match:
            raw[match.group(1)] = match.group(2)
        else: issues.append('UNPARSEABLE_TRAC_SIGNAL')
    elif 'GitHub' in repo:
        labels = r.get('labels','').strip()
        if labels:
            try:
                data = ast.literal_eval(labels)
                if not isinstance(data,list): raise ValueError('not a list')
                raw['labels'] = [str(a['name']) for a in data]
            except (ValueError, SyntaxError, TypeError, KeyError):
                issues.append('UNPARSEABLE_GITHUB_LABELS')
        match = re.fullmatch(r'state_reason=([^\s]+)',signal)
        if match:
            raw['state_reason'] = match.group(1)
        elif re.fullmatch(r'GitHub snapshot state=(open|closed)',signal):
            pass
        elif signal.startswith('Historical snapshot closed; GitHub enrichment unavailable'):
            issues.append('CLOSING_REASON_UNAVAILABLE_API_RATE_LIMIT')
        elif signal.startswith('stale label=') or signal.startswith('needs-info/cannot-reproduce label='):
            # Old signal was derived from label(s); the unmodified labels are in raw.
            issues.append('DERIVED_LABEL_REASON_STATE_REASON_NOT_RETAINED')
        else: issues.append('GITHUB_SIGNAL_NEEDS_MANUAL_CHECK')
    else: issues.append('UNKNOWN_TRACKER')
    return raw,issues


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output-dir',required=True)
    args=p.parse_args()
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    source=Path(args.input)
    with source.open(encoding='utf-8-sig',newline='') as f:
        original=list(csv.DictReader(f))
    if len(original)!=246: raise ValueError(f'Expected 246 source rows, got {len(original)}')
    groups=collections.defaultdict(list)
    for r in original: groups[r['pair_key']].append(r)
    if len(groups)!=82:raise ValueError(f'Expected 82 unique cases, got {len(groups)}')
    clean=[];worklist=[];audit=[];counts=collections.Counter()
    for case_id,part in sorted(groups.items()):
        if {r['system'] for r in part}!={'closure_aware','raw_metadata','binary_state'}:
            raise ValueError(f'Incomplete or repeated arm for {case_id}')
        for k in KEYS[1:]:
            if len(set(row[k] for row in part))!=1:raise ValueError(f'Inconsistent {k} for {case_id}')
        r=part[0];raw,issues=native_source(r)
        identifier=r['display_issue_id']; canonical_id=identifier
        url=r.get('issue_url','').strip()
        if 'GitHub' in r['repository'] and url:
            match=re.search(r'/issues/(\d+)(?:[/?#]|$)',urlsplit(url).path)
            if match:
                canonical_id=match.group(1)
                if canonical_id!=identifier: issues.append('ISSUE_ID_CORRECTED_FROM_URL')
            else:issues.append('NONSTANDARD_GITHUB_ISSUE_URL')
        if 'Name: raw_text, dtype: object' in r['issue_body']:
            issues.append('TRUNCATED_PANDAS_SERIES_ISSUE_BODY')
        if not url:issues.append('MISSING_ISSUE_URL')
        if r['l1_class']=='ABANDONED' and r['subtype']=='OTHER':
            issues.append('UNKNOWN_CLOSING_REASON_AS_ABANDONED_OTHER_GOLD')
        entry={
            'case_id':case_id,'review_text':r['review_text'],
            'repository':r['repository'],'display_issue_id':canonical_id,
            'issue_title':r['issue_title'],'issue_body':r['issue_body'],
            'binary_state':r['binary_state'].strip().lower(),
            'issue_url':url,'raw_tracker_fields':raw,
            'l1_class':r['l1_class'],'subtype':r['subtype'],'action_l1':r['action_l1'],
            'reference_evidence':'',
            'data_provenance_status':'RECONSTRUCTED_FROM_LEGACY_CSV_NOT_VERIFIED_AGAINST_TRACKER',
            'original_display_issue_id':identifier,
        }
        clean.append(entry)
        qa={'case_id':case_id,'app':r['app'],'original_display_id':identifier,
            'canonical_display_id':canonical_id,'issue_url':url,
            'signal_from_old_export':r['resolution_signal'],
            'gold_l1':r['l1_class'],'gold_subtype':r['subtype'],
            'raw_fields_json':json.dumps(raw,ensure_ascii=False,sort_keys=True),
            'qa_flags':';'.join(issues),'verified_against_source':'',
            'neutral_reference_evidence':'','reference_citation_or_link':'','reference_notes':''}
        worklist.append(qa)
        for z in issues:counts[z]+=1
        if entry['binary_state']=='closed' and entry['l1_class'] in {'REJECTED','ABANDONED','REDIRECTED'}:audit.append(qa)
    summary=validate(clean)
    fp=out/'real_82_native_staged.jsonl'
    with fp.open('w',encoding='utf-8') as f:
        for a in clean:f.write(json.dumps(a,ensure_ascii=False,sort_keys=True)+'\n')
    def write_csv(name,data):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    write_csv('audit36_verification_worklist.csv',audit)
    write_csv('quality_review_82.csv',worklist)
    summary.update({'source_csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'qa_flags':dict(counts),
                    'reference_evidence_verified':0,
                    'source_field_status':'RECONSTRUCTED_NOT_VERIFIED',
                    'issue_text_status':'LEGACY_EXPORT_28_PANDAS_REPR_TRUNCATION',
                    'recommendation':'Verify original metadata and independently write reference_evidence before live generation/annotation. Do not silently assume old taxonomy is gold.'})
    (out/'preflight_quality_report.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
