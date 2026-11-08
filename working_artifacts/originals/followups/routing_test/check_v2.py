"""Read existing bot-test artifacts only; create Checkpoint 1 evidence locally."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
SOURCE = Path(r'C:\Users\Ogtay\Desktop\test\bot_test')
MIRROR = OUT.parent / 'bot_test'
FILES = ['inputs.jsonl', 'sample_records.jsonl', 'responses_gpt-4o-mini-2024-07-18.jsonl',
         'judgments.jsonl', 'lexical.py', 'system_prompt_exact_utf8.txt']
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
before = {name: digest(SOURCE/name) for name in FILES}
assert all(before[name] == digest(MIRROR/name) for name in FILES)
def read(name):
    return [json.loads(line) for line in (SOURCE/name).read_text(encoding='utf-8').splitlines() if line.strip()]
spec = importlib.util.spec_from_file_location('frozen_lexical', SOURCE/'lexical.py')
lex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lex)
samples = sorted([r for r in read('sample_records.jsonl') if r['group']=='BOT'], key=lambda r:(r['repo'], r['number']))
assert len(samples)==50
selected = random.Random(20261024).sample(samples, 5)
inputs = {(r['repo'],r['number'],r['arm']):r for r in read('inputs.jsonl')}
responses = {(r['repo'],r['number'],r['arm']):r for r in read('responses_gpt-4o-mini-2024-07-18.jsonl')}
judgments = {(r['identity']['repo'],r['identity']['number'],r['identity']['arm']):r
             for r in read('judgments.jsonl') if r['identity']['dataset']=='bot_test' and r['identity']['generator']=='A'}
example = samples[0]
key = (example['repo'],example['number'])
raw = inputs[(*key,'RAW')]['user_message']
v2 = inputs[(*key,'TAXONOMY-V2')]['user_message']
diff = ''.join(difflib.unified_diff(raw.splitlines(keepends=True),v2.splitlines(keepends=True),fromfile='RAW',tofile='TAXONOMY-V2'))
closure = v2.split('RAW TRACKER CLOSURE FIELDS:\n',1)[1].rsplit('\n\nWrite a response to the review.',1)[0]
taxonomy = closure.split('NORMALIZED TAXONOMY FIELDS:\n',1)[1]
all_bot_v2 = [inputs[(r['repo'],r['number'],'TAXONOMY-V2')]['user_message'] for r in samples]
assert all(any(line.startswith('- labels: ') and 'wontfix' in json.loads(line[len('- labels: '):]) for line in s.splitlines()) for s in all_bot_v2)
assert all('NORMALIZED TAXONOMY FIELDS:\n'+taxonomy in s for s in all_bot_v2)
lines = ['# V2 check — Checkpoint 1', '',
    'Pre-registration commit: `0b83e2c` (Pre-register routing test and V2 check).', '',
    'Existing Model A outputs only. No generation, rescoring by a model, prompt edits, or paper edits. '
    'The frozen lexical function is used only to verify the saved scores and locate supporting text.', '',
    '## Finding', '',
    'All 50 BOT V2 prompts retain the raw `wontfix` label and append only three normalized fields. '
    'There is no prose definition of ABANDONED and no explanation in these fields that a bot closed the issue. '
    'Thus V2 tested raw tracker fields plus a terse taxonomy code. The examples below show responses interpreting '
    'the retained label as a decision not to address the issue. This is evidence of a plausible prompt conflict; '
    'it does not establish a causal explanation or measure a corrected prompt.', '',
    '## a. Full user messages and diff', '',
    f"Example: [{example['repo']}#{example['number']}]({example['url']}). Selected as the first BOT case sorted by repository and numeric issue number.", '',
    '### TAXONOMY-V2', '', '```text', v2, '```', '', '### RAW', '', '```text', raw, '```', '',
    '### Unified diff (RAW → TAXONOMY-V2)', '', '```diff', diff.rstrip(), '```', '',
    'Both arms use the same saved system prompt. Its full text is included below for context.', '',
    '```text', (SOURCE/'system_prompt_exact_utf8.txt').read_text(encoding='utf-8'), '```', '',
    '## b. Exact V2 closure block', '', '```text', closure, '```', '',
    'Yes: in this example the raw label line is exactly `- labels: ["wontfix"]`. All 50 BOT V2 prompts contain `wontfix` in their raw labels; 14 also include other labels.', '',
    '## c. Exact ABANDONED class text', '', '```text', taxonomy, '```', '',
    'These are the complete normalized taxonomy fields received by the model. No descriptive ABANDONED class text was supplied in the user or shared system message. '
    'This same three-field block occurs in all 50 BOT V2 inputs.', '',
    '## d. Five seeded BOT responses', '',
    'Sampling: Python `random.Random(20261024).sample(sorted_BOT_cases, 5)`, with the 50 cases sorted '
    'by `(repo, numeric issue number)`. No filtering on the response or scores; all five sampled cases are shown and none excluded.', '',
    'The judge saved boolean labels only, with no sentence-level rationale. Consequently the quotations below are '
    'supporting sentences identified from the saved responses and frozen lexical matches, not a recorded explanation '
    'from the judge. Judge and lexical DECLINED values are reported separately.', '']
evidence = []
for i,r in enumerate(selected,1):
    k=(r['repo'],r['number'],'TAXONOMY-V2')
    response=responses[k]['response']
    j=judgments[k]
    assert hashlib.sha256(response.encode()).hexdigest()==j['response_sha256']
    assert lex.score(response)==j['lexical']
    sentences=re.split(r'(?<=[.!?])\s+',response)
    support=[s for s in sentences if lex.score(s)['DECLINED']]
    matches=[{'pattern':p.pattern,'match':m.group()} for p in lex.COMPILED['DECLINED'] for m in p.finditer(response)]
    evidence.append({'repo':r['repo'],'number':r['number'],'response':response,
                     'judge_declined':j['judge']['DECLINED'],'lexical_declined':j['lexical']['DECLINED'],
                     'supporting_sentences':support,'lexical_matches':matches})
    lines += [f"### {i}. {r['repo']}#{r['number']}", '', f"Source: {r['url']}", '',
              f"Saved DECLINED: judge **{j['judge']['DECLINED']}**, lexical **{j['lexical']['DECLINED']}**.", '',
              'Full saved response:', '', '> '+response.replace('\n','\n> '), '',
              'Sentence(s) supporting DECLINED:', '']
    lines += ['> '+s for s in support] if support else ['No sentence triggers the frozen DECLINED lexical check.']
    lines += ['', 'Exact lexical matches: '+', '.join('`'+m['match']+'`' for m in matches)+'.', '']
assert before=={name:digest(SOURCE/name) for name in FILES}
lines += ['## Source integrity and checkpoint', '',
    f'Canonical source directory: `{SOURCE}`. Its six inspected files match the existing workspace mirror byte for byte. '
    'SHA-256 hashes were checked before and after inspection; no source changed. See `v2_check_evidence.json` for hashes and sample identities.', '',
    '**Stopped at CHECKPOINT 1.** No routing setup, routing scoring, fixes, or reruns performed.']
(OUT/'checkpoint1.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(OUT/'v2_check_evidence.json').write_text(json.dumps({'preregistration_commit':'0b83e2c','source_directory':str(SOURCE),
    'sha256':before,'sampling':{'seed':20261024,'population':50,'ordering':['repo','number_numeric'],'method':'random.Random(seed).sample(population,5)'},
    'v2_raw_wontfix_count':50,'v2_identical_taxonomy_block_count':50,'exclusions':[],
    'selected':evidence},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(evidence,indent=2,ensure_ascii=False))
