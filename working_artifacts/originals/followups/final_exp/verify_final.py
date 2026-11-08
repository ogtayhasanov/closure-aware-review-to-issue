"""Verify final-stage completeness, exact request settings, and original source preservation."""
import csv,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prep=load(OUT/'preparation_manifest.json');cfg=load(OUT/'generation_settings.json')
inputs={r['input_id']:r for r in read(OUT/'inputs_taxonomy_only.jsonl')}
assert len(inputs)==162
for item in prep['source_files'].values():assert sha(Path(item['path']))==item['sha256'],item['path']
for name in ['inputs_taxonomy_only.jsonl','generation_settings.json','system_prompt_exact_utf8.txt']:
    assert sha(OUT/name)==prep['outputs_sha256'][name]
new=[]
for tag in ['A','B']:
    settings=cfg['generation'][tag]
    records=read(OUT/f"responses_taxonomy_only_{settings['model_requested']}.jsonl")
    assert len(records)==len({r['input_id'] for r in records})==162
    assert {r['input_id'] for r in records}==set(inputs)
    for r in records:
        job=inputs[r['input_id']];p=r['request_payload']
        assert r['finish_reason']=='stop' and r['response'].strip()
        assert r['model_id'] in settings['model_ids_returned_in_reference_run']
        assert r['messages_sha256']==job['messages_sha256']
        assert hashlib.sha256(r['response'].encode()).hexdigest()==r['response_sha256']
        assert r['excluded_from_all_analyses']==job['excluded_from_all_analyses']
        if tag=='A':
            assert p['messages']==job['messages'] and p['temperature']==0 and p['max_tokens']==220 and p['seed']==20261020
        else:
            assert p['systemInstruction']['parts'][0]['text']==job['messages'][0]['content']
            assert p['contents'][0]['parts'][0]['text']==job['messages'][1]['content']
            assert p['generationConfig']=={'temperature':0,'maxOutputTokens':220,'thinkingConfig':{'thinkingLevel':'minimal'}}
            assert r['usage']['reasoning_tokens']==0
    new+=records
assert len(new)==324
for name,count in [('judge_core_scores.jsonl',324),('judge_routing_scores.jsonl',324),('judge_audit_scores.jsonl',140),('judge_audit_routing_scores.jsonl',140)]:
    rows=read(OUT/name);assert len(rows)==len({r['score_id'] for r in rows})==count
    assert all(r['judge_model'] in cfg['judge']['model_ids_returned_in_reference_run'] for r in rows)
with (OUT/'audit_sheet.csv').open(encoding='utf-8-sig',newline='') as f:sheet=list(csv.DictReader(f))
with (OUT/'audit_key.csv').open(encoding='utf-8-sig',newline='') as f:key=list(csv.DictReader(f))
assert len(sheet)==len(key)==140
keyed={r['sheet_id']:r for r in key}
for r in sheet:
    k=keyed[r['sheet_id']]
    assert hashlib.sha256(r['response'].encode()).hexdigest()==k['response_sha256']
    assert hashlib.sha256(r['tracker_evidence'].encode()).hexdigest()==k['tracker_evidence_sha256']
    assert str(k['issue_number'])!='2131' or 'nextcloud/' not in k['repository']
    if k['ASKS_DETAILS_applicable']=='False':assert r['ASKS_DETAILS']=='NA'
    if k['SAYS_DUPLICATE_applicable']=='False':assert r['SAYS_DUPLICATE']=='NA'
prev=load(OUT/'prevalence_manifest.json')
assert all(sha(Path(p))==h for p,h in prev['source_scan_sha256'].items())
summary={'final_generation_responses':324,'exact_generation_requests_verified':324,'non_stop_or_blank_final_responses':0,
 'core_scores':324,'routing_scores':324,'audit_outcome_scores':140,'audit_routing_scores':140,
 'audit_rows':140,'source_files_unchanged':True,'original_scans_unchanged':True,
 'gemma_thinking_tokens':0,'human_sheet_text_preserved':True,'human_labels_analysis':'pending'}
(OUT/'verification_final.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,indent=2))
