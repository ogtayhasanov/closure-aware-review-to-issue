#!/usr/bin/env python3
"""Create blind human-evaluation CSV and a separate private re-identification key.
After labels are frozen, use score to join the key and compute paired outcomes.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import uuid
from collections import Counter, defaultdict
from rq3_protocol import ARMS, PROMPT_SHA256, audit, validate
from run_rq3 import read_jsonl

ANNOTATION_FIELDS=['blind_id','reference_evidence','response','status_correct','unsupported_fix_claim','other_unsupported_claim','required_action_present','note']

def write_csv(path, fields, records):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(records)

def blind(args):
    cases=read_jsonl(args.input)
    validate(cases,args.expected_cases,args.expected_audit)
    by_id={r['case_id']:r for r in cases}
    responses=read_jsonl(args.responses)
    target_cases={r['case_id'] for r in cases if audit(r)} if args.audit_only else set(by_id)
    keys=[(r.get('case_id'),r.get('arm')) for r in responses if r.get('case_id') in target_cases]
    expected={(i,a) for i in target_cases for a in ARMS}
    if set(keys)!=expected or len(keys)!=len(expected):
        raise ValueError(f'Incomplete/duplicate generations for selected population: expected {len(expected)}, got {len(keys)}')
    for r in responses:
        if r.get('case_id') in target_cases and (r.get('system_sha256')!=PROMPT_SHA256 or 'response' not in r):
            raise ValueError('Input must consist of actual outputs for the same frozen prompt, not dry-run requests')
    if any(not by_id[i].get('reference_evidence') for i in target_cases):
        raise ValueError('Each selected case needs independently verified reference_evidence, not just the model-input taxonomy field.')
    rng=random.Random(args.shuffle_seed)
    retained=[r for r in responses if r.get('case_id') in target_cases]
    rng.shuffle(retained)
    annotations=[]; secret=[]
    for r in retained:
        row=by_id[r['case_id']]
        blind_id=uuid.uuid4().hex[:16].upper()
        annotations.append({'blind_id':blind_id,'reference_evidence':row['reference_evidence'],
            'response':r['response'],'status_correct':'','unsupported_fix_claim':'',
            'other_unsupported_claim':'','required_action_present':'','note':''})
        secret.append({'blind_id':blind_id,'case_id':r['case_id'],'arm':r['arm'],'gold_l1':row['l1_class'],
                       'gold_subtype':row['subtype'],'audit36':audit(row)})
    for path in (args.blind_csv,args.key_jsonl):
        if Path(path).exists():
            raise FileExistsError(f'Refusing to overwrite {path}; each blind run must remain immutable')
        Path(path).parent.mkdir(parents=True,exist_ok=True)
    write_csv(args.blind_csv,ANNOTATION_FIELDS,annotations)
    flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
    fd=os.open(args.key_jsonl,flags,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        for r in secret: f.write(json.dumps(r,sort_keys=True)+'\n')
    print(f'Created {len(annotations)} shuffled, arm-masked response rows. Do NOT open/share key file until labels are finalized.')

def mcnemar(a,b):
    n=a+b
    if n==0: return 1.0
    return min(1.0,2*sum(math.comb(n,k) for k in range(min(a,b)+1))/2**n)

def score(args):
    key=read_jsonl(args.key_jsonl)
    with open(args.blind_csv,encoding='utf-8-sig',newline='') as f: ann=list(csv.DictReader(f))
    ks={r['blind_id']:r for r in key}
    if len(ann)!=len(ks) or {r['blind_id'] for r in ann}!=set(ks):
        raise ValueError('Mismatch between blind annotations and key file')
    by_case=defaultdict(dict)
    actions_by_case=defaultdict(dict)
    for r in ann:
        ident=r['blind_id']
        v=r.get('status_correct','').strip()
        if v not in ('0','1'):
            raise ValueError(f'Incomplete/invalid status_correct for blind_id {ident}; require 0 or 1')
        for field in ('unsupported_fix_claim','other_unsupported_claim'):
            if r.get(field,'').strip() not in ('0','1'):
                raise ValueError(f'Incomplete/invalid {field} for blind_id {ident}; require 0 or 1')
        k=ks[ident]
        need=k['gold_l1']=='ABANDONED' and k['gold_subtype']=='NEEDS_INFO'
        redirect=k['gold_l1']=='REDIRECTED'
        action=r.get('required_action_present','').strip().upper()
        if need or redirect:
            if action not in ('0','1'):
                raise ValueError(f'required_action_present must be 0/1 for {ident}')
            actions_by_case[k['case_id']][k['arm']]=int(action)
        elif action!='NA':
            raise ValueError(f'required_action_present must be NA for non-action case {ident}')
        if k['arm'] in by_case[k['case_id']]: raise ValueError('Duplicate case-arm')
        by_case[k['case_id']][k['arm']]=int(v)
    for i,arms in by_case.items():
        if set(arms)!=set(ARMS): raise ValueError(f'Incomplete paired data for case {i}')
    pop=sorted(i for i in by_case if ks[next(r['blind_id'] for r in ann if ks[r['blind_id']]['case_id']==i)]['audit36'])
    out={'n_cases':len(by_case),'status_correct':{arm:sum(x[arm] for x in by_case.values()) for arm in ARMS},'audit36_n':len(pop)}
    out['audit36_status_correct']={arm:sum(by_case[i][arm] for i in pop) for arm in ARMS}
    comps={}
    for x,y in [('closure_aware','binary_state'),('raw_metadata','binary_state'),('closure_aware','raw_metadata')]:
        b=sum(by_case[i][x]==1 and by_case[i][y]==0 for i in pop)
        c=sum(by_case[i][x]==0 and by_case[i][y]==1 for i in pop)
        comps[x+'_vs_'+y]={'x_only_successes':b,'y_only_successes':c,'exact_mcnemar_two_sided_p':mcnemar(b,c)}
    out['paired_audit36']=comps
    action_stats={}
    for target_name,predicate in (
       ('NEEDS_INFO_request', lambda k:k['gold_l1']=='ABANDONED' and k['gold_subtype']=='NEEDS_INFO'),
       ('REDIRECTED_route_elsewhere',lambda k:k['gold_l1']=='REDIRECTED')):
        relevant={k['case_id'] for k in key if predicate(k) and k['case_id'] in by_case}
        action_stats[target_name]={arm:{'n':len(relevant),'passed':sum(actions_by_case[i][arm] for i in relevant)} for arm in ARMS}
    out['human_action_realization']=action_stats
    print(json.dumps(out,indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest='cmd',required=True)
    b=sp.add_parser('blind')
    b.add_argument('--input',required=True)
    b.add_argument('--responses',required=True)
    b.add_argument('--blind-csv',required=True)
    b.add_argument('--key-jsonl',required=True)
    b.add_argument('--audit-only',action='store_true',default=False)
    b.add_argument('--expected-cases',type=int,default=82)
    b.add_argument('--expected-audit',type=int,default=36)
    b.add_argument('--shuffle-seed',type=int,default=20261020)
    s=sp.add_parser('score')
    s.add_argument('--blind-csv',required=True)
    s.add_argument('--key-jsonl',required=True)
    s.add_argument('--report')
    args=ap.parse_args()
    {'blind':blind,'score':score}[args.cmd](args)
if __name__=='__main__':main()
