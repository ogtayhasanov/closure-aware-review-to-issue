"""Select existing responses using provenance, never taxonomy correctness labels."""
import csv,hashlib,importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;FINAL=ROOT.parent/'final_exp';BOT=ROOT.parent/'bot_test';ROUTING=ROOT.parent/'routing_test'
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def dump(name,rows):
    with (ROOT/name).open('w',encoding='utf-8',newline='\n') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
spec=importlib.util.spec_from_file_location('frozen_provenance',FINAL/'scripts/closure_provenance.py');prov=importlib.util.module_from_spec(spec);spec.loader.exec_module(prov)
extra=set(json.loads((BOT/'sample_report.json').read_text(encoding='utf-8'))['extra_bots'])
inputs=read(FINAL/'inputs_taxonomy_only.jsonl');byid={r['input_id']:r for r in inputs}
api={r['case_id']:r for r in read(ROOT/'github_api_evidence.jsonl')}
samplecsv={(r['repo'],str(r['number'])):r for r in csvread(BOT/'sample.csv')}
samplerecords={(r['repo'],str(r['number'])):r for r in read(BOT/'sample_records.jsonl')}
choices=[]
for r in inputs:
    d={'input_id':r['input_id'],'dataset':r['dataset'],'case_id':r['case_id'],'repository':r['repository'],'number':r['number'],'excluded_from_all_analyses':r['excluded_from_all_analyses']}
    if r['dataset']=='bot_test':
        s=samplecsv[r['repository'],str(r['number'])];full=samplerecords[r['repository'],str(r['number'])]
        assert s['closed_by']==full['closed_by'] and s['closed_by_type']==full['closed_by_type']
        bot=prov.is_bot(s['closed_by'],s['closed_by_type'],extra)
        switch=bot and not full.get('closer')
        d.update({'source':'bot_test/sample.csv (linked closer verified in sample_records.jsonl)','closed_by':s['closed_by'],'closed_by_type':s['closed_by_type'],'state':'closed','linked_fix':bool(full.get('closer')),'switch':switch,'reason':'bot closed, no linked fix' if switch else 'human closure; use RAW'})
    elif r['case_id'] in api:
        a=api[r['case_id']];parts={x['kind']:x for x in a['results']}
        assert all('body' in x for x in parts.values())
        issue=parts['issue']['body'];events=parts['timeline']['body']
        assert len(events)<100,'Pagination required before selecting switch'
        closed=[e for e in events if e.get('event')=='closed']
        last=closed[-1] if closed else None
        actor=issue.get('closed_by') or {}
        if issue['state']=='closed':
            assert last is not None
            assert actor.get('login')==(last.get('actor') or {}).get('login')
        bot=issue['state']=='closed' and prov.is_bot(actor.get('login'),actor.get('type'),extra)
        linked=bool(last and last.get('commit_id'))
        if bot:
            # All five candidate timelines have no commit or PR links of any kind.
            assert not any(e.get('commit_id') or (e.get('source') or {}).get('issue',{}).get('pull_request') for e in events), 'Linked-fix investigation required'
        switch=bot and not linked
        d.update({'source':'GitHub API issue and complete REST timeline, refreshed 2026-11-01','closed_by':actor.get('login',''),'closed_by_type':actor.get('type',''),'state':issue['state'],'linked_fix':linked if bot else 'not required for non-bot decision','switch':switch,'reason':'bot closed, no linked fix in complete timeline' if switch else 'currently open; use raw' if issue['state']=='open' else 'non-bot closure; use raw'})
    else:
        d.update({'source':'non-GitHub tracker: raw response required','closed_by':'','closed_by_type':'','state':'','linked_fix':'not evaluated','switch':False,'reason':'other tracker; use raw'})
    choices.append(d)
assert len(choices)==162
choice={r['input_id']:r for r in choices}
with (ROOT/'switch_provenance.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(choices[0]));w.writeheader();w.writerows(choices)
setup=json.loads((ROUTING/'setup_manifest.json').read_text(encoding='utf-8'))
oldjudge=read(BOT/'judgments.jsonl')
core={}
for j in oldjudge:
    i=j['identity'];ds=i['dataset']
    if ds=='bot_test' and i['arm']=='RAW':model={'A':'gpt-4o-mini-2024-07-18','B':'gemma-4-26b-a4b-it'}[i['generator']];iid=f"bot_test:{i['repo']}#{i['number']}"
    elif ds in ['historical','main_gemma'] and i['arm']=='raw_metadata':model='gpt-4o-mini-2024-07-18' if ds=='historical' else 'gemma-4-26b-a4b-it';iid='fair:'+i['case_id']
    else:continue
    core[model,iid]=j
taxcore={r['score_id']:r for r in read(FINAL/'judge_core_scores.jsonl')}
taxroute={r['score_id']:r for r in read(FINAL/'judge_routing_scores.jsonl')}
key=csvread(FINAL/'audit_key.csv');sheet={r['sheet_id']:r for r in csvread(FINAL/'audit_sheet.csv')}
auditroute={r['score_id']:r for r in read(FINAL/'judge_audit_routing_scores.jsonl')}
auditprimary={r['sheet_id']:r for r in csvread(FINAL/'audit_primary_scores.csv')}
auditby={(r['case_id'],r['arm']):r for r in key}
references=[]
for model in ['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']:
    raw={}
    for r in read(BOT/f'responses_{model}.jsonl'):
        if r['arm']=='RAW':raw[f"bot_test:{r['repo']}#{r['number']}"]=r
    fair=read(Path(setup['source_files']['fair_responses']['path'])) if model.startswith('gpt') else read(BOT/'main_responses_gemma.jsonl')
    for r in fair:
        if r['arm']=='raw_metadata':raw['fair:'+r['case_id']]=r
    assert len(raw)==162
    tax={r['input_id']:r for r in read(FINAL/f'responses_taxonomy_only_{model}.jsonl')}
    for arm,rs in [('RAW',raw),('TAXONOMY-ONLY',tax)]:
        for iid,r in rs.items():
            meta=byid[iid];j=core[model,iid] if arm=='RAW' else taxcore[model+':'+iid]
            assert sha(r['response'])==j['response_sha256']
            row={k:meta[k] for k in ['input_id','dataset','case_id','repository','number','group','excluded_from_all_analyses']}
            row.update({'arm':arm,'model':model,'response':r['response'],'response_sha256':sha(r['response']),'judge_core':j['judge'],'core_source':'bot_test/judgments.jsonl' if arm=='RAW' else 'final_exp/judge_core_scores.jsonl','judge_routing':None,'judge_STATES_OUTCOME':None})
            if arm=='TAXONOMY-ONLY':row['judge_routing']=taxroute[model+':'+iid]['judge']
            ak=auditby.get((meta['case_id'],'raw_metadata' if arm=='RAW' else arm))
            if model.startswith('gpt') and ak:
                row['judge_STATES_OUTCOME']=auditprimary[ak['sheet_id']]['judge_STATES_OUTCOME']=='True'
                if arm=='RAW':row['judge_routing']=auditroute[ak['sheet_id']]['judge']
            references.append(row)
assert len(references)==648
dump('reference_responses_and_scores.jsonl',references)
switch=[];routingjobs=[]
for r in references:
    c=choice[r['input_id']]
    if r['arm']!=('TAXONOMY-ONLY' if c['switch'] else 'RAW'):continue
    switch.append({**r,'arm':'SWITCH','selected_source_arm':r['arm'],'switch_reason':c['reason']})
    if r['judge_routing'] is None:
        routingjobs.append({'score_id':r['model']+':reference:'+r['input_id'],'input_id':r['input_id'],'model':r['model'],'response_sha256':r['response_sha256'],'judge_user_message':r['response']})
assert len(switch)==324
existing_jobs={j['score_id'] for j in routingjobs}
audit_case_ids={r['case_id'] for r in key}
for r in references:
    sid=r['model']+':reference:'+r['input_id']
    if r['arm']=='RAW' and r['case_id'] in audit_case_ids and r['judge_routing'] is None and sid not in existing_jobs:
        routingjobs.append({'score_id':sid,'input_id':r['input_id'],'model':r['model'],'response_sha256':r['response_sha256'],'judge_user_message':r['response']})
        existing_jobs.add(sid)
dump('responses_switch.jsonl',switch);dump('reference_routing_inputs.jsonl',routingjobs)
manifest={'total_case_inputs':162,'bot_test_switched':sum(c['switch'] for c in choices if c['dataset']=='bot_test'),'fair_switched':sum(c['switch'] for c in choices if c['dataset']=='fair'),'github_fair_inputs_refetched':len(api),'non_github_fair_inputs':82-len(api),'existing_responses_selected':324,'new_generation_for_switch':0,'missing_provenance':0,'extra_bot_names':sorted(extra),'extra_routing_judgments_needed':len(routingjobs),'fair_switches':[{'case_id':c['case_id'],'repository':c['repository'],'number':c['number']} for c in choices if c['dataset']=='fair' and c['switch']]}
(ROOT/'switch_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,indent=2))
