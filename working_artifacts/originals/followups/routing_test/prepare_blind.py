"""Prepare arm-masked annotation sheets; freeze secondary scores without summaries."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import random
import sys

sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
import lexical
OUT=Path(__file__).resolve().parent
SEED=20261024
FROZEN_COMMIT='e163e4403204df517551eb9320b873862994252d'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def writecsv(p,rows,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
setup=json.loads((OUT/'setup_manifest.json').read_text(encoding='utf-8'))
for info in setup['source_files'].values():
    assert sha(Path(info['path']))==info['sha256'],f"Source changed: {info['path']}"
registry=csvread(OUT/'case_registry.csv')
targets={r['case_id']:r for r in registry if r['included_routing']=='True'}
assert collections.Counter(r['cohort'] for r in targets.values())=={'NEEDS_INFO':16,'REDIRECTED':7}
arms={'binary_state','raw_metadata','closure_aware'}
expected={(cid,a) for cid in targets for a in arms}
source_paths={name:Path(setup['source_files'][name]['path']) for name in ['fair_responses','gemma_responses']}
sources=[('GPT-4o-mini','fair_responses','blind_sheet.csv','blind_key.csv',SEED),
         ('Gemma','gemma_responses','gemma_blind_sheet.csv','gemma_blind_key.csv',SEED+1)]
fields=['blind_id','response','ASKS_DETAILS','SAYS_DUPLICATE','GIVES_CANONICAL','notes']
allids=set();scores=[];details=[]
# Independent checks exercise the endpoint distinctions, not the real outcomes.
checks=[
 ('Please share your logs and app version.',True,False),
 ('Could you provide steps to reproduce this?',True,False),
 ('Please add more details to the issue.',True,False),
 ('Let us know if you have any questions.',False,False),
 ('The report already contains device details and logs.',False,False),
 ('Do not send logs.',False,False),
 ('This is a duplicate.',False,True),
 ('This is not a duplicate.',False,False),
 ('The issue is tracked elsewhere.',False,True),
 ('The problem is tracked in issue #234.',False,True),
 ('The problem is tracked in issue #123.',False,False),
]
for text,ask,duplicate in checks:
    actual=lexical.score(text,'123')
    assert (actual['ASKS_DETAILS'],actual['SAYS_DUPLICATE'])==(ask,duplicate),(text,actual)
    assert actual['GIVES_CANONICAL'] is None
for model,source,sheet_name,key_name,seed in sources:
    sheet_path=OUT/sheet_name;key_path=OUT/key_name
    assert not sheet_path.exists() and not key_path.exists(),'Refusing to overwrite an existing annotation sheet or key'
    records=read(source_paths[source])
    chosen=sorted([r for r in records if r['case_id'] in targets],key=lambda r:(r['case_id'],r['arm']))
    assert len(chosen)==69 and {(r['case_id'],r['arm']) for r in chosen}==expected
    rng=random.Random(seed);rng.shuffle(chosen)
    sheets=[];keys=[]
    for r in chosen:
        row=targets[r['case_id']]
        blind_id=f'R{rng.getrandbits(40):010X}'
        assert blind_id not in allids;allids.add(blind_id)
        response=r['response']
        response_hash=hashlib.sha256(response.encode('utf-8')).hexdigest()
        sheets.append({'blind_id':blind_id,'response':response,'ASKS_DETAILS':'','SAYS_DUPLICATE':'','GIVES_CANONICAL':'','notes':''})
        keys.append({'blind_id':blind_id,'model':model,'case_id':r['case_id'],'arm':r['arm'],
                     'cohort':row['cohort'],'repository':row['repository'],'issue_number':row['issue_number'],
                     'response_sha256':response_hash,'messages_sha256':r['messages_sha256'],
                     'source_file':str(source_paths[source]),'canonical_target_available':False})
        secondary=lexical.score(response,row['issue_number'],canonical_target=None)
        scores.append({'blind_id':blind_id,'model':model,'case_id':r['case_id'],'arm':r['arm'],
                       'cohort':row['cohort'],'response_sha256':response_hash,'lexical_version':lexical.VERSION,
                       'lexical':secondary,'primary_endpoint_applicability':{
                           'ASKS_DETAILS':row['cohort']=='NEEDS_INFO','SAYS_DUPLICATE':row['cohort']=='REDIRECTED',
                           'GIVES_CANONICAL':'descriptive_only; canonical target unavailable'}})
    writecsv(sheet_path,sheets,fields)
    writecsv(key_path,keys,list(keys[0]))
    reread=csvread(sheet_path)
    assert len(reread)==69 and list(reread[0])==fields
    assert all(all(r[q]=='' for q in ['ASKS_DETAILS','SAYS_DUPLICATE','GIVES_CANONICAL','notes']) for r in reread)
    assert all(r['response']==s['response'] for r,s in zip(reread,sheets))
    assert {r['blind_id'] for r in reread}=={r['blind_id'] for r in keys}
    assert collections.Counter(r['arm'] for r in keys)==dict.fromkeys(arms,23)
    assert collections.Counter(r['cohort'] for r in keys)=={'NEEDS_INFO':48,'REDIRECTED':21}
    details.append({'model':model,'rows':69,'unique_cases':23,'responses_per_arm':23,
        'NEEDS_INFO_rows':48,'REDIRECTED_rows':21,'shuffle_seed':seed,
        'blind_sheet':sheet_name,'key':key_name,'sheet_sha256_before_annotation':sha(sheet_path),'key_sha256':sha(key_path)})
with (OUT/'lexical_scores.jsonl').open('w',encoding='utf-8',newline='\n') as f:
    for row in scores:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
instructions='''# Routing annotation — Checkpoint 3

Label the two response sheets: `blind_sheet.csv` (GPT-4o-mini) and `gemma_blind_sheet.csv` (Gemma).
Each contains all 69 responses: 23 cases × three arms. Rows are independently shuffled and arm names are removed.
Use the sheets in this directory as the working copies. Keep the `blind_id` and `response` cells unchanged.
Save the labeled sheets as CSV in the same location when finished.

Do not open `blind_key.csv`, `gemma_blind_key.csv`, or `lexical_scores.jsonl` while annotating. These disclose conditions or secondary scores.
The response text is preserved exactly, including any citations. Blinding hides metadata, but wording can still suggest a condition.

Fill ASKS_DETAILS and SAYS_DUPLICATE as 1 (yes) or 0 (no) for every response. Judge only what the response says.
The hidden key will restrict each endpoint to its relevant case cohort in the later analysis.
Use U only if you genuinely cannot decide, and explain in notes. U is missing/uncertain, never a silent 0.

- **ASKS_DETAILS:** The response asks the user for specific missing information (steps to reproduce, logs, app version, device) or to add details to the issue. “Let us know if you have any questions” does not count. Merely mentioning diagnostic information without requesting it does not count.
- **SAYS_DUPLICATE:** The response says the problem is tracked in another issue or is a duplicate. Merely citing the retrieved issue does not establish another issue.
- **GIVES_CANONICAL:** SAYS_DUPLICATE, plus the canonical issue number or link. Step 2 found no supplied canonical target for these cases. Therefore this endpoint is descriptive only, and canonical correctness cannot be determined from these sheets. Enter U when the target cannot be established; use notes to record any apparent different-issue reference. Do not treat a citation to the retrieved issue itself as a canonical duplicate target.

The three label columns are deliberately blank initially. Your labels are primary; frozen lexical checks are secondary.
Do not use taxonomy class labels to decide whether a response is correct. This pass codes response behavior.
No outcomes or comparisons will be reported before your labels are available.

The source registry accounts for all 82 cases. The 59 cases outside NEEDS_INFO/REDIRECTED remain individually listed in `exclusions.csv`.
No routing case or response was excluded because of its text, length, or lexical score.

Lexical patterns were committed before scoring in `e163e4403204df517551eb9320b873862994252d`.
An earlier draft matched “The report already contains device details and logs” as a request. A synthetic check caught that noun/verb false positive, which was corrected and recommitted before any real response was scored.
GIVES_CANONICAL lexical values are null (unavailable), never assumed false; candidate references are retained separately.
No new model calls were made.

**Stopped at CHECKPOINT 3.** Label both sheets, then tell me when they are ready. Analysis and the true-status FIX_CLAIM split remain pending.
'''
(OUT/'annotation_instructions.md').write_text(instructions,encoding='utf-8')
for info in setup['source_files'].values():assert sha(Path(info['path']))==info['sha256']
manifest={'checkpoint':3,'lexical_commit':FROZEN_COMMIT,'lexical_version':lexical.VERSION,
    'lexical_sha256':sha(OUT/'lexical.py'),'lexical_freeze_precedes_scoring':True,'no_model_calls':True,
    'sheets':details,'total_blind_rows':138,'total_lexical_records':len(scores),
    'lexical_scores_sha256':sha(OUT/'lexical_scores.jsonl'),'unique_blind_ids':len(allids),
    'all_primary_annotation_cells_initially_blank':True,'all_sources_unchanged':True,
    'exclusions':'59 cases listed in exclusions.csv; zero exclusions among the 23 routing cases',
    'canonical_test_eligible':False,'canonical_gold_target_available':False,
    'analysis_status':'Waiting for human labels; no outcome summaries or statistical tests performed'}
(OUT/'checkpoint3_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Prepared two sheets of 69 rows each; 138 unique blind IDs, empty labels, 138 frozen secondary records. Sources unchanged.')
