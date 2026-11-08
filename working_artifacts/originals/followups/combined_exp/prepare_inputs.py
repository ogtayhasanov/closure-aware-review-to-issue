"""Build RAW+MEANING by replacing exactly the normalized-taxonomy block."""
import csv, hashlib, json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent
FINAL = ROOT.parent / 'final_exp'
BOT = ROOT.parent / 'bot_test'
ROUTING = ROOT.parent / 'routing_test'
def read(p): return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def mh(m): return digest(json.dumps(m, sort_keys=True, ensure_ascii=False))
setup = json.loads((ROUTING/'setup_manifest.json').read_text(encoding='utf-8'))
fairpath = Path(setup['source_files']['fair_saved_inputs']['path'])
sources = [BOT/'inputs.jsonl', FINAL/'inputs_taxonomy_only.jsonl', FINAL/'raw_reference_messages.jsonl', fairpath, FINAL/'generation_settings.json', FINAL/'system_prompt_exact_utf8.txt']
before = {str(p):sha(p) for p in sources}
assert sha(fairpath) == setup['source_files']['fair_saved_inputs']['sha256']
bot = {f"bot_test:{r['repo']}#{r['number']}":r['user_message'] for r in read(BOT/'inputs.jsonl') if r['arm']=='TAXONOMY-V2'}
fair = {'fair:'+r['case_id']:r['messages'][1]['content'] for r in read(fairpath) if r['arm']=='closure_aware'}
raw = {r['input_id']:r['user_message'] for r in read(FINAL/'raw_reference_messages.jsonl')}
base = {**bot, **fair}
assert len(base)==162
rows, checks = [], []
heading = 'NORMALIZED TAXONOMY FIELDS:\n'
ending = '\n\nWrite a response to the review.'
rawhead = 'RAW TRACKER CLOSURE FIELDS:\n'
for t in read(FINAL/'inputs_taxonomy_only.jsonl'):
    original = base[t['input_id']]
    assert original.count(heading)==1 and original.endswith(ending)
    start = original.index(heading)
    finish = len(original)-len(ending)
    old = original[start:finish]
    assert len(old.splitlines())==4 and old.splitlines()[1].startswith('- l1_class: ') and old.splitlines()[2].startswith('- subtype: ') and old.splitlines()[3].startswith('- action_l1: ')
    tax = t['messages'][1]['content']
    block = tax[tax.index('CLOSURE:\n'):-len(ending)]
    assert len(block.splitlines())==3
    new = original[:start]+block+original[finish:]
    assert new[:start].encode()==original[:start].encode()
    assert new[start+len(block):].encode()==original[finish:].encode()
    assert new[start:start+len(block)]==block
    raw_original = raw[t['input_id']]
    raw_block = raw_original[raw_original.index(rawhead):-len(ending)]
    assert raw_block in new and new.count(rawhead)==1
    assert new[:start] == raw_original[:-len(ending)]+'\n\n'
    messages=[t['messages'][0], {'role':'user','content':new}]
    assert digest(messages[0]['content'])==t['system_sha256']
    rows.append({**t,'arm':'RAW+MEANING','messages':messages,'messages_sha256':mh(messages),'user_message_sha256':digest(new),'source_user_message_sha256':digest(original)})
    checks.append({'input_id':t['input_id'],'outside_replaced_block_byte_identical':True,'closure_equals_taxonomy_only':True,'raw_block_retained':True,'source_sha256':digest(original),'raw_block_sha256':digest(raw_block),'closure_sha256':digest(block)})
assert len(rows)==162 and sum(r['excluded_from_all_analyses'] for r in rows)==1
assert before == {str(p):sha(p) for p in sources}
with (ROOT/'inputs_raw_meaning.jsonl').open('w',encoding='utf-8',newline='\n') as f:
    for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
with (ROOT/'input_integrity.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
for name in ['generation_settings.json','system_prompt_exact_utf8.txt','judge_core_prompt.txt','judge_routing_prompt.txt','judge_audit_prompt.txt']:
    shutil.copyfile(FINAL/name,ROOT/name)
manifest={'preregistration_commit':'48d8b42','total':162,'bot':80,'fair':82,'all_required_checks_passed':True,'analysis_exclusions':[{'input_id':r['input_id'],'reason':r['exclusion_reason']} for r in rows if r['excluded_from_all_analyses']], 'source_sha256':before,'outputs_sha256':{n:sha(ROOT/n) for n in ['inputs_raw_meaning.jsonl','generation_settings.json','system_prompt_exact_utf8.txt']}}
(ROOT/'preparation_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k not in ['source_sha256','outputs_sha256']},indent=2))
