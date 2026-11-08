"""Prepare Checkpoint 1 only. Replace exactly one closure block; no API calls."""
import collections
import csv
import difflib
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent
BOT=OUT.parent/'bot_test'
ROUTING=OUT.parent/'routing_test'
PREREG_COMMIT='fce3086081968dc950d972e24a57bcd5def70699'
MEANINGS_COMMIT='f8f329f76c0c5cd772d9f704763ba99b55d22c0c'
HEAD='RAW TRACKER CLOSURE FIELDS:\n'
ENDING='\n\nWrite a response to the review.'
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def message_hash(messages):return digest(json.dumps(messages,sort_keys=True,ensure_ascii=False))
def dump(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
bot_manifest=load(BOT/'run_manifest.json')
setup=load(ROUTING/'setup_manifest.json')
meanings=load(OUT/'meaning_lines.json')
source={
 'bot_manifest':BOT/'run_manifest.json','bot_inputs':BOT/'inputs.jsonl',
 'bot_sample':BOT/'sample_records.jsonl','system':BOT/bot_manifest['system_prompt_exact_file'],
 'routing_setup_manifest':ROUTING/'setup_manifest.json',
 'fair_cases':Path(setup['source_files']['cases']['path']),
 'fair_inputs':Path(setup['source_files']['fair_saved_inputs']['path']),
 'fair_responses':Path(setup['source_files']['fair_responses']['path']),
 'meaning_lines':OUT/'meaning_lines.json','preregistration':OUT/'final_experiments.md',
}
before={k:sha(p) for k,p in source.items()}
for key in ['cases','fair_saved_inputs','fair_responses']:
    info=setup['source_files'][key];assert sha(Path(info['path']))==info['sha256']
system=(source['system']).read_bytes().decode('utf-8')
assert digest(system)==bot_manifest['system_prompt_sha256']
settings={
 'generation':{tag:{'model_requested':bot_manifest['models_requested'][tag],
   'model_ids_returned_in_reference_run':bot_manifest['model_ids_returned'][tag],
   'provider':bot_manifest['providers'][tag],**bot_manifest['generation_settings'][tag]} for tag in ['A','B']},
 'judge':{'model_requested':bot_manifest['models_requested']['judge'],
   'model_ids_returned_in_reference_run':bot_manifest['model_ids_returned']['judge'],
   'provider':bot_manifest['providers']['judge'],**bot_manifest['judge_settings']},
 'system_sha256':digest(system),'source_manifest_sha256':before['bot_manifest']}
assert settings['generation']['A']['model_requested']=='gpt-4o-mini-2024-07-18'
assert settings['generation']['B']['model_requested']=='gemma-4-26b-a4b-it'
assert settings['generation']['A']['temperature']==settings['generation']['B']['temperature']==0
assert settings['generation']['A']['max_tokens']==settings['generation']['B']['max_tokens']==220
raw_bot={(r['repo'],r['number']):r for r in read(source['bot_inputs']) if r['arm']=='RAW'}
v2_bot={(r['repo'],r['number']):r for r in read(source['bot_inputs']) if r['arm']=='TAXONOMY-V2'}
sample=read(source['bot_sample'])
assert len(sample)==len(raw_bot)==len(v2_bot)==80
assert collections.Counter(r['group'] for r in sample)=={'BOT':50,'HUMAN':30}
fair=read(source['fair_cases']);fair_byid={r['case_id']:r for r in fair}
fair_prompts={(r['case_id'],r['arm']):r for r in read(source['fair_inputs'])}
assert len(fair_byid)==82 and len(fair_prompts)==246
fair_responses=read(source['fair_responses'])
assert len(fair_responses)==246
for r in fair_responses:
    p=fair_prompts[r['case_id'],r['arm']]
    assert p['messages'][0]=={'role':'system','content':system}
    assert r['messages_sha256']==p['messages_sha256']==message_hash(p['messages'])
    assert r['model_requested']==settings['generation']['A']['model_requested']
    assert r['seed']==settings['generation']['A']['seed']

jobs=[];raw_snapshots=[];invariants=[]
def add(dataset,cid,repo,number,group,cls,subtype,meaning_key,raw,excluded=False):
    assert raw.count(HEAD)==1 and raw.endswith(ENDING)
    start=raw.index(HEAD);end=len(raw)-len(ENDING)
    prefix=raw[:start];old=raw[start:end];suffix=raw[end:]
    assert old.startswith(HEAD) and not old.endswith('\n')
    assert prefix.endswith('\n\n') and 'Binary state: ' in prefix
    assert all(line.startswith('- ') for line in old.splitlines()[1:])
    new_block=f'CLOSURE:\n- class: {cls}\n- meaning: {meanings[meaning_key]}'
    new=prefix+new_block+suffix
    assert new[:start].encode()==prefix.encode()
    assert new[-len(suffix):].encode()==suffix.encode()
    assert new.count('CLOSURE:\n')==1 and HEAD not in new
    assert 'NORMALIZED TAXONOMY FIELDS:' not in new
    assert new_block.splitlines()==['CLOSURE:',f'- class: {cls}',f'- meaning: {meanings[meaning_key]}']
    input_id=f'{dataset}:{cid}'
    messages=[{'role':'system','content':system},{'role':'user','content':new}]
    jobs.append({'input_id':input_id,'dataset':dataset,'case_id':cid,'repository':repo,'number':number,
        'group':group,'arm':'TAXONOMY-ONLY','received_class':cls,'received_subtype':subtype,
        'meaning_key':meaning_key,'excluded_from_all_analyses':excluded,
        'exclusion_reason':'Nextcloud #2131 was fixed by merged PR #4470; user explicitly excludes it from every analysis' if excluded else '',
        'messages':messages,'messages_sha256':message_hash(messages),'system_sha256':digest(system),
        'user_message_sha256':digest(new),'raw_user_message_sha256':digest(raw)})
    raw_snapshots.append({'input_id':input_id,'user_message':raw,'user_message_sha256':digest(raw)})
    invariants.append({'input_id':input_id,'dataset':dataset,'prefix_utf8_sha256':digest(prefix),
       'suffix_utf8_sha256':digest(suffix),'raw_block_utf8_sha256':digest(old),
       'replacement_block_utf8_sha256':digest(new_block),'outside_block_byte_identical':True,
       'binary_state_line_preserved':True,'received_class':cls,'received_subtype':subtype,
       'meaning_key':meaning_key,'excluded_from_all_analyses':excluded})

for r in sorted(sample,key=lambda r:(r['repo'],r['number'])):
    raw=raw_bot[r['repo'],r['number']]['user_message']
    v2=v2_bot[r['repo'],r['number']]['user_message']
    cls=r['v2_class'];subtype='OTHER' if cls=='ABANDONED' else 'wontfix'
    assert f'- l1_class: {cls}\n- subtype: {subtype}\n' in v2
    assert raw_bot[r['repo'],r['number']]['system_sha256']==digest(system)
    if r['group']=='BOT':
        assert cls=='ABANDONED';meaning='ABANDONED/bot-closed (V2)'
    else:
        assert cls=='REJECTED';meaning=cls
    add('bot_test',f"{r['repo']}#{r['number']}",r['repo'],r['number'],r['group'],cls,subtype,meaning,raw)
for r in sorted(fair,key=lambda r:r['case_id']):
    cls=r['l1_class'];subtype=r['subtype']
    old_tax=fair_prompts[r['case_id'],'closure_aware']['messages'][1]['content']
    assert f'- l1_class: {cls}\n- subtype: {subtype}\n' in old_tax
    meaning=f'{cls}/{subtype}' if cls=='ABANDONED' else cls
    excluded=r['repository']=='nextcloud/android (GitHub)' and str(r['display_issue_id'])=='2131'
    add('fair',r['case_id'],r['repository'],r['display_issue_id'],'',cls,subtype,meaning,
        fair_prompts[r['case_id'],'raw_metadata']['messages'][1]['content'],excluded)
assert len(jobs)==len({r['input_id'] for r in jobs})==162
assert sum(r['excluded_from_all_analyses'] for r in jobs)==1
assert sum(r['dataset']=='fair' and r['received_class'] in {'REJECTED','ABANDONED','REDIRECTED'} and not r['excluded_from_all_analyses'] for r in jobs)==35
for name,rows in [('inputs_taxonomy_only.jsonl',jobs),('raw_reference_messages.jsonl',raw_snapshots)]:
    with (OUT/name).open('w',encoding='utf-8',newline='\n') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
with (OUT/'input_integrity.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(invariants[0]));w.writeheader();w.writerows(invariants)
excluded=[{k:r[k] for k in ['input_id','dataset','case_id','repository','number','received_class','received_subtype','excluded_from_all_analyses','exclusion_reason']} for r in jobs if r['excluded_from_all_analyses']]
dump('analysis_exclusions.json',excluded)
dump('generation_settings.json',settings)
(OUT/'system_prompt_exact_utf8.txt').write_bytes(system.encode('utf-8'))

# Reproducible examples: first BOT/HUMAN by repository/issue, first Nextcloud
# NEEDS_INFO case by case_id (native needs-info label rather than template inference).
examples=[next(r for r in jobs if r['dataset']=='bot_test' and r['group']=='BOT'),
          next(r for r in jobs if r['dataset']=='bot_test' and r['group']=='HUMAN'),
          next(r for r in jobs if r['dataset']=='fair' and 'nextcloud/' in r['repository'] and r['received_subtype']=='NEEDS_INFO')]
raw_byid={r['input_id']:r['user_message'] for r in raw_snapshots}
report=['# TAXONOMY-ONLY input review — Checkpoint 1','',
    f'Instructions committed first as `{PREREG_COMMIT}`. User-supplied meaning lines committed as `{MEANINGS_COMMIT}` before constructing inputs.', '',
    '**Prepared 162 inputs: 50 BOT + 30 HUMAN + 82 fair cases. No generation or judging has started.**', '',
    'Every new user message starts from the exact saved RAW/raw_metadata message. Only the heading and lines of '
    'the raw closure block are replaced. For all 162 inputs, the UTF-8 bytes of the prefix and suffix match exactly, '
    'including every Binary state line and the final instruction. The shared system message is unchanged. '
    'The new closure block contains only class and the exact user-supplied meaning line; raw labels are not copied into it. '
    'Existing review/title/body text remains unchanged and could itself contain label-like words.', '',
    '## Settings read from saved manifests','',
    '- Model A: gpt-4o-mini-2024-07-18, OpenAI, temperature 0, max_tokens 220, seed 20261020.',
    '- Model B: gemma-4-26b-a4b-it, Google native API, temperature 0, maxOutputTokens 220, thinkingLevel minimal, API seed omitted, as in bot_test.',
    '- Judge configuration retained: requested gpt-5.4-nano (reference returned snapshot gpt-5.4-nano-2026-03-17), temperature 0, reasoning none, max_completion_tokens 80.',
    f'- Shared system SHA-256: `{digest(system)}`.', '',
    '## Exclusions and frozen evidence','',
    'Nextcloud #2131 remains ABANDONED/OTHER exactly as received, with meaning “Closed without a fix. The reason is not recorded.” '
    'It is retained for generation but explicitly excluded from all analyses. The tracker refresh establishes that '
    'it was fixed by merged PR #4470; no taxonomy class is used as correctness truth. This leaves 35 of the original '
    '36 fair audit cases, hence 140 GPT-4o-mini responses for the later four-arm audit. No other case is excluded.', '',
    'Nextcloud #3425 remains included. The later audit will include its closing-comment evidence about Samsung '
    'battery restrictions and logs, separate from the supplied taxonomy block. No original tracker snapshot, '
    'message, response, earlier checkpoint, or manuscript has been edited.', '',
    '## Full example messages and diffs','']
for r in examples:
    raw=raw_byid[r['input_id']];new=r['messages'][1]['content']
    label=r['group'] if r['dataset']=='bot_test' else 'fair NEEDS_INFO'
    report += [f"### {label}: {r['repository']} #{r['number']}",'',
       'Selection is deterministic as described in prepare_inputs.py, without examining generated outcomes.', '',
       'TAXONOMY-ONLY user message:', '', '```text',new,'```','',
       'RAW user message:', '', '```text',raw,'```','',
       'Exact change (RAW → TAXONOMY-ONLY):', '', '```diff',
       ''.join(difflib.unified_diff(raw.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='RAW',tofile='TAXONOMY-ONLY')).rstrip(),'```','']
report += ['## Shared system message','', '```text',system,'```','',
    '**Stopped at CHECKPOINT 1.** Awaiting the user’s OK before any new responses, scores, human audit sheet, '
    'prevalence scan, or release package is produced.']
(OUT/'checkpoint1.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
assert before=={k:sha(p) for k,p in source.items()}
dump('preparation_manifest.json',{'preregistration_commit':PREREG_COMMIT,'meaning_lines_commit':MEANINGS_COMMIT,
    'source_files':{k:{'path':str(p),'sha256':before[k],'unchanged_after_preparation':True} for k,p in source.items()},
    'input_counts':{'bot_test':80,'BOT':50,'HUMAN':30,'fair':82,'total':162},
    'all_162_outside_closure_blocks_utf8_identical':True,'binary_state_lines_preserved':162,
    'meaning_usage':dict(collections.Counter(r['meaning_key'] for r in jobs)),
    'generation_exclusions':0,'analysis_exclusions':excluded,'fair_human_audit_cases':35,
    'fair_human_audit_responses_after_generation':140,'new_responses_generated':0,'new_scores_generated':0,
    'system_sha256':digest(system),'example_input_ids':[r['input_id'] for r in examples],
    'outputs_sha256':{name:sha(OUT/name) for name in ['inputs_taxonomy_only.jsonl','raw_reference_messages.jsonl',
       'input_integrity.csv','analysis_exclusions.json','generation_settings.json','system_prompt_exact_utf8.txt','checkpoint1.md']}})
print(json.dumps({'prepared':len(jobs),'meanings':dict(collections.Counter(r['meaning_key'] for r in jobs)),
    'analysis_exclusions':excluded,'all_162_outside_blocks_byte_identical':True,'examples':[(r['repository'],r['number'],r['group'] or 'NEEDS_INFO') for r in examples]},indent=2))
