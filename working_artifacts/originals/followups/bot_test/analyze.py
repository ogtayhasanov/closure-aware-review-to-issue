"""Analyze complete paired outputs. Never substitute lexical labels for missing judgments."""
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from run_experiment import MODELS, RUN, SETTINGS, actual_settings, response_jobs, read, JUDGE_INSTRUCTIONS

QUESTIONS=('DECLINED','FIX_CLAIM','INACTIVITY')
ARMS=('RAW','RAW+CLOSER','TAXONOMY-V1','TAXONOMY-V2')

def wilson(k,n):
    if not n: return None,None
    z=1.959963984540054
    p=k/n; divisor=1+z*z/n
    center=(p+z*z/(2*n))/divisor
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/divisor
    return max(0,center-half),min(1,center+half)

def rate(values):
    n=len(values); k=sum(values); lo,hi=wilson(k,n)
    return f'{k}/{n} ({100*k/n:.1f}%; {100*lo:.1f}–{100*hi:.1f})' if n else 'NA'

def mcnemar(a,b):
    assert set(a)==set(b)
    a_only=sum(a[k] and not b[k] for k in a)
    b_only=sum(b[k] and not a[k] for k in a)
    n=a_only+b_only
    p=min(1.,2*sum(math.comb(n,i) for i in range(min(a_only,b_only)+1))/2**n) if n else 1.
    return {'pairs':len(a),'a_only':a_only,'b_only':b_only,'p_exact_two_sided':p}

def holm(tests):
    previous=0.
    for pos,index in enumerate(sorted(range(len(tests)),key=lambda i:tests[i]['p_exact_two_sided'])):
        previous=max(previous,min(1.,(len(tests)-pos)*tests[index]['p_exact_two_sided']))
        tests[index]['p_holm']=previous

def kappa(pairs):
    n=len(pairs)
    if not n: return {'n':0,'kappa':None}
    observed=sum(a==b for a,b in pairs)/n
    pa=sum(a for a,b in pairs)/n; pb=sum(b for a,b in pairs)/n
    expected=pa*pb+(1-pa)*(1-pb)
    return {'n':n,'agreement':observed,'kappa':(observed-expected)/(1-expected) if expected<1 else None}

def csv_write(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    sample=read(OUT/'sample_records.jsonl')
    groups={(r['repo'],r['number']):r['group'] for r in sample}
    jobs=response_jobs()
    assert len(jobs)==1132, f'Expected 1132 response records, got {len(jobs)}; no analysis of incomplete data'
    expected={j['response_key']:j for j in jobs}
    judgments=read(OUT/'judgments.jsonl')
    actual={j['response_key']:j for j in judgments}
    assert len(judgments)==len(actual)==1132 and set(actual)==set(expected), 'Missing/duplicate/unexpected judgments'
    for response_key,j in actual.items():
        assert j['response_sha256']==hashlib.sha256(expected[response_key]['response'].encode()).hexdigest()
        assert j['model_requested']==MODELS['judge']
        assert j['judge_prompt_sha256']==hashlib.sha256(JUDGE_INSTRUCTIONS.encode()).hexdigest()
        assert set(j['judge'])==set(QUESTIONS)
    bot=[j for j in judgments if j['identity']['dataset']=='bot_test']
    assert len(bot)==640
    partitions=defaultdict(list)
    for j in bot:
        ident=j['identity']
        group=groups[ident['repo'],ident['number']]
        partitions[ident['generator'],group,ident['arm']].append(j)
    text=['# Bot-closure experiment results', '',
          '**Automated results, provisional pending the blind human audit.**', '',
          '## Design and completeness', '',
          '- Sample: 50 BOT (25 Signal, 25 Jitsi) and all 30 eligible HUMAN issues (3 Signal, 27 Jitsi).',
          '- Bot experiment: 320 complete responses per generator, 640 total. Main Gemma rerun: 246 responses. Historical responses scored without regeneration: 246.',
          '- All 1,132 responses have blinded judge and frozen lexical scores. No missing response was replaced with a lexical score.',
          '- Model A: gpt-4o-mini-2024-07-18. Model B: Gemma 4 26B A4B Instruct (approved amendment). Judge: GPT-5.4 nano, reasoning off, temperature 0 (approved amendment).',
          '- Same system/user text across providers. Temperature 0 and output limit 220 for generation. Google native transport disables thinking; API seed omitted after compatibility endpoint rejection. Original main generation file remains unchanged.',
          '- The OpenAI judge is not provider-independent of Model A. Interpret model comparisons with that limitation and the pending human audit.', '',
          '## Per-model, group and arm rates', '',
          'Cells show count / denominator (percentage; Wilson 95% confidence interval). FIX_CLAIM is a false claim for both sampled groups under the preregistered ground truth. DECLINED is erroneous for BOT and expected for HUMAN.', '',
          '| Model | Group | Arm | DECLINED | FIX_CLAIM | INACTIVITY |',
          '|---|---|---|---|---|---|']
    rates=[]
    for tag in ('A','B'):
        for group in ('BOT','HUMAN'):
            for arm in ARMS:
                rows=partitions[tag,group,arm]
                assert len(rows)==(50 if group=='BOT' else 30)
                text.append('| '+' | '.join([tag,group,arm]+[rate([r['judge'][q] for r in rows]) for q in QUESTIONS])+' |')
                for q in QUESTIONS:
                    vals=[r['judge'][q] for r in rows]; lo,hi=wilson(sum(vals),len(vals))
                    rates.append({'model':tag,'group':group,'arm':arm,'question':q,'count':sum(vals),'n':len(vals),
                                  'proportion':sum(vals)/len(vals),'wilson_lower':lo,'wilson_upper':hi})
    tests=[]
    text+=['','## Paired BOT false-DECLINED comparisons','','Two-sided exact McNemar tests. Holm correction is applied separately to each model’s three planned comparisons. Model A is primary; Model B is secondary.', '',
           '| Model | Comparison | Pairs | V2-only errors | Comparator-only errors | Exact p | Holm p |',
           '|---|---|---:|---:|---:|---:|---:|']
    for tag in ('A','B'):
        v2={(r['identity']['repo'],r['identity']['number']):r['judge']['DECLINED'] for r in partitions[tag,'BOT','TAXONOMY-V2']}
        local=[]
        for comparator in ('RAW','RAW+CLOSER','TAXONOMY-V1'):
            comp={(r['identity']['repo'],r['identity']['number']):r['judge']['DECLINED'] for r in partitions[tag,'BOT',comparator]}
            local.append({'model':tag,'comparison':'TAXONOMY-V2 vs '+comparator,**mcnemar(v2,comp)})
        holm(local); tests.extend(local)
        for t in local:
            text.append(f"| {tag} | {t['comparison']} | {t['pairs']} | {t['a_only']} | {t['b_only']} | {t['p_exact_two_sided']:.6g} | {t['p_holm']:.6g} |")
    text+=['','## Judge versus lexical agreement','','Cohen’s kappa is descriptive; lexical matching is not ground truth. Undefined kappa indicates no variation in the marginal labels.', '',
           '| Scope | Question | N | Agreement | Kappa |','|---|---|---:|---:|---:|']
    agreement=[]
    for scope,rows in [('bot experiment',bot),('all scored responses',judgments)]:
        for q in QUESTIONS:
            stats=kappa([(r['judge'][q],r['lexical'][q]) for r in rows]); agreement.append({'scope':scope,'question':q,**stats})
            kap=f"{stats['kappa']:.4f}" if stats['kappa'] is not None else 'undefined'
            text.append(f"| {scope} | {q} | {stats['n']} | {100*stats['agreement']:.1f}% | {kap} |")
    text+=['','## FIX_CLAIM on historical and main rerun responses','','These populations include genuinely resolved issues, so a FIX_CLAIM occurrence here is not automatically an error.', '',
           '| Dataset | Arm | FIX_CLAIM (Wilson 95% CI) |','|---|---|---|']
    for dataset in ('historical','main_gemma'):
        rows=[j for j in judgments if j['identity']['dataset']==dataset]
        assert len(rows)==246
        for arm in ('binary_state','raw_metadata','closure_aware'):
            text.append(f"| {dataset} | {arm} | {rate([j['judge']['FIX_CLAIM'] for j in rows if j['identity']['arm']==arm])} |")
    main=[j for j in judgments if j['identity']['dataset']=='main_gemma']
    mapped={arm:{j['identity']['case_id']:j['judge']['FIX_CLAIM'] for j in main if j['identity']['arm']==arm} for arm in ('raw_metadata','closure_aware')}
    main_test=mcnemar(mapped['closure_aware'],mapped['raw_metadata'])
    text+=['',f"Main Gemma rerun, FIX_CLAIM taxonomy vs raw: {main_test['pairs']} pairs, taxonomy-only {main_test['a_only']}, raw-only {main_test['b_only']}, exact McNemar p = {main_test['p_exact_two_sided']:.6g}.", '',
           '**Unavailable endpoint:** the original “specific closure reason conveyed” checker was not found. No replacement endpoint or associated test was invented. That part of Step 6 remains pending the original code or an approved definition.', '']
    # Freeze blind selection with disagreements across any question plus ceil(25% of the rest).
    ordered=sorted(jobs,key=lambda j:j['response_key'])
    disagreements=[j for j in ordered if any(actual[j['response_key']]['judge'][q]!=actual[j['response_key']]['lexical'][q] for q in QUESTIONS)]
    rest=[j for j in ordered if j not in disagreements]
    rng=random.Random(20261024)
    audit=disagreements+rng.sample(rest,math.ceil(len(rest)*0.25))
    rng.shuffle(audit)
    blind=[]; blindkey=[]
    disagreement_ids={j['response_key'] for j in disagreements}
    for i,j in enumerate(audit,1):
        bid=f'B{i:04d}'
        blind.append({'blind_id':bid,'response':j['response'],'DECLINED':'','FIX_CLAIM':'','INACTIVITY':'','notes':''})
        blindkey.append({'blind_id':bid,'response_key':j['response_key'],**j['identity'],
                         'inclusion':'disagreement' if j['response_key'] in disagreement_ids else 'random_25_percent'})
    csv_write(OUT/'blind_sheet.csv',blind,['blind_id','response',*QUESTIONS,'notes'])
    fields=list(dict.fromkeys(k for r in blindkey for k in r))
    csv_write(OUT/'blind_key.csv',blindkey,fields)
    text+=['## Blind human audit','',f'blind_sheet.csv contains {len(audit)} shuffled responses: all {len(disagreements)} judge/lexical disagreements plus {len(audit)-len(disagreements)} randomly selected responses from the remaining {len(rest)} (ceil of 25%; seed 20261024).',
           'The sheet has no arm, group, issue identifier, model identifier, judge labels, or lexical labels. Responses can themselves mention issue information, which has not been redacted. Keep blind_key.csv closed until annotations are complete.', '',
           '## Exclusions, failures, and completeness','',
           'Sample exclusions are fully listed in exclusions.csv. Generation failures and non-stop attempts are retained in request_failures.jsonl and attempt ledgers; none is silently dropped. See completion_audit.json for unresolved keys and main-run finish reasons.', '']
    failures=read(OUT/'request_failures.jsonl')
    text.append(f'Logged request/validation failures: {len(failures)}. Earlier compatibility and truncation failures were retried under the documented provider adapter; complete final responses are analyzed.')
    # Only draw comparative conclusions from the primary endpoint, not preregistered expectations.
    a_bot={arm:sum(r['judge']['DECLINED'] for r in partitions['A','BOT',arm]) for arm in ARMS}
    text+=['','## Observed primary pattern','',
           'Model A BOT false-DECLINED counts: '+', '.join(f'{arm} {a_bot[arm]}/50' for arm in ARMS)+'.',
           'The automated primary result does not support the preregistered prediction that TAXONOMY-V2 would rarely make false-DECLINED claims. None of the three primary paired comparisons is significant after Holm correction.',
           'For Gemma, TAXONOMY-V2 reduces false-DECLINED claims from 50/50 under TAXONOMY-V1 to 21/50. Its comparisons with RAW (23/50) and RAW+CLOSER (24/50) are not statistically significant after correction. Nonsignificance does not establish equivalence.',
           'These automated results do not establish human-validated accuracy. The OpenAI judge/provider limitation and blind human audit remain material to interpretation.', '']
    (OUT/'results.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    csv_write(OUT/'rates.csv',rates,list(rates[0]))
    (OUT/'statistics.json').write_text(json.dumps({'paired_bot_tests':tests,'main_fix_claim_test':main_test,'agreement':agreement},indent=2),encoding='utf-8')
    print(json.dumps({'responses':len(jobs),'judgments':len(judgments),'blind_rows':len(audit),'disagreements':len(disagreements),'primary_bot_declined':a_bot}))

if __name__=='__main__': main()
