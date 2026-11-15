"""Join complete scores without running the preregistered human-label analyses."""
import csv,hashlib,importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def module(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
bl=module('bot_check',OUT/'scripts/bot_lexical.py');rl=module('route_check',OUT/'scripts/routing_lexical.py')
cfg=load(OUT/'generation_settings.json')
records=[]
for tag in ['A','B']:
    r=read(OUT/f"responses_taxonomy_only_{cfg['generation'][tag]['model_requested']}.jsonl")
    assert len(r)==len({x['input_id'] for x in r})==162
    records+=r
core={r['score_id']:r for r in read(OUT/'judge_core_scores.jsonl')}
routing={r['score_id']:r for r in read(OUT/'judge_routing_scores.jsonl')}
assert len(core)==len(routing)==324
rows=[]
for r in records:
    key=r['model_requested']+':'+r['input_id'];c=core[key];t=routing[key]
    assert c['response_sha256']==t['response_sha256']==r['response_sha256']==hashlib.sha256(r['response'].encode()).hexdigest()
    b=bl.score(r['response']);q=rl.score(r['response'],r['number'])
    row={k:r[k] for k in ['input_id','dataset','case_id','repository','number','group','arm','model_requested','excluded_from_all_analyses','response_sha256']}
    row['judge_model']=c['judge_model']
    for name in ['DECLINED','FIX_CLAIM','INACTIVITY']:row['judge_'+name]=c['judge'][name];row['lexical_'+name]=b[name]
    for name in ['ASKS_DETAILS','SAYS_DUPLICATE']:row['judge_'+name]=t['judge'][name];row['lexical_'+name]=q[name]
    rows.append(row)
def write(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
write('auto_scores.csv',rows)
audit=list(csv.DictReader((OUT/'audit_lexical_scores.csv').open(encoding='utf-8-sig')))
aj={r['score_id']:r for r in read(OUT/'judge_audit_scores.jsonl')}
arj={r['score_id']:r for r in read(OUT/'judge_audit_routing_scores.jsonl')}
assert len(audit)==len(aj)==len(arj)==140
ar=[]
for r in audit:
    j=aj[r['sheet_id']];jr=arj[r['sheet_id']];assert r['response_sha256']==j['response_sha256']==jr['response_sha256']
    ar.append({**r,'judge_NO_FALSE_FIX':j['judge']['NO_FALSE_FIX'],'judge_STATES_OUTCOME':j['judge']['STATES_OUTCOME'],'judge_model':j['judge_model'],
        'judge_ASKS_DETAILS':jr['judge']['ASKS_DETAILS'] if r['lexical_ASKS_DETAILS']!='NA' else 'NA',
        'judge_SAYS_DUPLICATE':jr['judge']['SAYS_DUPLICATE'] if r['lexical_SAYS_DUPLICATE']!='NA' else 'NA'})
write('audit_auto_scores.csv',ar)
usage=[]
for stage,name in [('generation_A','generation_attempts_A.jsonl'),('generation_B','generation_attempts_B.jsonl'),('judge_core','judge_core_attempts.jsonl'),('judge_routing','judge_routing_attempts.jsonl'),('judge_audit','judge_audit_attempts.jsonl'),('judge_audit_routing','judge_audit_routing_attempts.jsonl')]:
    data=read(OUT/name);totals={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
    for r in data:
        u=r.get('usage') or r.get('raw_response',{}).get('usage',{})
        for k in totals:totals[k]+=u.get(k,0)
    usage.append({'stage':stage,'billed_attempts_recorded':len(data),**totals})
write('api_usage.csv',usage)
manifest={'new_final_responses':324,'responses_per_generator':162,'core_judge_scores':len(core),'routing_judge_scores':len(routing),'audit_judge_scores':len(aj),'audit_routing_judge_scores':len(arj),
 'all_new_responses_scored':True,'analysis_exclusion_rows':sum(r['excluded_from_all_analyses'] for r in records),
 'excluded_case':'nextcloud/android#2131 (one response per generator; retained but excluded from all analyses)',
 'missing_responses':0,'missing_scores':0,'human_label_analysis':'pending; no primary tests performed',
 'files':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['auto_scores.csv','audit_auto_scores.csv','api_usage.csv']}}
(OUT/'completion_audit.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,indent=2))
