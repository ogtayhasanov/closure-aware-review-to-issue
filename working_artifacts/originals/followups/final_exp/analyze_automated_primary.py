"""Apply the committed short-check amendment; never alter existing model scores."""
import collections,csv,hashlib,json,math,random,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent;BOT=OUT.parent/'bot_test';ROUTING=OUT.parent/'routing_test'
AMENDMENT='dbfeb186e02996c4749b1ef67caf54e5d01fff18'
ARMS=('binary_state','raw_metadata','closure_aware','TAXONOMY-ONLY')
QUESTIONS=('NO_FALSE_FIX','STATES_OUTCOME','ASKS_DETAILS','SAYS_DUPLICATE')
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def txtsha(s):return hashlib.sha256(s.encode()).hexdigest()
def writecsv(name,rows):
    p=OUT/name
    if name=='audit_short_sheet.csv' and p.exists():
        existing=csvread(p)
        assert len(existing)==len(rows)
        for old,new in zip(existing,rows):
            for field in ['sheet_id','issue_url','tracker_evidence','response']:assert old[field]==new[field],'Existing short sheet content changed'
            for q in ['ASKS_DETAILS','SAYS_DUPLICATE']:
                if new[q]=='NA':assert old[q]=='NA','Existing NA applicability changed'
        return  # Preserve every human label and note, even on deterministic reruns.
    if name=='audit_short_key.csv' and p.exists():
        assert csvread(p)==rows,'Existing selection key differs'
        return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def boolean(v):
    if v in ['True','TRUE','YES','Yes','1',True]:return True
    if v in ['False','FALSE','NO','No','0',False]:return False
    if v in ['',None,'None','NA']:return None
    raise ValueError('Unexpected score: '+str(v))
def wilson(k,n):
    if n==0:return None,None
    z=1.959963984540054;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0,c-h),min(1,c+h)
def rate(k,n):
    lo,hi=wilson(k,n)
    return f'{k}/{n} ({100*k/n:.1f}%; {100*lo:.1f}–{100*hi:.1f})' if n else 'n/a'
def mc(a,b):
    assert set(a)==set(b)
    ao=sum(a[k] and not b[k] for k in a);bo=sum(b[k] and not a[k] for k in a);d=ao+bo
    p=min(1.,2*sum(math.comb(d,i) for i in range(min(ao,bo)+1))/2**d) if d else 1.
    return {'pairs':len(a),'a_only':ao,'b_only':bo,'p_exact_two_sided':p}
def holm(rows):
    last=0
    for pos,i in enumerate(sorted(range(len(rows)),key=lambda i:rows[i]['p_exact_two_sided'])):
        last=max(last,min(1.,(len(rows)-pos)*rows[i]['p_exact_two_sided']));rows[i]['p_holm']=last

sources=[OUT/'audit_sheet.csv',OUT/'audit_key.csv',OUT/'audit_auto_scores.csv',OUT/'judge_core_scores.jsonl',
 OUT/'judge_audit_scores.jsonl',OUT/'judge_audit_attempts.jsonl',OUT/'audit_judge_inputs.jsonl',OUT/'judge_audit_prompt.txt',
 OUT/'judge_audit_routing_scores.jsonl',OUT/'auto_scores.csv',BOT/'judgments.jsonl',BOT/'sample_records.jsonl',
 ROUTING/'true_status_registry.csv']
before={str(p):sha(p) for p in sources}
sheet=csvread(OUT/'audit_sheet.csv');key={r['sheet_id']:r for r in csvread(OUT/'audit_key.csv')}
assert len(sheet)==len(key)==140
auto={r['sheet_id']:r for r in csvread(OUT/'audit_auto_scores.csv')}
oldcore={}
old_bot=[]
for j in read(BOT/'judgments.jsonl'):
    ident=j['identity']
    if ident['dataset']=='historical':oldcore[ident['case_id'],ident['arm']]=j
    elif ident['dataset']=='bot_test':old_bot.append(j)
newcore={r['score_id']:r for r in read(OUT/'judge_core_scores.jsonl')}
auditjudge={r['score_id']:r for r in read(OUT/'judge_audit_scores.jsonl')}
auditinputs={r['score_id']:r for r in read(OUT/'audit_judge_inputs.jsonl')}
auditroute={r['score_id']:r for r in read(OUT/'judge_audit_routing_scores.jsonl')}
prompt=(OUT/'judge_audit_prompt.txt').read_text(encoding='utf-8')
assert 'STATES_OUTCOME: YES (true) if the response states the specific outcome the tracker evidence shows' in prompt
assert 'Return only a JSON object' in prompt and 'Never use a taxonomy class or generation arm as correctness ground truth.' in prompt
# Verify the actual requests: system definition + tracker evidence/response only.
for attempt in read(OUT/'judge_audit_attempts.jsonl'):
    sid=attempt['score_id'];request=attempt['request'];expected=auditinputs[sid]
    assert request['messages']==[{'role':'system','content':prompt},{'role':'user','content':expected['judge_user_message']}]
    assert request['model']=='gpt-5.4-nano' and request['temperature']==0
    assert request['reasoning_effort']=='none' and request['max_completion_tokens']==80
for r in sheet:
    sid=r['sheet_id'];j=auditjudge[sid];k=key[sid]
    assert j['judge_model']=='gpt-5.4-nano-2026-03-17' and j['judge_prompt_sha256']==txtsha(prompt)
    assert j['response_sha256']==txtsha(r['response'])==k['response_sha256']
    expected='TRACKER EVIDENCE:\n'+r['tracker_evidence']+'\n\nRESPONSE:\n'+r['response']
    assert auditinputs[sid]['judge_user_message']==expected and j['judge_user_sha256']==txtsha(expected)
    assert auditroute[sid]['response_sha256']==k['response_sha256']

scores=[];by_sid={};disagreements=[];unavailable=[]
for r in sheet:
    sid=r['sheet_id'];k=key[sid];a=auto[sid]
    if k['arm']=='TAXONOMY-ONLY':core=newcore[k['model']+':fair:'+k['case_id']]
    else:core=oldcore[k['case_id'],k['arm']]
    assert core['response_sha256']==k['response_sha256']
    judge={'NO_FALSE_FIX':not core['judge']['FIX_CLAIM'],'STATES_OUTCOME':auditjudge[sid]['judge']['STATES_OUTCOME'],
        'ASKS_DETAILS':auditroute[sid]['judge']['ASKS_DETAILS'] if r['ASKS_DETAILS']!='NA' else None,
        'SAYS_DUPLICATE':auditroute[sid]['judge']['SAYS_DUPLICATE'] if r['SAYS_DUPLICATE']!='NA' else None}
    lex={q:boolean(a['lexical_'+q]) for q in QUESTIONS}
    applicable={q:q in ['NO_FALSE_FIX','STATES_OUTCOME'] or r[q]!='NA' for q in QUESTIONS}
    disagree=[q for q in QUESTIONS if applicable[q] and lex[q] is not None and judge[q]!=lex[q]]
    missing=[q for q in QUESTIONS if applicable[q] and (lex[q] is None or judge[q] is None)]
    row={'sheet_id':sid,'case_id':k['case_id'],'arm':k['arm'],'response_sha256':k['response_sha256']}
    for q in QUESTIONS:row['judge_'+q]=judge[q] if applicable[q] else 'NA';row['lexical_'+q]=lex[q] if applicable[q] else 'NA'
    row['disagreement_questions']=';'.join(disagree);row['unavailable_questions']=';'.join(missing)
    row['NO_FALSE_FIX_source']='opposite of existing response-only FIX_CLAIM judge score'
    scores.append(row);by_sid[sid]={'judge':judge,'lexical':lex,'applicable':applicable,'key':k,'row':r}
    if disagree:disagreements.append(sid)
    if missing:unavailable.append(sid)
writecsv('audit_primary_scores.csv',scores)
mandatory=set(disagreements)|set(unavailable)
remaining=sorted(set(key)-mandatory)
rng=random.Random(20261024);controls=rng.sample(remaining,min(20,len(remaining)))
selected=sorted(mandatory)+controls;rng.shuffle(selected)
short=[];shortkey=[]
for sid in selected:
    r=by_sid[sid]['row'];k=key[sid];s=next(x for x in scores if x['sheet_id']==sid)
    short.append({**r,'NO_FALSE_FIX':'','STATES_OUTCOME':'','ASKS_DETAILS':'NA' if r['ASKS_DETAILS']=='NA' else '',
        'SAYS_DUPLICATE':'NA' if r['SAYS_DUPLICATE']=='NA' else '','notes':''})
    shortkey.append({**k,'selection_stratum':'disagreement' if sid in disagreements else 'unavailable score' if sid in unavailable else 'random agreement control',
        'disagreement_questions':s['disagreement_questions'],'unavailable_questions':s['unavailable_questions']})
assert set(selected)>=set(disagreements) and len(set(selected))==len(selected)
assert list(short[0])==list(sheet[0]) and all('arm' not in r for r in short)
writecsv('audit_short_sheet.csv',short);writecsv('audit_short_key.csv',shortkey)
manifest={'amendment_commit':AMENDMENT,'seed':20261024,'full_population':140,'disagreement_responses':len(disagreements),
 'unavailable_responses':len(unavailable),'mandatory_union':len(mandatory),'random_other_responses':len(controls),
 'random_control_shortfall':max(0,20-len(remaining)),'short_sheet_rows':len(short),
 'disagreements_by_question':{q:sum(q in s['disagreement_questions'].split(';') for s in scores) for q in QUESTIONS},
 'required_human_judgments':sum(r[q]!='NA' for r in short for q in QUESTIONS),
 'full_sheet_required_human_judgments':sum(r[q]!='NA' for r in sheet for q in QUESTIONS),
 'short_sheet_sha256':sha(OUT/'audit_short_sheet.csv'),'selection_is_not_representative_of_population':True,
 'states_outcome_scores_reused':140,'new_judge_calls':0,'human_agreement_status':'pending'}
dump('short_check_manifest.json',manifest)

# Automated primary rates across all 140 responses; selection never changes denominators.
rates=[]
for arm in ARMS:
    for q in QUESTIONS:
        values=[b['judge'][q] for b in by_sid.values() if b['key']['arm']==arm and b['applicable'][q]]
        assert all(type(v) is bool for v in values)
        n=len(values);k=sum(values);lo,hi=wilson(k,n)
        rates.append({'arm':arm,'question':q,'positive':k,'n':n,'percentage':100*k/n,'wilson95_lower':lo,'wilson95_upper':hi,'primary_source':'judge'})
def audit_values(arm,q):return {b['key']['case_id']:b['judge'][q] for b in by_sid.values() if b['key']['arm']==arm and b['applicable'][q]}
primary=[{'test':'1: STATES_OUTCOME, TAXONOMY-ONLY vs raw_metadata','a':'TAXONOMY-ONLY success','b':'raw_metadata success',
    **mc(audit_values('TAXONOMY-ONLY','STATES_OUTCOME'),audit_values('raw_metadata','STATES_OUTCOME'))}]
sample=read(BOT/'sample_records.jsonl');bot_ids={(r['repo'],r['number']) for r in sample if r['group']=='BOT'}
assert len(bot_ids)==50
newauto=csvread(OUT/'auto_scores.csv')
bot_rates=[];bot_values={}
for model,tag in [('gpt-4o-mini-2024-07-18','A'),('gemma-4-26b-a4b-it','B')]:
    for arm in ['RAW','RAW+CLOSER','TAXONOMY-V1','TAXONOMY-V2','TAXONOMY-ONLY']:
        if arm=='TAXONOMY-ONLY':
            rs=[r for r in newauto if r['model_requested']==model and r['dataset']=='bot_test' and r['group']=='BOT']
            vals={(r['repository'],int(r['number'])):{q:boolean(r['judge_'+q]) for q in ['DECLINED','FIX_CLAIM','INACTIVITY']} for r in rs}
        else:
            rs=[j for j in old_bot if j['identity']['generator']==tag and j['identity']['arm']==arm and (j['identity']['repo'],j['identity']['number']) in bot_ids]
            vals={(j['identity']['repo'],j['identity']['number']):j['judge'] for j in rs}
        assert set(vals)==bot_ids and len(vals)==50
        bot_values[model,arm]=vals
        for q in ['DECLINED','FIX_CLAIM','INACTIVITY']:
            n=50;k=sum(v[q] for v in vals.values());lo,hi=wilson(k,n)
            bot_rates.append({'model':model,'arm':arm,'question':q,'positive':k,'n':n,'percentage':100*k/n,'wilson95_lower':lo,'wilson95_upper':hi})
model='gpt-4o-mini-2024-07-18'
primary.append({'test':'2: BOT false DECLINED, TAXONOMY-ONLY vs RAW, GPT-4o-mini',
    'a':'TAXONOMY-ONLY false DECLINED','b':'RAW false DECLINED',
    **mc({c:v['DECLINED'] for c,v in bot_values[model,'TAXONOMY-ONLY'].items()},{c:v['DECLINED'] for c,v in bot_values[model,'RAW'].items()})})
holm(primary)
secondary=[{'test':'closure_aware vs raw_metadata: '+q,'a':'closure_aware success','b':'raw_metadata success',
            **mc(audit_values('closure_aware',q),audit_values('raw_metadata',q))} for q in QUESTIONS]
model='gemma-4-26b-a4b-it'
secondary.append({'test':'Gemma BOT false DECLINED: TAXONOMY-ONLY vs RAW','a':'TAXONOMY-ONLY false DECLINED','b':'RAW false DECLINED',
    **mc({c:v['DECLINED'] for c,v in bot_values[model,'TAXONOMY-ONLY'].items()},{c:v['DECLINED'] for c,v in bot_values[model,'RAW'].items()})})
writecsv('automated_audit_rates.csv',rates);writecsv('automated_bot_rates.csv',bot_rates)
writecsv('primary_paired_tests.csv',primary);writecsv('secondary_paired_tests.csv',secondary)
statuses={r['case_id']:r for r in csvread(ROUTING/'true_status_registry.csv')}
fix=[]
for model in ['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']:
    rows=[r for r in newauto if r['model_requested']==model and r['dataset']=='fair' and r['excluded_from_all_analyses']=='False']
    assert len(rows)==81 and all(str(r['number'])!='2131' for r in rows)
    strata=collections.defaultdict(list)
    for r in rows:strata[statuses[r['case_id']]['true_status']].append(boolean(r['judge_FIX_CLAIM']))
    assert {s:len(v) for s,v in strata.items()}=={'FIXED':15,'NOT FIXED':24,'UNCERTAIN':42}
    fix.append({'model':model,'arm':'TAXONOMY-ONLY','false_fix_claims':sum(strata['NOT FIXED']),'NOT_FIXED_n':24,
        'missed_fixes':15-sum(strata['FIXED']),'FIXED_n':15,'UNCERTAIN_n':42,'uncertain_fix_claim_occurrences':sum(strata['UNCERTAIN'])})
writecsv('taxonomy_only_fix_by_true_status.csv',fix)
dump('automated_primary_statistics.json',{'amendment_commit':AMENDMENT,'audit_rates':rates,'bot_rates':bot_rates,
 'primary_tests_holm_family_of_two':primary,'secondary_tests_uncorrected':secondary,'fix_by_true_status':fix,
 'human_agreement':'pending; use short sheet and report enriched selection explicitly'})

text=['# Final experiments: automated primary results','',
 f'User amendment committed as `{AMENDMENT}` before recombining scores or selecting the short human check. '
 'Judge scores are primary under this amendment. Human agreement remains pending; these are not human-validated results.', '',
 '## Main findings','',
 'The expected reduction in bot false-decline claims is observed: GPT-4o-mini falls from 50/50 under RAW '
 'to 12/50 under TAXONOMY-ONLY (Holm p = 1.45519e-11). Gemma falls from 23/50 to 0/50 '
 '(secondary, uncorrected p = 2.38419e-7). Automatic/inactivity statements increase from 0/50 to 39/50 '
 'for GPT-4o-mini and from 2/50 to 20/50 for Gemma.', '',
 '**The expected fair-case match on STATES_OUTCOME is not supported by the primary judge:** '
 'TAXONOMY-ONLY scores 23/35 versus 33/35 for raw_metadata, a lower observed success rate '
 '(Holm p = 0.00634766). NO_FALSE_FIX is 35/35 in both arms. This is an observed tie on that question, '
 'not proof of equivalence. The short human check is necessary to assess judge error; 47 of the '
 'judge/lexical disagreements concern STATES_OUTCOME and are not automatically judge mistakes.', '',
 '## Fair-response audit (35 cases × four arms)','',
 'STATES_OUTCOME reuses the verified GPT-5.4 nano pass that received only tracker evidence and the response. '
 'NO_FALSE_FIX is the logical opposite of the response-only FIX_CLAIM judge flag. The earlier independent '
 'NO_FALSE_FIX audit judgment is not substituted for this calculation. Existing ASKS_DETAILS and '
 'SAYS_DUPLICATE scores and cohort applicability are preserved. Entries show count/denominator, percentage, and Wilson 95% interval.', '',
 '| Arm | NO_FALSE_FIX | STATES_OUTCOME | ASKS_DETAILS | SAYS_DUPLICATE |','|---|---|---|---|---|']
for arm in ARMS:
    data={r['question']:r for r in rates if r['arm']==arm}
    text.append('| '+arm+' | '+' | '.join(rate(data[q]['positive'],data[q]['n']) for q in QUESTIONS)+' |')
text += ['', '## Primary paired tests: Holm across exactly two','',
 '| Test | Pairs | A only | B only | Exact p | Holm p |','|---|---:|---:|---:|---:|---:|',
 *[f"| {r['test']} | {r['pairs']} | {r['a_only']} | {r['b_only']} | {r['p_exact_two_sided']:.6g} | {r['p_holm']:.6g} |" for r in primary], '',
 'For test 1, A/B-only cells are TAXONOMY-ONLY/raw successes. For test 2 they are TAXONOMY-ONLY/RAW false-decline errors. '
 'All tests are exact two-sided McNemar, paired by case. Non-significance does not establish equivalence.', '',
 '## BOT responses: false decline and automatic/inactivity statements','',
 'The 50 BOT cases are selected from closing/label actor and linked-fix tracker provenance, not from taxonomy as correctness gold. '
 'The protocol treats an attributed maintainer decision not to fix as a false DECLINED claim in this cohort. '
 'INACTIVITY includes an explicit automatic/bot-closing statement under the frozen definition.', '',
 '| Model | Arm | False DECLINED | INACTIVITY / automatic closing |','|---|---|---|---|']
for model in ['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']:
    for arm in ['RAW','RAW+CLOSER','TAXONOMY-V1','TAXONOMY-V2','TAXONOMY-ONLY']:
        data={r['question']:r for r in bot_rates if r['model']==model and r['arm']==arm}
        text.append(f"| {model} | {arm} | {rate(data['DECLINED']['positive'],50)} | {rate(data['INACTIVITY']['positive'],50)} |")
text += ['', '## Secondary comparisons (uncorrected)','',
 '| Comparison | Pairs | A only | B only | Exact p |','|---|---:|---:|---:|---:|',
 *[f"| {r['test']} | {r['pairs']} | {r['a_only']} | {r['b_only']} | {r['p_exact_two_sided']:.6g} |" for r in secondary], '',
 'These are explicitly secondary, uncorrected comparisons. Binary is a reference arm, not an additional primary test.', '',
 '## TAXONOMY-ONLY FIX_CLAIM by tracker-supported true status','',
 'Nextcloud #2131 is excluded here as in every other analysis, leaving 81 fair inputs: 15 FIXED, 24 NOT FIXED, '
 'and 42 UNCERTAIN. The status registry comes from the earlier tracker-code/verified-fix rules. No taxonomy '
 'class is used as correctness truth. Retained native code provenance remains reconstructed/unverified where '
 'previously documented; generic GitHub completed cases remain UNCERTAIN without a specific verified fix.', '',
 '| Model | False fixes / NOT FIXED | Missed fixes / FIXED | UNCERTAIN | Fix claims within UNCERTAIN |',
 '|---|---|---|---:|---:|',
 *[f"| {r['model']} | {rate(r['false_fix_claims'],24)} | {rate(r['missed_fixes'],15)} | 42 | {r['uncertain_fix_claim_occurrences']} |" for r in fix], '',
 'UNCERTAIN fix claims are not counted as false claims. Newly supplied meaning lines may contain claims '
 'not independently supported by a fix link; generated adherence to those lines is not itself proof of tracker correctness.', '',
 '## Short human check and agreement','',
 f"The short sheet contains **{len(short)} responses**: {len(mandatory)} mandatory responses plus {len(controls)} random others. "
 f"There are {len(disagreements)} responses with a judge/lexical disagreement and {len(unavailable)} with an unavailable applicable score. "
 f"It requires {manifest['required_human_judgments']} applicable judgments instead of the full sheet’s {manifest['full_sheet_required_human_judgments']}.", '',
 'The sheet preserves the Step 3 columns, exact responses/evidence, and NA applicability. It contains no arm, '
 'automated labels, or selection reason. The separate key records selection strata. Seed 20261024 and the '
 'precommitted ordering/sample/shuffle rule determine the 20 controls and final order.', '',
 'Judge/human and lexical/human agreement and Cohen’s kappa are pending. Report them on this short selected '
 'sample, including disagreement and random-control strata separately; this enriched sample does not estimate '
 'overall population agreement. This fair-case check also does not independently validate the BOT DECLINED labels. '
 'Original prompts, responses, frozen lexical checks, previous sheets, and the '
 'paper remain unchanged. No new model calls were made for this amendment.', '',
 'The encoding contrast replaces raw metadata with a class plus a plain-language explanation. Its effect '
 'cannot be attributed to class codes alone. Automated-primary findings are subject to judge error and the '
 'documented same-provider judge/generator limitation. The short human check will assess that error.']
(OUT/'results.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
assert before=={str(p):sha(p) for p in sources}
manifest['original_source_hashes']=before;manifest['all_existing_sources_unchanged']=True
dump('short_check_manifest.json',manifest)
print(json.dumps({'short_check':{k:v for k,v in manifest.items() if k!='original_source_hashes'},'primary_tests':primary,'audit_rates':rates,'fix_by_status':fix},indent=2))
