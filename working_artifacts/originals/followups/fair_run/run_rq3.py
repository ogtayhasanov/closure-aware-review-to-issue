#!/usr/bin/env python3
"""Generate all three TOSEM RQ3 arms with a frozen prompt; supports dry-run and resume.
Requires OPENAI_API_KEY in the local environment to call the API. Never paste keys
into files or chat. Uses Python standard library only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import urllib.error
import urllib.request
from rq3_protocol import ARMS, VERSION, PROMPT_SHA256, audit, render, validate

MODEL='gpt-4o-mini-2024-07-18'  # Same snapshot described in prior manuscript.
SEED=20261020

def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]

def append_jsonl(path, record):
    with open(path,'a',encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True)+'\n')
        f.flush()
        os.fsync(f.fileno())

def complete_key(record):
    return (record['case_id'], record['arm'])

def call_openai(messages, model, seed, max_retries=5):
    token = os.environ.get('OPENAI_API_KEY')
    if not token:
        raise RuntimeError('OPENAI_API_KEY is not set; use --dry-run to prepare calls without an API key')
    base=os.environ.get('OPENAI_BASE_URL','https://api.openai.com/v1').rstrip('/')
    payload={'model':model,'messages':messages,'temperature':0,'max_tokens':220,'seed':seed}
    data=json.dumps(payload).encode('utf-8')
    request=urllib.request.Request(base+'/chat/completions',data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(request,timeout=120) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            detail=e.read().decode('utf-8',errors='replace')[:1200]
            if e.code not in (429,500,502,503,504) or attempt == max_retries-1:
                raise RuntimeError(f'API status={e.code}: {detail}') from e
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt == max_retries-1:
                raise
        time.sleep(min(2**attempt,20))
    raise AssertionError('unreachable')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--expected-cases',type=int,default=82)
    p.add_argument('--expected-audit',type=int,default=36)
    p.add_argument('--model',default=MODEL)
    p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--dry-run',action='store_true',help='Write request payloads but make no API calls')
    p.add_argument('--only-audit36',action='store_true',help='Limit to 36, but FULL run is needed for 82-case metrics')
    args=p.parse_args()
    rows=read_jsonl(args.input)
    summary=validate(rows,args.expected_cases,args.expected_audit)
    print(json.dumps(summary,indent=2))
    jobs=[(row,arm) for row in sorted(rows,key=lambda r:r['case_id']) for arm in ARMS if not args.only_audit36 or audit(row)]
    random.Random(args.seed).shuffle(jobs)  # avoid fixed arm/time order
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    existing=read_jsonl(output) if output.exists() else []
    keys=[complete_key(r) for r in existing]
    if len(keys)!=len(set(keys)):
        raise ValueError('Output contains duplicated (case_id, arm) rows')
    present=set(keys)
    # Prevent accidental mixing of prompt versions or models in resumed output.
    for r in existing:
        if r.get('system_sha256')!=PROMPT_SHA256 or r.get('model_requested')!=args.model or r.get('protocol')!=VERSION or r.get('seed')!=args.seed:
            raise ValueError('Resume would mix different prompt/model/seed versions. Use a new output path.')
    if not args.dry_run and not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('Set OPENAI_API_KEY in your local environment (do not share it in chat)')
    for pos,(row,arm) in enumerate(jobs,1):
        if (row['case_id'],arm) in present: continue
        messages=render(row,arm)
        prefix={'case_id':row['case_id'],'arm':arm,'protocol':VERSION,'system_sha256':PROMPT_SHA256,
                'model_requested':args.model,'seed':args.seed,'audit36':audit(row),
                'messages_sha256':hashlib.sha256(json.dumps(messages,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
        if args.dry_run:
            record={**prefix,'messages':messages,'dry_run':True}
        else:
            result=call_openai(messages,args.model,args.seed)
            answer=result['choices'][0]['message'].get('content') or ''
            if not answer.strip():
                raise RuntimeError(f'Blank response for {row["case_id"]} {arm}; aborting without writing it')
            record={**prefix,'response':answer,'model_returned':result.get('model'),
                    'system_fingerprint':result.get('system_fingerprint'),
                    'response_id':result.get('id'),'created':result.get('created'),
                    'finish_reason':result['choices'][0].get('finish_reason'),
                    'usage':result.get('usage')}
        append_jsonl(output,record)
        print(f'[{pos}/{len(jobs)}] {row["case_id"]} {arm}',flush=True)
    print('Finished. Dry-run files contain requests ONLY, not generated responses.' if args.dry_run else 'Completed real API generation; verify response_count and finish_reason before evaluation.')

if __name__=='__main__': main()
