"""Read-only model access check; never write credentials or generation outputs."""
import json,os,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parent
def get(url,headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as r:
            data=json.load(r)
        return {'status':200,'data':data}
    except urllib.error.HTTPError as e:
        msg=e.read().decode(errors='replace')
        for key in ['OPENAI_API_KEY','GEMINI_API_KEY']:
            secret=os.environ.get(key,'')
            if secret:msg=msg.replace(secret,'[REDACTED]')
        return {'status':e.code,'error':msg[:1200]}
results={'checked_at_utc':datetime.now(timezone.utc).isoformat()}
for model in ['gpt-4o-mini-2024-07-18','gpt-5.4-nano']:
    results[model]=get('https://api.openai.com/v1/models/'+model,{'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']})
results['gemma-4-26b-a4b-it']=get('https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it',{'x-goog-api-key':os.environ['GEMINI_API_KEY']})
(OUT/'provider_access.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({k:v['status'] for k,v in results.items() if isinstance(v,dict)}))
