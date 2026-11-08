"""Audit all keys and finish reasons, then write a truthful run manifest."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from run_experiment import MODELS,RUN,SETTINGS,actual_settings,read,digest
from rq3_protocol import render,SYSTEM_PROMPT,PROMPT_SHA256

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def audit():
    inputs=read(OUT/'inputs.jsonl')
    expected={(x['repo'],x['number'],x['arm']):x for x in inputs}
    results={}
    problems=[]
    all_expected_google=Counter()
    for tag in ('A','B'):
        rows=read(OUT/f'responses_{MODELS[tag]}.jsonl')
        actual=[(r['repo'],r['number'],r['arm']) for r in rows]
        missing=set(expected)-set(actual)
        bad=[]
        for r in rows:
            ident=r['repo'],r['number'],r['arm']
            messages=[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':expected[ident]['user_message']}]
            if digest(messages)!=r['messages_sha256'] or r['system_sha256']!=PROMPT_SHA256 or r['finish_reason']!='stop' or not r['response'].strip():
                bad.append(ident)
            if tag=='B': all_expected_google[digest(messages)]+=1
        info={'n':len(rows),'expected':320,'duplicates':len(actual)-len(set(actual)),
              'missing':sorted(missing),'invalid':bad,'finish_reasons':dict(Counter(r['finish_reason'] for r in rows))}
        results[tag]=info
        if len(rows)!=320 or missing or bad or info['duplicates']: problems.append(tag)
    main=read(OUT/'main_responses_gemma.jsonl')
    cases=read(RUN/'private_working/real_82_native_staged.jsonl')
    expected_main={(c['case_id'],arm):c for c in cases for arm in ('binary_state','raw_metadata','closure_aware')}
    mainkeys=[(r['case_id'],r['arm']) for r in main]
    invalid=[]
    for r in main:
        ident=r['case_id'],r['arm']
        messages=render(expected_main[ident],r['arm'])
        all_expected_google[digest(messages)]+=1
        if digest(messages)!=r['messages_sha256'] or r['finish_reason']!='stop' or not r['response'].strip(): invalid.append(ident)
    results['main']={'n':len(main),'expected':246,'missing':sorted(set(expected_main)-set(mainkeys)),
                     'duplicates':len(mainkeys)-len(set(mainkeys)),'invalid':invalid,
                     'finish_reasons':dict(Counter(r['finish_reason'] for r in main))}
    if len(main)!=246 or results['main']['missing'] or invalid or results['main']['duplicates']: problems.append('main')
    successful_transport=Counter()
    native=read(OUT/'google_transport_ledger.jsonl')
    for r in native:
        p=r['request']; answer=r['response']
        assert p['generationConfig']=={'temperature':0,'maxOutputTokens':220,'thinkingConfig':{'thinkingLevel':'minimal'}}
        assert p['systemInstruction']['parts'][0]['text']==SYSTEM_PROMPT
        candidate=(answer.get('candidates') or [{}])[0]
        if candidate.get('finishReason')=='STOP':
            messages=[{'role':'system','content':p['systemInstruction']['parts'][0]['text']},
                      {'role':'user','content':p['contents'][0]['parts'][0]['text']}]
            successful_transport[digest(messages)]+=1
    results['google_transport']={'records':len(native),'successful':sum(successful_transport.values()),
                  'expected_successful':566,'matches_all_prompts':successful_transport==all_expected_google}
    if successful_transport!=all_expected_google: problems.append('google_transport')
    results['unresolved_stages']=problems
    results['recorded_failures']=len(read(OUT/'request_failures.jsonl'))
    (OUT/'completion_audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results))
    return problems

def manifest():
    prereg='e0bf6d93f8c5447d2e5ff1d782228c8204490867'
    git=subprocess.run(['git','-C',r'C:\Users\Ogtay\Desktop\test','rev-parse','HEAD'],capture_output=True,text=True)
    ids={}
    for tag in ('A','B'):
        ids[tag]=sorted({r['model_id'] for r in read(OUT/f'responses_{MODELS[tag]}.jsonl')})
    ids['judge']=sorted({r['model_id'] for r in read(OUT/'judgments.jsonl')})
    costs={}
    for tag,name,prices in [('A','attempts_A.jsonl',(.15,.6)),('judge','judge_attempts.jsonl',(.2,1.25))]:
        uses=[r['raw_response'].get('usage',{}) for r in read(OUT/name)]
        inp=sum(r.get('prompt_tokens',0) for r in uses); out=sum(r.get('completion_tokens',0) for r in uses)
        costs[tag]={'input_tokens':inp,'output_tokens':out,'estimated_usd_without_cache_discount':(inp*prices[0]+out*prices[1])/1e6}
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='run_manifest.json']
    file_counts={}
    for p in files:
        info={'bytes':p.stat().st_size,'lines':len(p.read_text(encoding='utf-8-sig').splitlines())}
        if p.suffix=='.jsonl': info['records']=len(read(p))
        elif p.suffix=='.csv':
            with p.open(encoding='utf-8-sig',newline='') as f: info['records']=sum(1 for _ in csv.DictReader(f))
        file_counts[p.name]=info
    old=json.loads((OUT/'preparation_manifest.json').read_text(encoding='utf-8'))
    unchanged={name:sha(Path(name))==expected for name,expected in old['source_sha256'].items()}
    assert all(unchanged.values())
    data={'date':'2026-10-24','timezone':'Asia/Riyadh','written_at_utc':datetime.now(timezone.utc).isoformat(),
          'preregistration_commit':prereg,'git_commit':git.stdout.strip() if git.returncode==0 else None,
          'model_ids_returned':ids,'models_requested':MODELS,
          'providers':{'A':'OpenAI','B':'Google AI Studio native API','judge':'OpenAI'},
          'generation_settings':{'A':actual_settings('A'),'B':actual_settings('B')},
          'judge_settings':{'temperature':0,'reasoning_effort':'none','max_completion_tokens':80},
          'main_rerun_transport_note':'Original main script byte-unchanged; its seed log is the requested seed. Actual Google API seed is null; native request ledger is authoritative.',
          'sample_seed':20261024,'blind_seed':20261024,'generation_order_seed':20261024,
          'system_prompt_sha256':PROMPT_SHA256,'source_files_unchanged':unchanged,
          'system_prompt_exact_file':'system_prompt_exact_utf8.txt',
          'judge_prompt_exact_file':'judge_prompt_exact_utf8.txt',
          'counts_per_jsonl':{p.name:len(read(p)) for p in files if p.suffix=='.jsonl'},
          'counts_per_file':file_counts,
          'sha256_per_output_file':{p.name:sha(p) for p in files},
          'costs':costs,'total_estimated_openai_usd_without_cache_discount':sum(x['estimated_usd_without_cache_discount'] for x in costs.values()),
          'limitations':['Human blind audit pending; automated results provisional.',
                        'Judge and Model A share OpenAI as provider, per approved amendment.',
                        'Original specific-closure-reason-conveyed checker not located; endpoint remains unavailable.'],
          'private_files':'Encrypted credentials are excluded from Git, hashes, copies and manifests.'}
    (OUT/'run_manifest.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({'model_ids':ids,'estimated_openai_usd':data['total_estimated_openai_usd_without_cache_discount']}))

if __name__=='__main__':
    if '--manifest' in sys.argv: manifest()
    else: sys.exit(bool(audit()))
