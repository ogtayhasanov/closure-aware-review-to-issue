"""Resumable exact-settings generation and blinded automated response scoring."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,random,sys,threading,time
from pathlib import Path
import urllib.request,urllib.error
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
LOCK=threading.Lock()
GOOGLE_LOCK=threading.Lock()
GOOGLE_NEXT=0.0
SETTINGS=json.loads((OUT/'generation_settings.json').read_text(encoding='utf-8'))
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()] if p.exists() else []
def sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def append(name,row):
    with LOCK:
        with (OUT/name).open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n');f.flush()
def safe(e):
    s=str(e)
    for name in ['OPENAI_API_KEY','GEMINI_API_KEY']:
        key=os.environ.get(name)
        if key:s=s.replace(key,'[REDACTED]')
    return s[:1800]
def post(url,payload,headers):
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={**headers,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
    except urllib.error.HTTPError as e:raise RuntimeError(f'HTTP {e.code}: '+e.read().decode(errors='replace')[:1400]) from e
def frozen_check():
    m=json.loads((OUT/'preparation_manifest.json').read_text(encoding='utf-8'))
    for name in ['inputs_raw_meaning.jsonl','system_prompt_exact_utf8.txt','generation_settings.json']:
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==m['outputs_sha256'][name],name
def generation(tag):
    frozen_check();cfg=SETTINGS['generation'][tag];model=cfg['model_requested']
    output=f'responses_raw_meaning_{model}.jsonl'
    done=read(OUT/output);present={r['input_id'] for r in done};assert len(done)==len(present)
    jobs=[r for r in read(OUT/'inputs_raw_meaning.jsonl') if r['input_id'] not in present]
    random.Random(20261024).shuffle(jobs)
    def job(r):
        for attempt in range(1,4):
            started=now()
            try:
                if tag=='A':
                    payload={'model':model,'messages':r['messages'],'temperature':cfg['temperature'],'max_tokens':cfg['max_tokens'],'seed':cfg['seed']}
                    raw=post('https://api.openai.com/v1/chat/completions',payload,{'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']})
                    answer=raw['choices'][0]['message'].get('content') or '';finish=raw['choices'][0]['finish_reason'];returned=raw['model'];usage=raw.get('usage',{})
                else:
                    global GOOGLE_NEXT
                    with GOOGLE_LOCK:
                        time.sleep(max(0.0, GOOGLE_NEXT-time.monotonic()))
                        GOOGLE_NEXT=time.monotonic()+2.1
                    payload={'systemInstruction':{'parts':[{'text':r['messages'][0]['content']}]},
                        'contents':[{'role':'user','parts':[{'text':r['messages'][1]['content']}]}],
                        'generationConfig':{'temperature':cfg['temperature'],'maxOutputTokens':cfg['max_tokens'],'thinkingConfig':{'thinkingLevel':cfg['thinking_level']}}}
                    raw=post('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',payload,{'x-goog-api-key':os.environ['GEMINI_API_KEY']})
                    candidate=raw.get('candidates',[{}])[0];parts=candidate.get('content',{}).get('parts',[])
                    answer=''.join(p.get('text','') for p in parts if not p.get('thought'))
                    finish={'STOP':'stop','MAX_TOKENS':'length'}.get(candidate.get('finishReason'),candidate.get('finishReason','unknown'))
                    returned=raw.get('modelVersion');u=raw.get('usageMetadata',{})
                    usage={'prompt_tokens':u.get('promptTokenCount',0),'completion_tokens':u.get('candidatesTokenCount',0),'reasoning_tokens':u.get('thoughtsTokenCount',0),'total_tokens':u.get('totalTokenCount',0)}
                rec={**{k:r[k] for k in ['input_id','dataset','case_id','repository','number','group','arm','excluded_from_all_analyses','messages_sha256','system_sha256']},
                    'model_requested':model,'model_id':returned,'timestamp':started,'settings':cfg,'request_payload':payload,
                    'response':answer,'response_sha256':sha(answer),'finish_reason':finish,'raw_response':raw,'usage':usage,'attempt':attempt}
                append(f'generation_attempts_{tag}.jsonl',rec)
                assert returned in cfg['model_ids_returned_in_reference_run'],f'Model version drift: {returned}'
                assert finish=='stop' and answer.strip(),'Blank or non-stop response retained in attempt ledger'
                append(output,rec);return True
            except Exception as e:
                append('request_failures.jsonl',{'stage':'generation','tag':tag,'input_id':r['input_id'],'attempt':attempt,'timestamp':now(),'error':safe(e)})
                if any(s in str(e) for s in ['HTTP 400','HTTP 401','HTTP 403','HTTP 404','insufficient_quota','Model version drift']):return False
                if attempt<3:time.sleep(12*attempt)
        return False
    success=0
    if tag=='B':
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i,f in enumerate(as_completed([pool.submit(job,r) for r in jobs]),1):
                success+=f.result()
                if i%10==0:print(f'Generation {tag}: {len(present)+success}/162',flush=True)
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i,f in enumerate(as_completed([pool.submit(job,r) for r in jobs]),1):
                success+=f.result()
                if i%20==0:print(f'Generation {tag}: {len(present)+success}/162',flush=True)
    print(f'Generation {tag} complete: {len(read(OUT/output))}/162',flush=True)
    return len(read(OUT/output))==162
def judge(stage,only_model=None):
    frozen_check()
    prompt=(OUT/('judge_'+('routing' if stage=='reference_routing' else stage)+'_prompt.txt')).read_text(encoding='utf-8')
    expected={'core':{'DECLINED','FIX_CLAIM','INACTIVITY'},'routing':{'ASKS_DETAILS','SAYS_DUPLICATE'},'audit':{'NO_FALSE_FIX','STATES_OUTCOME'},'audit_routing':{'ASKS_DETAILS','SAYS_DUPLICATE'},'reference_routing':{'ASKS_DETAILS','SAYS_DUPLICATE'}}[stage]
    jobs=[]
    if stage=='reference_routing':
        jobs=read(OUT/'reference_routing_inputs.jsonl')
    elif stage in ['audit','audit_routing']:
        jobs=read(OUT/'audit_judge_inputs.jsonl')
        if stage=='audit_routing':
            for j in jobs:j['judge_user_message']=j['judge_user_message'].rsplit('\n\nRESPONSE:\n',1)[1]
    else:
        for tag in ['A','B']:
            if only_model and tag!=only_model:continue
            model=SETTINGS['generation'][tag]['model_requested']
            for r in read(OUT/f'responses_raw_meaning_{model}.jsonl'):
                jobs.append({'score_id':model+':'+r['input_id'],'input_id':r['input_id'],'model':model,
                    'response':r['response'],'response_sha256':r['response_sha256'],'judge_user_message':r['response']})
        assert len(jobs)==(162 if only_model else 324),'Generation incomplete; no silent scoring omissions'
    name=f'judge_{stage}_scores.jsonl';done=read(OUT/name);present={r['score_id'] for r in done};assert len(done)==len(present)
    todo=[j for j in jobs if j['score_id'] not in present]
    cfg=SETTINGS['judge']
    def job(j):
        payload={'model':cfg['model_requested'],'messages':[{'role':'system','content':prompt},{'role':'user','content':j['judge_user_message']}],
            'temperature':cfg['temperature'],'reasoning_effort':cfg['reasoning_effort'],'max_completion_tokens':cfg['max_completion_tokens'],'response_format':{'type':'json_object'}}
        for attempt in range(1,5):
            try:
                raw=post('https://api.openai.com/v1/chat/completions',payload,{'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']})
                append(f'judge_{stage}_attempts.jsonl',{'score_id':j['score_id'],'timestamp':now(),'request':payload,'raw_response':raw,'attempt':attempt})
                assert raw['model'] in cfg['model_ids_returned_in_reference_run'],'Judge version drift: '+raw['model']
                assert raw['choices'][0]['finish_reason']=='stop','Non-stop judge completion'
                labels=json.loads(raw['choices'][0]['message']['content'])
                assert set(labels)==expected and all(type(v) is bool for v in labels.values()),'Invalid judge schema'
                append(name,{k:v for k,v in {**j,'judge':labels,'judge_model':raw['model'],'judge_prompt_sha256':sha(prompt),
                    'judge_user_sha256':sha(j['judge_user_message']),'usage':raw.get('usage',{}),'timestamp':now()}.items() if k not in ['response','judge_user_message']})
                return True
            except Exception as e:
                append('request_failures.jsonl',{'stage':'judge_'+stage,'score_id':j['score_id'],'attempt':attempt,'timestamp':now(),'error':safe(e)})
                if any(s in str(e) for s in ['HTTP 400','HTTP 401','HTTP 403','HTTP 404','insufficient_quota','version drift']):return False
                if attempt<4:time.sleep(5*attempt)
        return False
    successes=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,f in enumerate(as_completed([pool.submit(job,j) for j in todo]),1):
            successes+=f.result()
            if i%40==0:print(f'Judge {stage}: {len(present)+successes}/{len(jobs)}',flush=True)
    print(f'Judge {stage} complete: {len(read(OUT/name))}/{len(jobs)}',flush=True)
    return len(read(OUT/name))==len(jobs)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['A','B','core','routing','audit','audit_routing','reference_routing']);p.add_argument('--only-model',choices=['A','B']);args=p.parse_args()
    append('execution_sources.jsonl',{'timestamp':now(),'stage':args.stage,'only_model':args.only_model,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    ok=generation(args.stage) if args.stage in ['A','B'] else judge(args.stage,args.only_model)
    sys.exit(0 if ok else 1)
