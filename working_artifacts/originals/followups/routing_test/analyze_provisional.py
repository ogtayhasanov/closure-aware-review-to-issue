"""Authorized lexical-only routing and tracker-evidence FIX_CLAIM analysis.

No generation, no new judge, no changes to frozen inputs or human sheets.
"""
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
import lexical
OUT=Path(__file__).resolve().parent
REFRESH=OUT/'tracker_refresh_20261101'
BOT=OUT.parent/'bot_test'
ARMS=('binary_state','raw_metadata','closure_aware')
MODELS={'historical':'GPT-4o-mini','main_gemma':'Gemma'}
AMENDMENT_COMMIT='a24ebf36f75bbe23429efe9022ba22d7915d1b3a'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def csvwrite(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,data): (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def wilson(k,n):
    if n==0:return None,None
    z=1.959963984540054;p=k/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0.,center-half),min(1.,center+half)
def rate(k,n):
    lo,hi=wilson(k,n)
    return f'{k}/{n} ({100*k/n:.1f}%; {100*lo:.1f}–{100*hi:.1f})' if n else 'unavailable (n=0)'
def mcnemar(a,b):
    assert set(a)==set(b)
    a_only=sum(a[c] and not b[c] for c in a)
    b_only=sum(b[c] and not a[c] for c in a)
    d=a_only+b_only
    p=min(1.,2*sum(math.comb(d,i) for i in range(min(a_only,b_only)+1))/(2**d)) if d else 1.
    return {'pairs':len(a),'taxonomy_only':a_only,'raw_only':b_only,'p_exact_two_sided':p}
def holm(rows):
    prev=0.
    for pos,idx in enumerate(sorted(range(len(rows)),key=lambda i:rows[i]['p_exact_two_sided'])):
        prev=max(prev,min(1.,(len(rows)-pos)*rows[idx]['p_exact_two_sided']))
        rows[idx]['p_holm']=prev

setup=load(OUT/'setup_manifest.json');blind_manifest=load(OUT/'checkpoint3_manifest.json')
source_paths=[Path(info['path']) for info in setup['source_files'].values()]
source_paths += [BOT/'judgments.jsonl',OUT/'lexical.py',OUT/'lexical_scores.jsonl',OUT/'case_registry.csv']
source_paths += list(REFRESH.glob('*.json'))
protected=[OUT/name for name in ['blind_sheet.csv','gemma_blind_sheet.csv','blind_key.csv','gemma_blind_key.csv']]
before={str(p):sha(p) for p in source_paths+protected}
for info in setup['source_files'].values():assert sha(Path(info['path']))==info['sha256']
assert sha(OUT/'lexical.py')==blind_manifest['lexical_sha256']
assert sha(OUT/'lexical_scores.jsonl')==blind_manifest['lexical_scores_sha256']
assert abs(wilson(0,50)[1]-.071347599)<1e-8
assert mcnemar(dict.fromkeys(range(10),True),dict.fromkeys(range(10),False))['p_exact_two_sided']==.001953125
dummy=[{'p_exact_two_sided':p} for p in [.01,.03,.04]];holm(dummy)
assert [round(r['p_holm'],2) for r in dummy]==[.03,.06,.06]

cases=read(Path(setup['source_files']['cases']['path']));byid={r['case_id']:r for r in cases}
registry={r['case_id']:r for r in csvread(OUT/'case_registry.csv')}
assert len(cases)==len(byid)==len(registry)==82
responses={}
for dataset,source in [('historical','fair_responses'),('main_gemma','gemma_responses')]:
    rows=read(Path(setup['source_files'][source]['path']))
    assert len(rows)==246
    for r in rows:
        key=(dataset,r['case_id'],r['arm']);assert key not in responses
        responses[key]=r

# Refresh records report observations and distinguish final closure from earlier events.
refreshed=[]
for number in [3425,2131]:
    issue=load(REFRESH/f'issue_{number}_issue_connector.json')['structuredContent']['issue']
    timeline=load(REFRESH/f'issue_{number}_timeline_page1.json')
    assert len(timeline)<100,'Timeline pagination required'
    closes=[e for e in timeline if e['event']=='closed']
    final=max(closes,key=lambda e:e['created_at'])
    reopened=[e for e in timeline if e['event']=='reopened']
    r={'number':number,'issue_url':issue['url'],'state':issue['state'],'current_state_reason':issue['state_reason'],
       'final_closed_at':final['created_at'],'final_closed_by':final['actor']['login'],
       'final_closing_commit_id':final.get('commit_id'),'closure_count':len(closes),'reopen_count':len(reopened),
       'timeline_events':len(timeline),'timeline_complete':True,'fetched_date':'2026-11-01'}
    if number==2131:
        pr=load(REFRESH/'pull_4470.json')
        assert pr['merged'] and 'closes #2131' in pr['body'].lower()
        assert pr['merged_at']=='2019-10-01T09:15:30Z' and final['created_at']=='2019-10-01T09:15:31Z'
        r.update({'observed_closure_reason':'Merged fix PR #4470: Normalize local target path in auto upload; explicitly closes #2131.',
           'supporting_url':pr['html_url'],'merged_at':pr['merged_at'],'merge_commit_sha':pr['merge_commit_sha'],
           'status_for_step5':'FIXED','earlier_bot_closure':'2019-05-23T21:23:11Z; reopened 2019-07-30T05:51:40Z'})
    else:
        close_comments=[e for e in timeline if e['event']=='commented' and e['created_at']==final['created_at']]
        assert len(close_comments)==1 and close_comments[0]['user']['login']==final['actor']['login']
        r.update({'observed_closure_reason':'Manual closure at the time of maintainer advice to disable Samsung battery restrictions and inspect logs. No linked closing fix commit or PR in the complete timeline.',
           'supporting_url':close_comments[0]['html_url'],'supporting_comment':close_comments[0]['body'],
           'status_for_step5':'UNCERTAIN','inference_limit':'Configuration-advice context is observable; generic completed status is not proof of a code fix or a native NOT FIXED resolution code.'})
    refreshed.append(r)
dump('tracker_refresh_summary.json',refreshed)
refresh_by_number={r['number']:r for r in refreshed}

# Routing: use exactly the already saved lexical labels, verifying against response text.
lexical_rows=read(OUT/'lexical_scores.jsonl')
assert len(lexical_rows)==138
route={}
for row in lexical_rows:
    dataset='historical' if row['model']=='GPT-4o-mini' else 'main_gemma'
    key=(dataset,row['case_id'],row['arm'])
    r=responses[key];c=byid[row['case_id']]
    assert row['response_sha256']==hashlib.sha256(r['response'].encode()).hexdigest()
    assert lexical.score(r['response'],c['display_issue_id'],None)==row['lexical']
    assert key not in route;route[key]=row
route_rates=[];paired=[]
for dataset,model in MODELS.items():
    tests=[]
    for question,cohort in [('ASKS_DETAILS','NEEDS_INFO'),('SAYS_DUPLICATE','REDIRECTED')]:
        ids={cid for cid,r in registry.items() if r['cohort']==cohort}
        for arm in ARMS:
            values=[route[dataset,cid,arm]['lexical'][question] for cid in ids]
            k=sum(values);n=len(values);lo,hi=wilson(k,n)
            route_rates.append({'model':model,'arm':arm,'question':question,'cohort':cohort,'positive':k,'n':n,
                'percentage':100*k/n,'wilson95_lower':lo,'wilson95_upper':hi,'label_source':'frozen lexical only; provisional'})
        test={'model':model,'question':question,**mcnemar(
            {cid:route[dataset,cid,'closure_aware']['lexical'][question] for cid in ids},
            {cid:route[dataset,cid,'raw_metadata']['lexical'][question] for cid in ids})}
        tests.append(test)
    holm(tests);paired.extend(tests)
csvwrite('provisional_routing_rates.csv',route_rates)
csvwrite('provisional_routing_paired_tests.csv',paired)

# True-status split: no taxonomy class or subtype is consulted here.
status_rows=[]
for c in cases:
    native=c['raw_tracker_fields'];resolution=str(native.get('resolution','')).upper()
    status='UNCERTAIN';source='retained_tracker_fields';reason='Insufficient tracker evidence for requested FIXED/NOT FIXED definitions'
    evidence=json.dumps(native,sort_keys=True,ensure_ascii=False)
    link=c['issue_url']
    if c['binary_state']=='closed' and resolution=='FIXED':
        status='FIXED';reason=f'Native tracker resolution={resolution}'
    elif c['binary_state']=='closed' and resolution in {'WORKSFORME','INCOMPLETE','INVALID','DUPLICATE'}:
        status='NOT FIXED';reason=f'Native tracker resolution={resolution}'
    elif 'GitHub' in c['repository'] and int(c['display_issue_id']) in refresh_by_number:
        ref=refresh_by_number[int(c['display_issue_id'])]
        status=ref['status_for_step5'];reason=ref['observed_closure_reason'];link=ref['supporting_url']
        source='refreshed GitHub timeline and PR' if status=='FIXED' else 'refreshed GitHub timeline and closing comment'
        evidence=json.dumps(ref,sort_keys=True,ensure_ascii=False)
    elif c['binary_state']=='open':reason='Open case: UNCERTAIN under the requested three-way split'
    elif resolution=='NOTVLC':reason='Native notvlc resolution is outside the four requested NOT FIXED codes'
    elif 'GitHub' in c['repository'] and native.get('state_reason')=='completed':
        reason='GitHub completed without a verified closing fix commit/merged PR in retained evidence'
    elif 'GitHub' in c['repository']:
        reason='Closed GitHub case; labels alone do not establish requested native status or a code fix'
    status_rows.append({'case_id':c['case_id'],'repository':c['repository'],'issue_number':c['display_issue_id'],
        'true_status':status,'status_source':source,'reason':reason,'native_resolution':native.get('resolution',''),
        'evidence_url':link,'evidence':evidence,'retained_source_provenance':c['data_provenance_status'],
        'taxonomy_used_for_status':False})
status_byid={r['case_id']:r for r in status_rows}
assert len(status_byid)==82
status_counts=collections.Counter(r['true_status'] for r in status_rows)
assert sum(status_counts.values())==82
assert status_counts=={'FIXED':16,'NOT FIXED':24,'UNCERTAIN':42}
csvwrite('true_status_registry.csv',status_rows)
csvwrite('uncertain_status_cases.csv',[r for r in status_rows if r['true_status']=='UNCERTAIN'])
judgments={}
for j in read(BOT/'judgments.jsonl'):
    ident=j['identity'];dataset=ident['dataset']
    if dataset not in MODELS:continue
    key=(dataset,ident['case_id'],ident['arm'])
    assert key not in judgments and key in responses
    assert j['response_sha256']==hashlib.sha256(responses[key]['response'].encode()).hexdigest()
    judgments[key]=j
assert set(judgments)==set(responses) and len(judgments)==492
fix_rates=[];fix_records=[]
for dataset,model in MODELS.items():
    for arm in ARMS:
        for label_source in ['judge','lexical']:
            def count(status,positive):
                ids=[cid for cid,r in status_byid.items() if r['true_status']==status]
                return sum(judgments[dataset,cid,arm][label_source]['FIX_CLAIM']==positive for cid in ids),len(ids)
            false,nnot=count('NOT FIXED',True);missed,nfixed=count('FIXED',False);unknown,nunc=count('UNCERTAIN',True)
            falseci=wilson(false,nnot);missci=wilson(missed,nfixed)
            fix_rates.append({'model':model,'arm':arm,'fix_claim_score_source':label_source,
                'false_fix_claims':false,'NOT_FIXED_n':nnot,'false_fix_percentage':100*false/nnot,
                'false_fix_wilson95_lower':falseci[0],'false_fix_wilson95_upper':falseci[1],
                'missed_fixes':missed,'FIXED_n':nfixed,'missed_fix_percentage':100*missed/nfixed,
                'missed_fix_wilson95_lower':missci[0],'missed_fix_wilson95_upper':missci[1],
                'UNCERTAIN_n':nunc,'uncertain_FIX_CLAIM_occurrences':unknown})
        for cid in byid:
            j=judgments[dataset,cid,arm]
            fix_records.append({'model':model,'case_id':cid,'arm':arm,'repository':byid[cid]['repository'],
                'issue_number':byid[cid]['display_issue_id'],'true_status':status_byid[cid]['true_status'],
                'judge_FIX_CLAIM':j['judge']['FIX_CLAIM'],'lexical_FIX_CLAIM':j['lexical']['FIX_CLAIM'],
                'response_sha256':j['response_sha256'],'judge_model':j['model_id']})
csvwrite('fix_claim_by_true_status.csv',fix_rates)
csvwrite('fix_claim_case_scores.csv',fix_records)
dump('provisional_statistics.json',{'routing_rates':route_rates,'routing_paired_tests':paired,
    'status_counts':dict(status_counts),'fix_claim_by_true_status':fix_rates,'human_agreement_kappa':None,
    'human_agreement_status':'Unavailable: no completed routing human labels used'})

text=['# Provisional routing and tracker-status results — 1 November 2026','',
    '**Lexical-only routing results. Human validation is pending.** The user authorized this analysis on '
    '1 November 2026, superseding the wait for labels for these provisional results. No new generation or judging '
    'was performed. The paper, original responses, prompts, earlier checkpoints, and human annotation sheets remain unchanged.', '',
    '## Two refreshed Nextcloud closures','',
    '**[#2131](https://github.com/nextcloud/android/issues/2131) is FIXED under the requested evidence rule.** '
    '[PR #4470](https://github.com/nextcloud/android/pull/4470), “Normalize local target path in auto upload”, '
    'explicitly says “This closes #2131 and closes #4220.” It merged on 1 October 2019 at 09:15:30 UTC; '
    'the final issue-close event follows at 09:15:31 UTC. An earlier stale-bot closure on 23 May 2019 '
    'was reopened on 30 July. The historical ABANDONED/OTHER fallback therefore does not describe the final outcome.', '',
    '**[#3425](https://github.com/nextcloud/android/issues/3425) was closed manually with configuration advice.** '
    'tobiasKaminsky closed it on 14 January 2019 at 06:48:34 UTC, at the same time as '
    '[advice about Samsung battery restrictions and logs](https://github.com/nextcloud/android/issues/3425#issuecomment-453913811). '
    'Its complete eight-event timeline contains no closing fix commit or PR. The current generic state_reason is '
    'completed, but that alone does not prove a code fix. It remains UNCERTAIN under the strict amended status rule. '
    'The observed context is configuration advice, not evidence of abandonment. Raw snapshots, comments, timelines, '
    'and the merged PR are retained in `tracker_refresh_20261101/`.', '',
    'This refresh corrects the earlier interpretation that the two cases might simply be dropped from 36 to obtain '
    '34 confirmed non-resolved cases: one is demonstrably fixed and the other lacks sufficient status evidence. '
    'The other 34 taxonomy-defined non-resolved cases are not all independently validated either. '
    'No frozen cohort or input was retrospectively repaired.', '',
    '## Routing rates','',
    'The 23 registered routing cases are retained (16 NEEDS_INFO, 7 REDIRECTED), with all three responses per '
    'case for each model. The other 59 cases are individually accounted for in `exclusions.csv`. '
    'Routing cohorts use the registered taxonomy-input fallback only for selection; taxonomy is not an answer key. '
    'The already frozen lexical rules and 138 saved lexical records were verified against exact response hashes. '
    'Each entry below is positive count / case count, percentage, and Wilson 95% interval.', '',
    '| Model | Arm | ASKS_DETAILS (n=16) | SAYS_DUPLICATE (n=7) |',
    '|---|---|---|---|']
for model in MODELS.values():
    for arm in ARMS:
        rr={r['question']:r for r in route_rates if r['model']==model and r['arm']==arm}
        text.append(f"| {model} | {arm} | {rate(rr['ASKS_DETAILS']['positive'],16)} | {rate(rr['SAYS_DUPLICATE']['positive'],7)} |")
text += ['', 'The frozen lexical check does not reproduce the old large raw-versus-taxonomy separation. '
    'With fair prompts, raw already requests details in 12/16 GPT-4o-mini cases and 14/16 Gemma cases, '
    'compared with 14/16 and 15/16 under taxonomy. Both arms flag duplicates in 7/7 cases for both models. '
    'This provisional evidence does not establish a taxonomy routing advantage; it also cannot prove equivalence.', '',
    'A concrete lexical limitation is visible in the GPT-4o-mini binary SAYS_DUPLICATE count: '
    'the sole positive is VLC #20777, where the response says “duplicated entries”. That describes playlist content, '
    'not a duplicate tracker issue. The frozen lexical result remains 1/7 and is explicitly flagged here as a '
    'semantic false positive. It is not silently corrected or presented as a human-confirmed routing success.', '',
    '### Paired taxonomy versus raw comparisons','',
    'Exact two-sided McNemar, paired by case. Holm adjustment is across the two routing questions within each '
    'generator. Binary is shown for reference only. These automated comparisons are provisional; they do not replace '
    'human coding. Non-significance does not establish equivalence.', '',
    '| Model | Question | Pairs | Taxonomy only | Raw only | Exact p | Holm p |',
    '|---|---|---:|---:|---:|---:|---:|',
    *[f"| {r['model']} | {r['question']} | {r['pairs']} | {r['taxonomy_only']} | {r['raw_only']} | {r['p_exact_two_sided']:.6g} | {r['p_holm']:.6g} |" for r in paired], '',
    'Canonical issue targets were absent from every original arm for all seven REDIRECTED cases. '
    'GIVES_CANONICAL therefore remains descriptive/unassessable; it is not counted as seven failures. '
    'The new SAYS_DUPLICATE definition includes an explicit duplicate statement. The old paper endpoint required '
    'explicit routing elsewhere and was narrower, so the old 7/7 versus 0/7 endpoint is not numerically interchangeable.', '',
    'Human-label agreement and Cohen’s kappa are **unavailable**. Both 69-row blind sheets already exist for later '
    'annotation and were left unchanged. Any later annotation after seeing these results should be described as '
    'arm-masked, but not fully independent of the aggregate findings. Lexical patterns can miss paraphrases or '
    'misread requests and negation; no patterns were adjusted after inspecting outcomes.', '',
    '## FIX_CLAIM by tracker-supported status','',
    '**82 input cases: 16 FIXED, 24 NOT FIXED, 42 UNCERTAIN.** These are review/issue cases, not 82 unique tracker issues. '
    'All three arms share the same status registry. Repeated issues are retained because the paired experiment '
    'contains different reviews; possible dependence between those cases limits inference.', '',
    '- FIXED: 8 Bugzilla FIXED + 7 Trac fixed + Nextcloud #2131 with a verified closing merged fix PR.',
    '- NOT FIXED: closed native WORKSFORME, INCOMPLETE, INVALID, or DUPLICATE codes (case-insensitive).',
    '- UNCERTAIN: 11 open cases, 1 Trac notvlc case, and 30 GitHub closed cases without the specific FIXED/NOT FIXED evidence required here.', '',
    'The 30 uncertain GitHub cases include repeated retrieved issues. Generic completed state and stale/needs-info '
    'labels do not establish a code fix or one of the requested resolution codes. This phase refreshed the two '
    'requested GitHub issues; it did not independently re-fetch and adjudicate every remaining GitHub case. '
    'Bugzilla/Trac codes are the retained native-resolution fields, originally reconstructed from the legacy export '
    'and not re-fetched in this phase. Those provenance limits are retained per row. No taxonomy class enters '
    'the status-assignment function. See `true_status_registry.csv` and the explicit 42-row uncertain list.', '',
    'Reuse of the existing FIX_CLAIM judge labels is shown first (GPT-5.4 nano; no new calls). All 492 response '
    'hashes and judgments matched. Rates concern tracker-status errors: they are not equivalent to prompt '
    'faithfulness, especially where newly verified fix evidence was absent from the original input.', '',
    '| Model | Arm | False fix claims / NOT FIXED | Missed fixes / FIXED | UNCERTAIN | FIX_CLAIM within UNCERTAIN |',
    '|---|---|---|---|---:|---:|']
for r in fix_rates:
    if r['fix_claim_score_source']!='judge':continue
    text.append(f"| {r['model']} | {r['arm']} | {rate(r['false_fix_claims'],r['NOT_FIXED_n'])} | {rate(r['missed_fixes'],r['FIXED_n'])} | {r['UNCERTAIN_n']} | {r['uncertain_FIX_CLAIM_occurrences']} |")
text += ['', 'FIX_CLAIM occurrences in UNCERTAIN cases are not labeled false. No uncertain case was silently '
    'dropped, reclassified through taxonomy, or included in the false-fix or missed-fix denominators.', '',
    '### Existing lexical FIX_CLAIM sensitivity check','',
    '| Model | Arm | False fix claims / 24 | Missed fixes / 16 | FIX_CLAIM within 42 UNCERTAIN |',
    '|---|---|---:|---:|---:|']
for r in fix_rates:
    if r['fix_claim_score_source']=='lexical':
        text.append(f"| {r['model']} | {r['arm']} | {r['false_fix_claims']}/24 | {r['missed_fixes']}/16 | {r['uncertain_FIX_CLAIM_occurrences']} |")
text += ['', 'Full Wilson intervals for both score sources are in `fix_claim_by_true_status.csv`. '
    '`fix_claim_case_scores.csv` retains all 492 case/arm scores with their status and response hash.', '',
    '## Files, reproducibility, and pending work','',
    '- `provisional_routing_rates.csv` and `provisional_routing_paired_tests.csv`: lexical routing rates and paired tests.',
    '- `provisional_statistics.json`: all provisional counts and statistical outputs.',
    '- `true_status_registry.csv` and `uncertain_status_cases.csv`: evidence, source, reason, and status for every case.',
    '- `tracker_refresh_summary.json`: the two refreshed closure histories and specific supporting links.',
    '- `analysis_manifest_20261101.json`: source hashes, unchanged-file checks, amendments, and output hashes.', '',
    'Authorized Steps 1–3 are complete. The intended primary human routing audit remains pending. '
    'Steps 4–10 in the user’s 1 November list are deferred until after Masaryk. No taxonomy-only arm, third '
    'generator/judge, specific-reason scorer, prevalence split, table recomputation, retrieval ablation, or release '
    'package was started in this phase. The manuscript remains unchanged.']
(OUT/'results.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
assert before=={str(p):sha(p) for p in source_paths+protected}
outputs=['results.md','tracker_refresh_summary.json','provisional_routing_rates.csv','provisional_routing_paired_tests.csv',
         'true_status_registry.csv','uncertain_status_cases.csv','fix_claim_by_true_status.csv','fix_claim_case_scores.csv','provisional_statistics.json']
dump('analysis_manifest_20261101.json',{'date':'2026-11-01','user_amendment_commit':AMENDMENT_COMMIT,
    'analysis_script_sha256':sha(Path(__file__)),
    'lexical_frozen_commit':blind_manifest['lexical_commit'],'source_sha256':before,'sources_and_blind_sheets_unchanged':True,
    'outputs_sha256':{name:sha(OUT/name) for name in outputs},'new_generation_count':0,'new_judge_count':0,
    'routing_lexical_records':138,'fix_claim_judgment_records':492,'status_counts':dict(status_counts),
    'human_validation_pending':True,'human_primary_labels_used':0,'deferred_steps':[4,5,6,7,8,9,10]})
print(json.dumps({'routing_rates':route_rates,'paired':paired,'statuses':dict(status_counts),
                  'fix_judge':[r for r in fix_rates if r['fix_claim_score_source']=='judge']},indent=2))
