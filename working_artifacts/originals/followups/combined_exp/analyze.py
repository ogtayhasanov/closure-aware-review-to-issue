"""Join frozen scores, validate coverage, and analyze the preregistered combined arm."""
import collections,csv,hashlib,importlib.util,json,math,random,sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;FINAL=ROOT.parent/'final_exp';BOT=ROOT.parent/'bot_test'
MODELS=['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']
ARMS=['RAW','TAXONOMY-ONLY','RAW+MEANING','SWITCH']
CORE=['DECLINED','FIX_CLAIM','INACTIVITY']
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tsha(s):return hashlib.sha256(s.encode()).hexdigest()
def dump(name,obj):(ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def writecsv(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bl=module('frozen_bot_lex',FINAL/'scripts/bot_lexical.py');rl=module('frozen_routing_lex',FINAL/'scripts/routing_lexical.py')
settings=json.loads((ROOT/'generation_settings.json').read_text(encoding='utf-8'))
manifest=json.loads((ROOT/'preparation_manifest.json').read_text(encoding='utf-8'))
for path,digest in manifest['source_sha256'].items():assert sha(Path(path))==digest,'Original input changed: '+path
for name,digest in manifest['outputs_sha256'].items():assert sha(ROOT/name)==digest,name
inputs={r['input_id']:r for r in read(ROOT/'inputs_raw_meaning.jsonl')}
key=csvread(FINAL/'audit_key.csv');sheets={r['sheet_id']:r for r in csvread(FINAL/'audit_sheet.csv')}
auditmeta={r['case_id']:r for r in key};assert len(auditmeta)==35
evidence={r['case_id']:sheets[r['sheet_id']]['tracker_evidence'] for r in key}
urls={r['case_id']:sheets[r['sheet_id']]['issue_url'] for r in key}
judgecore={r['score_id']:r for r in read(ROOT/'judge_core_scores.jsonl')}
judgeroute={r['score_id']:r for r in read(ROOT/'judge_routing_scores.jsonl')}
judgeaudit={r['score_id']:r for r in read(ROOT/'judge_audit_scores.jsonl')}
referenceroute={r['score_id']:r for r in read(ROOT/'judge_reference_routing_scores.jsonl')}
assert len(judgecore)==len(judgeroute)==324
assert len(judgeaudit)==140
referencejobs=read(ROOT/'reference_routing_inputs.jsonl');assert len(referenceroute)==len(referencejobs)
# Verify actual evidence-only audit requests and unchanged judge settings.
auditjobs={r['score_id']:r for r in read(ROOT/'audit_judge_inputs.jsonl')}
for attempt in read(ROOT/'judge_audit_attempts.jsonl'):
    job=auditjobs[attempt['score_id']];p=attempt['request']
    assert p['messages']==[{'role':'system','content':(ROOT/'judge_audit_prompt.txt').read_text(encoding='utf-8')},{'role':'user','content':job['judge_user_message']}]
    assert job['judge_user_message'].startswith('TRACKER EVIDENCE:\n'+evidence[job['case_id']]+'\n\nRESPONSE:\n')
    assert p['temperature']==0 and p['reasoning_effort']=='none' and p['max_completion_tokens']==80
    assert p['model']==settings['judge']['model_requested']
for stage,data in [('core',judgecore),('routing',judgeroute),('audit',judgeaudit),('reference_routing',referenceroute)]:
    promptstage='routing' if stage=='reference_routing' else stage
    for s in data.values():
        assert s['judge_model'] in settings['judge']['model_ids_returned_in_reference_run']
        assert s['judge_prompt_sha256']==tsha((ROOT/f'judge_{promptstage}_prompt.txt').read_text(encoding='utf-8'))
combined=[]
for model in MODELS:
    rs=read(ROOT/f'responses_raw_meaning_{model}.jsonl');assert len(rs)==len({r['input_id'] for r in rs})==162
    for r in rs:
        sid=model+':'+r['input_id'];meta=inputs[r['input_id']];cfg=settings['generation']['A' if model==MODELS[0] else 'B']
        assert r['response'].strip() and r['finish_reason']=='stop'
        assert r['model_id'] in cfg['model_ids_returned_in_reference_run'] and r['settings']==cfg
        assert r['response_sha256']==tsha(r['response'])==judgecore[sid]['response_sha256']==judgeroute[sid]['response_sha256']
        assert r['messages_sha256']==meta['messages_sha256']
        if model==MODELS[0]:assert r['request_payload']['messages']==meta['messages']
        else:
            assert r['request_payload']['systemInstruction']['parts'][0]['text']==meta['messages'][0]['content']
            assert r['request_payload']['contents'][0]['parts'][0]['text']==meta['messages'][1]['content']
            assert r['usage'].get('reasoning_tokens',0)==0
        state=None
        if r['dataset']=='fair' and r['case_id'] in auditmeta:
            a=judgeaudit[sid];assert a['response_sha256']==r['response_sha256'];state=a['judge']['STATES_OUTCOME']
        combined.append({k:r[k] for k in ['input_id','dataset','case_id','repository','number','group','excluded_from_all_analyses','arm','response','response_sha256']}|{'model':model,'judge_core':judgecore[sid]['judge'],'judge_routing':judgeroute[sid]['judge'],'judge_STATES_OUTCOME':state,'selected_source_arm':''})
refs=read(ROOT/'reference_responses_and_scores.jsonl');assert len(refs)==648
for r in refs:
    sid=r['model']+':reference:'+r['input_id']
    if r['judge_routing'] is None and sid in referenceroute:
        s=referenceroute[sid];assert s['response_sha256']==r['response_sha256'];r['judge_routing']=s['judge']
    if r['model']==MODELS[1] and r['dataset']=='fair' and r['case_id'] in auditmeta:
        arm='raw_metadata' if r['arm']=='RAW' else r['arm']
        a=judgeaudit[r['model']+':reference:'+arm+':'+r['case_id']]
        assert a['response_sha256']==r['response_sha256'];r['judge_STATES_OUTCOME']=a['judge']['STATES_OUTCOME']
    r['selected_source_arm']=''
choices={r['input_id']:r for r in csvread(ROOT/'switch_provenance.csv')}
switch=[]
for r in refs:
    chosen='TAXONOMY-ONLY' if choices[r['input_id']]['switch']=='True' else 'RAW'
    if r['arm']==chosen:switch.append({**r,'arm':'SWITCH','selected_source_arm':r['arm']})
assert len(switch)==324 and all(r['judge_routing'] is not None for r in switch)
allrows=refs+combined+switch
assert len(allrows)==1296 and len({(r['model'],r['arm'],r['input_id']) for r in allrows})==1296
scores=[]
for r in allrows:
    b=bl.score(r['response']);rt=rl.score(r['response'],r['number']);route=r['judge_routing']
    row={k:r[k] for k in ['model','arm','input_id','dataset','case_id','repository','number','group','excluded_from_all_analyses','response_sha256','selected_source_arm']}
    for q in CORE:row['judge_'+q]=r['judge_core'][q];row['lexical_'+q]=b[q]
    row['judge_NO_FALSE_FIX']=not r['judge_core']['FIX_CLAIM'];row['lexical_NO_FALSE_FIX']=not b['FIX_CLAIM']
    row['judge_STATES_OUTCOME']=r['judge_STATES_OUTCOME'] if r['judge_STATES_OUTCOME'] is not None else 'NA'
    for q in ['ASKS_DETAILS','SAYS_DUPLICATE']:
        row['judge_'+q]=route[q] if route is not None else 'NA';row['lexical_'+q]=rt[q]
    scores.append(row)
writecsv('scores_all_arms.csv',scores)
assert sum(r['excluded_from_all_analyses'] for r in scores)==8
included=[r for r in scores if not r['excluded_from_all_analyses']]
def wilson(k,n):
    z=1.959963984540054;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0,c-h),min(1,c+h)
def vals(model,arm,cohort,q):
    rs=[r for r in included if r['model']==model and r['arm']==arm]
    if cohort in ['BOT','HUMAN']:rs=[r for r in rs if r['dataset']=='bot_test' and r['group']==cohort]
    elif cohort=='fair_all':rs=[r for r in rs if r['dataset']=='fair']
    elif cohort=='audit35':rs=[r for r in rs if r['dataset']=='fair' and r['case_id'] in auditmeta]
    elif cohort in ['NEEDS_INFO','REDIRECTED']:
        flag='ASKS_DETAILS_applicable' if cohort=='NEEDS_INFO' else 'SAYS_DUPLICATE_applicable'
        rs=[r for r in rs if r['dataset']=='fair' and r['case_id'] in auditmeta and auditmeta[r['case_id']][flag]=='True']
    else:raise ValueError(cohort)
    v={r['case_id']:r['judge_'+q] for r in rs}
    expected={'BOT':50,'HUMAN':30,'fair_all':81,'audit35':35,'NEEDS_INFO':16,'REDIRECTED':7}[cohort]
    assert len(rs)==len(v)==expected,(model,arm,cohort,q,len(rs))
    assert all(type(x) is bool for x in v.values()),(model,arm,cohort,q)
    return v
rates=[]
for model in MODELS:
    for arm in ARMS:
        for cohort,qs in [('BOT',CORE),('HUMAN',CORE),('fair_all',CORE+['NO_FALSE_FIX']),('audit35',['NO_FALSE_FIX','STATES_OUTCOME']),('NEEDS_INFO',['ASKS_DETAILS']),('REDIRECTED',['SAYS_DUPLICATE'])]:
            for q in qs:
                v=vals(model,arm,cohort,q);k=sum(v.values());n=len(v);lo,hi=wilson(k,n)
                rates.append({'model':model,'arm':arm,'cohort':cohort,'question':q,'positive':k,'n':n,'percentage':100*k/n,'wilson95_lower':lo,'wilson95_upper':hi})
writecsv('rates.csv',rates)
def mc(model,arm,base,cohort,q,label):
    a=vals(model,arm,cohort,q);b=vals(model,base,cohort,q);assert a.keys()==b.keys()
    ao=sum(a[c] and not b[c] for c in a);bo=sum(b[c] and not a[c] for c in a);d=ao+bo
    p=min(1.0,2*sum(math.comb(d,i) for i in range(min(ao,bo)+1))/2**d) if d else 1.0
    return {'test':label,'model':model,'arm_a':arm,'arm_b':base,'cohort':cohort,'question':q,'pairs':len(a),'a_positive':sum(a.values()),'b_positive':sum(b.values()),'a_only':ao,'b_only':bo,'p_exact_two_sided':p}
primary=[mc(MODELS[0],'RAW+MEANING','RAW','BOT','DECLINED','1: BOT false DECLINED'),mc(MODELS[0],'RAW+MEANING','RAW','audit35','STATES_OUTCOME','2: audit STATES_OUTCOME')]
last=0
for i,pos in enumerate(sorted(range(2),key=lambda i:primary[i]['p_exact_two_sided'])):
    last=max(last,min(1.0,(2-i)*primary[pos]['p_exact_two_sided']));primary[pos]['p_holm']=last
writecsv('primary_tests.csv',primary)
secondary=[]
for model in MODELS:
    for base in (['TAXONOMY-ONLY'] if model==MODELS[0] else ['RAW','TAXONOMY-ONLY']):
        for cohort,q in [('BOT','DECLINED'),('audit35','STATES_OUTCOME')]:
            secondary.append(mc(model,'RAW+MEANING',base,cohort,q,f'{model}: RAW+MEANING vs {base}: {q}'))
writecsv('secondary_tests.csv',secondary)
intervals=[]
for model in MODELS:
    a=vals(model,'RAW+MEANING','audit35','STATES_OUTCOME');b=vals(model,'RAW','audit35','STATES_OUTCOME')
    differences=np.array([int(a[c])-int(b[c]) for c in sorted(a)])
    # Whole-case paired bootstrap represented by multinomial frequencies of {-1,0,+1}.
    probs=np.array([(differences==v).sum() for v in [-1,0,1]])/35
    draws=np.random.default_rng(20261024).multinomial(35,probs,size=200000)
    boot=(draws[:,2]-draws[:,0])/35
    lo,hi=np.quantile(boot,[.025,.975])
    intervals.append({'model':model,'contrast':'RAW+MEANING minus RAW','question':'STATES_OUTCOME','n':35,'difference':float(differences.mean()),'paired_bootstrap95_lower':float(lo),'paired_bootstrap95_upper':float(hi),'replicates':200000,'seed':20261024})
writecsv('paired_difference_intervals.csv',intervals)
# Make only the conditional test-2 blind sheet, with neutral IDs after shuffling.
av=vals(MODELS[0],'RAW+MEANING','audit35','STATES_OUTCOME');bv=vals(MODELS[0],'RAW','audit35','STATES_OUTCOME')
discordant=sorted(c for c in av if av[c]!=bv[c]);blind=[];blindkey=[]
lookup={(r['model'],r['arm'],r['case_id']):r for r in allrows if r['dataset']=='fair'}
jobs=[lookup[MODELS[0],arm,c] for c in discordant for arm in ['RAW','RAW+MEANING']]
random.Random(20261024).shuffle(jobs)
for i,r in enumerate(jobs,1):
    sid=f'M{i:03d}'
    blind.append({'sheet_id':sid,'issue_url':urls[r['case_id']],'tracker_evidence':evidence[r['case_id']],'response':r['response'],'STATES_OUTCOME':''})
    blindkey.append({'sheet_id':sid,'case_id':r['case_id'],'arm':r['arm'],'model':r['model'],'response_sha256':r['response_sha256'],'tracker_evidence_sha256':tsha(evidence[r['case_id']])})
if blind:
    assert not (ROOT/'audit_test2_sheet.csv').exists(),'Preserve any human labels on rerun'
    writecsv('audit_test2_sheet.csv',blind);writecsv('audit_test2_key.csv',blindkey)
dump('blind_sheet_manifest.json',{'discordant_cases':len(discordant),'response_rows':len(blind),'required_answers':len(blind),'questions':['STATES_OUTCOME'],'arm_hidden':True,'seed':20261024,'human_labels':'pending' if blind else 'not needed; no discordant pairs'})
def rate(model,arm,cohort,q):
    r=next(r for r in rates if (r['model'],r['arm'],r['cohort'],r['question'])==(model,arm,cohort,q))
    return f"{r['positive']}/{r['n']} ({r['percentage']:.1f}%; {100*r['wilson95_lower']:.1f}–{100*r['wilson95_upper']:.1f})"
sm=json.loads((ROOT/'switch_manifest.json').read_text(encoding='utf-8'))
report=['# RAW+MEANING and provenance-switch results','',
    'Instructions were committed before construction as `48d8b42`; interval and score-reuse methods were recorded as `1fd3aa8`. All 162 input checks passed. Both generators returned all 162 nonblank, stop-finished responses with the registered model IDs and exact settings. The shared system prompt is unchanged. Original prompts, responses, scores and the paper are unchanged.','',
    '## Primary tests','',
    '| Test | A positive | RAW positive | A only | RAW only | Exact McNemar p | Holm p |',
    '|---|---:|---:|---:|---:|---:|---:|']
for r in primary:report.append(f"| {r['test']} | {r['a_positive']}/{r['pairs']} | {r['b_positive']}/{r['pairs']} | {r['a_only']} | {r['b_only']} | {r['p_exact_two_sided']:.8g} | {r['p_holm']:.8g} |")
report+=['','A is RAW+MEANING. DECLINED is an erroneous attributed maintainer rejection in the provenance-defined BOT cohort, so lower is better. STATES_OUTCOME is evidence-supported correctness, so higher is better. Holm covers exactly these two tests.','']
for ci in intervals:
    report.append(f"{ci['model']}: STATES_OUTCOME difference RAW+MEANING minus RAW = {100*ci['difference']:+.2f} percentage points; paired-bootstrap 95% CI [{100*ci['paired_bootstrap95_lower']:+.2f}, {100*ci['paired_bootstrap95_upper']:+.2f}] points (35 pairs, 200,000 replicates, seed 20261024).")
report+=['','A non-significant test does not establish equivalence. The bootstrap interval resamples whole cases and is discrete at this sample size.','', '## BOT cohort: 50 issues per model','', '| Model | Arm | False DECLINED | INACTIVITY / automatic closure |', '|---|---|---|---|']
for model in MODELS:
    for arm in ARMS:report.append(f"| {model} | {arm} | {rate(model,arm,'BOT','DECLINED')} | {rate(model,arm,'BOT','INACTIVITY')} |")
report+=['','Rate intervals are Wilson 95%. These BOT correctness labels use tracker closing-actor/linked-fix provenance, not received taxonomy classes. INACTIVITY uses the frozen definition that also includes automatic closure.','', '## Fair audit: 35 cases per model','', '| Model | Arm | STATES_OUTCOME | NO_FALSE_FIX | ASKS_DETAILS (16) | SAYS_DUPLICATE (7) |','|---|---|---|---|---|---|']
for model in MODELS:
    for arm in ARMS:report.append(f"| {model} | {arm} | {rate(model,arm,'audit35','STATES_OUTCOME')} | {rate(model,arm,'audit35','NO_FALSE_FIX')} | {rate(model,arm,'NEEDS_INFO','ASKS_DETAILS')} | {rate(model,arm,'REDIRECTED','SAYS_DUPLICATE')} |")
report+=['','STATES_OUTCOME uses only the unchanged tracker evidence and response; no arm or taxonomy class is given to the judge. NO_FALSE_FIX is the opposite of FIX_CLAIM. Frozen lexical checks are secondary and recorded in `scores_all_arms.csv`; STATES_OUTCOME has no lexical score. Cohort applicability is retained from the earlier audit, without treating it as correctness truth.','', '## Secondary tests, uncorrected','', '| Model | Contrast | Question | Pairs | A only | B only | Exact p |','|---|---|---|---:|---:|---:|---:|']
for r in secondary:report.append(f"| {r['model']} | {r['arm_a']} vs {r['arm_b']} | {r['question']} | {r['pairs']} | {r['a_only']} | {r['b_only']} | {r['p_exact_two_sided']:.8g} |")
report+=['', '## Switch provenance and coverage','',
    f"The rule switches {sm['bot_test_switched']}/80 bot-test inputs and {sm['fair_switched']}/82 fair inputs, identically for both generators. All switch outputs are existing responses; no switch generation was performed. GitHub API issue records and complete REST timelines were refreshed for all {sm['github_fair_inputs_refetched']} GitHub-hosted fair inputs. Other trackers ({sm['non_github_fair_inputs']}) retain RAW. The five switching fair inputs are Nextcloud #3376, #2555, #4054, #4660, and #6443. All have a final bot closure and no commit/PR references in the complete returned timeline.", '',
    'Nextcloud #5910 is currently open; its historical bot closure does not trigger the switch. The repeated retrieved issue #5454 occurs in four distinct fair inputs and #2152 in two; all distinct case IDs remain separate. Bot-test provenance is taken from sample.csv, with absence of linked closers verified against the matching sample_records.jsonl. The frozen extra bot list contains automated-signal. No received taxonomy class is consulted for switching.', '',
    'Nextcloud #2131 is retained in generation and all score ledgers, but explicitly excluded from every analysis because verified PR #4470 fixed it. This leaves 81 fair inputs and the unchanged 35-case audit. No other case or response is excluded. Rates for HUMAN bot-test cases (30), the full included fair set (81), and INACTIVITY in all cohorts are in rates.csv. Switch selections, reasons and API provenance are retained individually.', '',
    f"## Conditional blind human check\n\nTest 2 has {len(discordant)} discordant case pairs. Its blind sheet contains {len(blind)} shuffled responses and exactly {len(blind)} STATES_OUTCOME answers, with arms and automated answers hidden. The key is separate. Human labels are {'pending' if blind else 'not required'}. This selected sheet does not estimate population agreement.", '',
    'All required combined, switch and audit-comparator scores are complete. The comprehensive ledger retains 102 additional original RAW rows with routing judgments marked NA because those judgments were not needed for these comparisons or switch selections. Their core and lexical scores remain present. STATES_OUTCOME is NA outside the 35-case audit; it is never silently coded false.', '',
    '## Interpretation and limitations','',
    'The expected GPT bot improvement was not observed: 50/50 false DECLINED in both RAW+MEANING and RAW, with no automatic/inactivity statements. Gemma shows a different secondary result: 23/50 to 0/50 false DECLINED. The effect differs by generator. Fair-case RAW denotes the original raw_metadata arm. The switch scores 29/35 on STATES_OUTCOME for both models and therefore loses detail versus RAW; bot provenance alone does not ensure that a class/meaning-only response preserves a specific recorded closure reason.', '',
    'The combined contrast adds the plain-language class/meaning block while retaining raw fields; it cannot isolate class codes from explanations. The switch is a deterministic post-processing policy on existing responses and is reported descriptively. Automated judge results are primary under the existing amendment; earlier human labels concern a different selected comparison and are not transferred to new responses. The same-provider GPT judge/generator limitation remains. Agreement between judge and lexical checks is not correctness validation.', '']
(ROOT/'results.md').write_text('\n'.join(report),encoding='utf-8')
usage=[]
for stage in ['A','B','core','routing','audit','reference_routing']:
    p=ROOT/(f'generation_attempts_{stage}.jsonl' if stage in ['A','B'] else f'judge_{stage}_attempts.jsonl')
    attempts=read(p);totals=collections.Counter()
    for r in attempts:
        u=r.get('usage') or r.get('raw_response',{}).get('usage',{})
        for k in ['prompt_tokens','completion_tokens','total_tokens']:totals[k]+=u.get(k,0)
    usage.append({'stage':stage,'recorded_returned_attempts':len(attempts),'prompt_tokens':totals['prompt_tokens'],'completion_tokens':totals['completion_tokens'],'total_tokens':totals['total_tokens']})
writecsv('api_usage.csv',usage)
dump('completion_audit.json',{'generated_responses':324,'missing_generated_responses':0,'combined_core_scores':324,'combined_routing_scores':324,'audit_evidence_scores':140,'reference_routing_scores':len(referenceroute),'score_ledger_rows':len(scores),'analysis_exclusion_rows':8,'excluded_case':'nextcloud/android#2131','all_source_hashes_unchanged':True,'missing_applicable_analysis_scores':0,'states_outcome_lexical_used':False,'primary_tests':primary,'intervals':intervals,'blind_response_rows':len(blind),'failures_and_retries_recorded':len(read(ROOT/'request_failures.jsonl'))})
print(json.dumps({'primary':primary,'intervals':intervals,'blind_rows':len(blind),'generation_complete':324},indent=2))
