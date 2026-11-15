"""Adapt only Google's transport; execute the historical generator without editing it."""
import io
import json
import time
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager

@contextmanager
def native_google_transport(key, output_path):
    request_original, open_original = urllib.request.Request, urllib.request.urlopen
    last_start = [0.0]
    native_prefix = 'https://generativelanguage.googleapis.com/v1beta/models/'

    def request(url, data=None, *args, **kwargs):
        if url.startswith('https://generativelanguage.googleapis.com/v1beta/openai') and data:
            time.sleep(max(0,2.1-(time.monotonic()-last_start[0])))
            last_start[0] = time.monotonic()
            p = json.loads(data)
            assert [x['role'] for x in p['messages']] == ['system','user']
            native = {'systemInstruction':{'parts':[{'text':p['messages'][0]['content']}]},
                      'contents':[{'role':'user','parts':[{'text':p['messages'][1]['content']}]}],
                      'generationConfig':{'temperature':p['temperature'],'maxOutputTokens':p['max_tokens'],
                                          'thinkingConfig':{'thinkingLevel':'minimal'}}}
            req = request_original(native_prefix+p['model']+':generateContent',data=json.dumps(native).encode(),
                   headers={'x-goog-api-key':key,'Content-Type':'application/json'})
            return req
        return request_original(url,data,*args,**kwargs)

    def urlopen(req, *args, **kwargs):
        if isinstance(req,request_original) and req.full_url.startswith(native_prefix) and req.data:
            with open_original(req,*args,**kwargs) as response:
                raw = json.load(response)
            candidate = (raw.get('candidates') or [{}])[0]
            parts = candidate.get('content',{}).get('parts',[])
            answer = ''.join(p.get('text','') for p in parts if not p.get('thought'))
            usage = raw.get('usageMetadata',{})
            result = {'id':raw.get('responseId'), 'model':raw.get('modelVersion'),
                      'created':int(time.time()), 'choices':[{'index':0,'message':{'role':'assistant','content':answer},
                       'finish_reason':{'STOP':'stop','MAX_TOKENS':'length'}.get(candidate.get('finishReason'),candidate.get('finishReason','unknown'))}],
                      'usage':{'prompt_tokens':usage.get('promptTokenCount',0),
                               'completion_tokens':usage.get('candidatesTokenCount',0),
                               'total_tokens':usage.get('totalTokenCount',0),
                               'completion_tokens_details':{'reasoning_tokens':usage.get('thoughtsTokenCount',0)}},
                      'provider_raw_response':raw}
            with output_path.open('a',encoding='utf-8') as f:
                f.write(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),
                     'request':json.loads(req.data),'response':raw},ensure_ascii=False,sort_keys=True)+'\n')
                f.flush()
            return io.BytesIO(json.dumps(result).encode())
        return open_original(req,*args,**kwargs)

    urllib.request.Request, urllib.request.urlopen = request, urlopen
    try:
        yield
    finally:
        urllib.request.Request, urllib.request.urlopen = request_original, open_original
