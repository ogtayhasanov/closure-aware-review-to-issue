"""Check supplied account model access without generation calls or exposing credentials."""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent

def get(url, headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as f:
            return {'status': f.status, 'data': json.load(f)}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        for token in (os.environ.get('OPENAI_API_KEY'), os.environ.get('GEMINI_API_KEY')):
            if token:
                raw = raw.replace(token, '[REDACTED]')
        return {'status': e.code, 'error': raw[:1200]}

results = {'checked_at_utc': datetime.now(timezone.utc).isoformat()}
for model in ('gpt-4o-mini-2024-07-18', 'gpt-5.4-nano'):
    r = get('https://api.openai.com/v1/models/' + model, {'Authorization': 'Bearer '+os.environ['OPENAI_API_KEY']})
    results[model] = r
r = get('https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000', {'x-goog-api-key': os.environ['GEMINI_API_KEY']})
if r['status'] == 200:
    models = r['data'].get('models', [])
    results['google'] = {'status': 200, 'gemma_models': [x for x in models if 'gemma' in x.get('name','').lower()]}
else:
    results['google'] = r
(OUT/'provider_probe.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
