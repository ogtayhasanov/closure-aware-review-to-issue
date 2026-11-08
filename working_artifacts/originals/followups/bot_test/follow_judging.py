"""Score newly completed responses while generation continues; no scheduled task is created."""
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_experiment import OUT,read,response_jobs,judge

def spend():
    total=0.
    for name,prices in [('attempts_A.jsonl',(.15,.6)),('judge_attempts.jsonl',(.2,1.25))]:
        for r in read(OUT/name):
            u=r.get('raw_response',{}).get('usage') or {}
            total+=(u.get('prompt_tokens',0)*prices[0]+u.get('completion_tokens',0)*prices[1])/1e6
    return total

while True:
    try:
        jobs=response_jobs()
        completed={r['response_key'] for r in read(OUT/'judgments.jsonl')}
    except json.JSONDecodeError:
        time.sleep(1)
        continue
    missing=sum(j['response_key'] not in completed for j in jobs)
    if len(jobs)==1132 and not missing:
        print('All 1132 judgments complete.',flush=True)
        break
    if spend()>=.60:
        raise SystemExit('Pausing at USD 0.60 tracked OpenAI usage to preserve the budget reserve.')
    if missing>=20 or (len(jobs)==1132 and missing):
        if judge():
            raise SystemExit('Unresolved judge request; see failure ledger. No scores substituted.')
    else:
        time.sleep(10)
