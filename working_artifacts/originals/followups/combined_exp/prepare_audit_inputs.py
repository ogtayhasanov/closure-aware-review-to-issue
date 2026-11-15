"""Prepare masked evidence-only audit judging for combined and Gemma comparators."""
import csv,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FINAL=ROOT.parent/'final_exp';BOT=ROOT.parent/'bot_test'
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
key=rows(FINAL/'audit_key.csv');sheet={r['sheet_id']:r for r in rows(FINAL/'audit_sheet.csv')}
evidence={k['case_id']:sheet[k['sheet_id']]['tracker_evidence'] for k in key}
assert len(evidence)==35
models=['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']
jobs=[]
for model in models:
    rs=read(ROOT/f'responses_raw_meaning_{model}.jsonl')
    assert len(rs)==162
    for r in rs:
        if r['dataset']=='fair' and r['case_id'] in evidence:
            jobs.append({'score_id':model+':'+r['input_id'],'case_id':r['case_id'],'model':model,'response_sha256':r['response_sha256'], 'tracker_evidence_sha256':hashlib.sha256(evidence[r['case_id']].encode()).hexdigest(),'judge_user_message':'TRACKER EVIDENCE:\n'+evidence[r['case_id']]+'\n\nRESPONSE:\n'+r['response']})
model=models[1]
for arm,rs in [('raw_metadata',read(BOT/'main_responses_gemma.jsonl')),('TAXONOMY-ONLY',read(FINAL/f'responses_taxonomy_only_{model}.jsonl'))]:
    for r in rs:
        if r.get('arm')==arm and r['case_id'] in evidence:
            jobs.append({'score_id':model+':reference:'+arm+':'+r['case_id'],'case_id':r['case_id'],'model':model,'response_sha256':hashlib.sha256(r['response'].encode()).hexdigest(),'tracker_evidence_sha256':hashlib.sha256(evidence[r['case_id']].encode()).hexdigest(),'judge_user_message':'TRACKER EVIDENCE:\n'+evidence[r['case_id']]+'\n\nRESPONSE:\n'+r['response']})
assert len(jobs)==len({j['score_id'] for j in jobs})==140, len(jobs)
with (ROOT/'audit_judge_inputs.jsonl').open('w',encoding='utf-8',newline='\n') as f:
    for j in jobs:f.write(json.dumps(j,ensure_ascii=False,sort_keys=True)+'\n')
print('Prepared 70 combined audit responses and 70 existing Gemma comparator responses; evidence and response only.',flush=True)
