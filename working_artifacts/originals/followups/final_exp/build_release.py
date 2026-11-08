"""Build a portable, credential-free local release; verify full prompt/response coverage."""
import csv,hashlib,json,re,shutil,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
BOT=ROOT/'bot_test';ROUTING=ROOT/'routing_test';DEST=OUT/'release'
setup=json.loads((ROUTING/'setup_manifest.json').read_text(encoding='utf-8'))
FAIR=Path(setup['source_files']['cases']['path']).parent.parent
DESKTOP=Path(r'C:\Users\Ogtay\Desktop\test')
DL=Path(r'C:\Users\Ogtay\Downloads')
DEST.mkdir(exist_ok=True)
(DEST/'.gitattributes').write_bytes(b'* -text\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def textsha(s):return hashlib.sha256(s.encode()).hexdigest()
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='\n') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
mappings=[(str(ROOT),''),(str(DESKTOP/'bot_test'),'bot_test'),(str(DESKTOP/'routing_test'),'routing_test'),
 (str(DESKTOP/'final_exp'),'final_exp'),(str(DESKTOP/'provenance_out'),'final_exp/provenance_out'),
 (str(DESKTOP/'closure_provenance.py'),'final_exp/closure_provenance.py'),(str(DESKTOP),'final_exp'),
 (str(FAIR),'fair_run'),(str(DL/'run_haring_rrf_frozen_e2e.py'),'reference_scripts/run_haring_rrf_frozen_e2e.py'),
 (str(DL/'TOSEM_Overleaf_ready_2026-08-09.zip'),'sources/table1_paper_reference.zip')]
mappings.sort(key=lambda x:len(x[0]),reverse=True)
def portable_text(text):
    for origin,target in mappings:
        for src in [origin.replace('\\','\\\\'),origin,origin.replace('\\','/')]:
            if src in text:
                # Collapse only the following path separators. Message contents
                # are independently hash-checked below, never silently edited.
                text=text.replace(src+'\\\\',target+'/' if target else '')
                text=text.replace(src+'\\',target+'/' if target else '')
                text=text.replace(src+'/',target+'/' if target else '')
                text=text.replace(src,target or '.')
    # Unused external source references in archival scripts/manifests are made
    # explicit portable placeholders, not falsely presented as included data.
    text=re.sub(r'[A-Za-z]:[\\/]+Users[\\/]+[^\s\"\x27<>`\r\n]+',lambda m:'external_sources/'+re.split(r'[\\/]+',m.group())[-1],text)
    for prefix in ['/'+'mnt/data/','/'+'tmp/']:
        text=text.replace(prefix,'external_sources/')
    return text
inventory=[]
def copy(source,relative,transform=True):
    target=DEST/relative;target.parent.mkdir(parents=True,exist_ok=True)
    data=source.read_bytes();changed=False
    if transform and source.suffix.lower() in {'.py','.md','.txt','.json','.jsonl','.csv','.tex'}:
        text=data.decode('utf-8-sig');new=portable_text(text)
        if new!=text:
            data=new.encode('utf-8');changed=True
    target.write_bytes(data)
    inventory.append({'release_file':relative.replace('\\','/'),'source_sha256':sha(source),'release_sha256':sha(target),
                      'local_path_references_rewritten':changed})

# Preserve all scoped runs, source records, frozen patterns, and actual API ledgers.
for name in ['rq3_protocol.py','run_rq3.py','prepare_staged_native.py','import_legacy_csv.py','blind_and_score.py','lexical_checks.py','finalize_verified_evidence.py','RUBRIC_FROZEN.md','README.md','MANIFEST_SHA256.json']:
    copy(FAIR/name,'fair_run/'+name)
for name in ['real_82_native_staged.jsonl','fair_prompts_246_dryrun.jsonl','new_responses_246.jsonl','quality_review_82.csv','audit36_verification_worklist.csv','preflight_quality_report.json']:
    copy(FAIR/'private_working'/name,'fair_run/private_working/'+name)
for p in sorted((FAIR/'tests').glob('*.py')):copy(p,'fair_run/tests/'+p.name)
bot_names=['inputs.jsonl','sample.csv','sample_records.jsonl','issue_bodies.jsonl','system_prompt_exact_utf8.txt','judge_prompt_exact_utf8.txt',
 'responses_gpt-4o-mini-2024-07-18.jsonl','responses_gemma-4-26b-a4b-it.jsonl','main_responses_gemma.jsonl',
 'judgments.jsonl','judge_attempts.jsonl','attempts_A.jsonl','attempts_B.jsonl','google_transport_ledger.jsonl','request_failures.jsonl',
 'run_manifest.json','preparation_manifest.json','completion_audit.json','amendment_20261024.md','lexical.py','run_experiment.py','google_transport.py','prepare_inputs.py','build_sample.py','analyze.py']
for name in bot_names:
    p=BOT/name
    if p.exists():copy(p,'bot_test/'+name)
for name in ['routing_and_v2_check.md','case_registry.csv','exclusions.csv','input_evidence_audit.csv','input_evidence_summary.csv','lexical.py',
 'lexical_scores.jsonl','setup_manifest.json','checkpoint3_manifest.json','amendment_20261101.md','results.md',
 'provisional_routing_rates.csv','provisional_routing_paired_tests.csv','provisional_statistics.json','true_status_registry.csv',
 'uncertain_status_cases.csv','fix_claim_by_true_status.csv','fix_claim_case_scores.csv','tracker_refresh_summary.json',
 'analyze_provisional.py','prepare_routing.py','inspect_sources.py']:
    copy(ROUTING/name,'routing_test/'+name)
for p in sorted((ROUTING/'tracker_refresh_20261101').glob('*.json')):copy(p,'routing_test/tracker_refresh_20261101/'+p.name)
final_names=['final_experiments.md','meaning_lines.json','meaning_lines_supplement.md','inputs_taxonomy_only.jsonl','raw_reference_messages.jsonl',
 'generation_settings.json','system_prompt_exact_utf8.txt','preparation_manifest.json','input_integrity.csv','analysis_exclusions.json','probe_models.py',
 'judge_core_prompt.txt','judge_routing_prompt.txt','judge_audit_prompt.txt','judge_audit_routing_prompt.txt','scoring_plan.md','outcome_lexical.py','run_final.py','prepare_inputs.py',
 'prepare_audit.py','prepare_prevalence.py','collect_scores.py','build_release.py','verify_final.py','verification_final.json','audit_key.csv','audit_instructions.md','audit_manifest.json',
 'audit_judge_inputs.jsonl','audit_lexical_scores.csv','audit_auto_scores.csv','auto_scores.csv','api_usage.csv','completion_audit.json',
 'judge_core_scores.jsonl','judge_routing_scores.jsonl','judge_audit_scores.jsonl','judge_audit_routing_scores.jsonl','judge_core_attempts.jsonl','judge_routing_attempts.jsonl','judge_audit_attempts.jsonl','judge_audit_routing_attempts.jsonl',
 'generation_attempts_A.jsonl','generation_attempts_B.jsonl','responses_taxonomy_only_gpt-4o-mini-2024-07-18.jsonl','responses_taxonomy_only_gemma-4-26b-a4b-it.jsonl',
 'execution_sources.jsonl','execution_manifest.json','prevalence_sensitivity.csv','prevalence_sensitivity.md','prevalence_manifest.json','provenance_summarize.txt','table1_source_excerpt.txt']
for name in final_names:
    p=OUT/name
    if p.exists():copy(p,'final_exp/'+name)
for folder,label in [(BOT,'bot_test'),(ROUTING,'routing_test'),(OUT,'final_exp')]:
    already={r['release_file'] for r in inventory}
    for p in sorted(folder.glob('*.py')):
        relative=label+'/'+p.name
        if relative not in already:copy(p,relative)
for p in sorted((OUT/'scripts').glob('*.py')):copy(p,'final_exp/scripts/'+p.name)
copy(OUT/'scripts/closure_provenance.py','final_exp/closure_provenance.py')
for p in sorted((OUT/'provenance_out').glob('*')):
    if p.is_file():copy(p,'final_exp/provenance_out/'+p.name)
copy(DL/'run_haring_rrf_frozen_e2e.py','reference_scripts/run_haring_rrf_frozen_e2e.py')
copy(DL/'TOSEM_Overleaf_ready_2026-08-09.zip','sources/table1_paper_reference.zip',False)

# Blank template in release; never overwrite or clear the user's working sheet.
with (OUT/'audit_sheet.csv').open(encoding='utf-8-sig',newline='') as f:sheet=list(csv.DictReader(f))
for r in sheet:
    for q in ['NO_FALSE_FIX','STATES_OUTCOME','notes']:r[q]=''
    for q in ['ASKS_DETAILS','SAYS_DUPLICATE']:
        if r[q]!='NA':r[q]=''
with (DEST/'final_exp/audit_sheet.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(sheet[0]));w.writeheader();w.writerows(sheet)
assert sha(DEST/'final_exp/audit_sheet.csv')==load(OUT/'audit_manifest.json')['sheet_sha256_before_labels']

# Canonical complete prompt/response index, independent of provider envelopes.
messages={};responses=[]
def add_input(key,msgs):
    h=textsha(json.dumps(msgs,sort_keys=True,ensure_ascii=False))
    if key in messages:assert messages[key]['messages_sha256']==h
    messages[key]={'input_key':key,'messages':msgs,'messages_sha256':h}
def add_response(dataset,cid,arm,r,model,source):
    key=f'{dataset}:{cid}:{arm}';assert key in messages
    assert r['messages_sha256']==messages[key]['messages_sha256'],f'Response/input mismatch: {key}'
    response=r['response'];rs=textsha(response)
    excluded=dataset=='fair' and cid=='fdb3e658e38d05422ec9cd14d85214590bc61d1b87394fc6d434493865fcfa97'
    responses.append({'response_key':model+':'+key,'input_key':key,'dataset':dataset,'case_id':cid,'arm':arm,'model':model,
       'response':response,'response_sha256':rs,'excluded_from_all_analyses':excluded,'source_file':source,'source_record':r})
system=(OUT/'system_prompt_exact_utf8.txt').read_bytes().decode('utf-8')
for r in read(FAIR/'private_working/fair_prompts_246_dryrun.jsonl'):add_input('fair:'+r['case_id']+':'+r['arm'],r['messages'])
for r in read(BOT/'inputs.jsonl'):add_input(f"bot_test:{r['repo']}#{r['number']}:{r['arm']}",[{'role':'system','content':system},{'role':'user','content':r['user_message']}])
for r in read(OUT/'inputs_taxonomy_only.jsonl'):add_input(r['dataset']+':'+r['case_id']+':TAXONOMY-ONLY',r['messages'])
for r in read(FAIR/'private_working/new_responses_246.jsonl'):add_response('fair',r['case_id'],r['arm'],r,'gpt-4o-mini-2024-07-18','fair_run/private_working/new_responses_246.jsonl')
for r in read(BOT/'main_responses_gemma.jsonl'):add_response('fair',r['case_id'],r['arm'],r,'gemma-4-26b-a4b-it','bot_test/main_responses_gemma.jsonl')
for model in ['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']:
    for r in read(BOT/f'responses_{model}.jsonl'):add_response('bot_test',f"{r['repo']}#{r['number']}",r['arm'],r,model,'bot_test/responses_'+model+'.jsonl')
    for r in read(OUT/f'responses_taxonomy_only_{model}.jsonl'):add_response(r['dataset'],r['case_id'],r['arm'],r,model,'final_exp/responses_taxonomy_only_'+model+'.jsonl')
assert len(messages)==728 and len(responses)==len({r['response_key'] for r in responses})==1456
assert sum(r['excluded_from_all_analyses'] for r in responses)==8
jsonl(DEST/'data/messages_all.jsonl',[messages[k] for k in sorted(messages)])
jsonl(DEST/'data/responses_all.jsonl',sorted(responses,key=lambda r:r['response_key']))
for r in read(DEST/'data/messages_all.jsonl'):assert textsha(json.dumps(r['messages'],sort_keys=True,ensure_ascii=False))==r['messages_sha256']
for r in read(DEST/'data/responses_all.jsonl'):assert textsha(r['response'])==r['response_sha256']

with (DEST/'SOURCE_INVENTORY.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
verification='''"""Verify release hashes and full response/prompt coverage without any API calls."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
for name,h in manifest.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h,name
def rows(name):return [json.loads(s) for s in (root/name).read_text(encoding='utf-8').splitlines() if s.strip()]
m=rows('data/messages_all.jsonl');r=rows('data/responses_all.jsonl')
assert len(m)==728 and len(r)==1456
assert len({x['input_key'] for x in m})==728
assert len({x['response_key'] for x in r})==1456
for x in m:assert hashlib.sha256(json.dumps(x['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()==x['messages_sha256']
for x in r:assert hashlib.sha256(x['response'].encode()).hexdigest()==x['response_sha256']
print('Verified every release hash, 728 exported message sets, and 1456 exported responses. Original hashes are retained where profile paths were deidentified.')
'''
(DEST/'verify_release.py').write_text(verification,encoding='utf-8')
coverage={'unique_message_sets':728,'final_responses':1456,'fair_original_responses':492,'bot_original_responses':640,
 'taxonomy_only_responses':324,'original_judgments':1132,'new_core_judgments':324,'new_routing_judgments':324,'new_audit_judgments':140,
 'audit_routing_judgments':140,'audit_routing_identical_text_reuse':35,'audit_routing_additional_calls':105,
 'excluded_2131_response_records':8,'human_audit_template_rows':140,'human_labels':'pending; release contains the blank template',
 'failed_attempts':'Retained in attempt ledgers; excluded from canonical final-response index with finish_reason preserved.',
 'scope':'Fair shared-prompt RQ3, bot-closure experiment, routing checks, and TAXONOMY-ONLY follow-up. Older unequal-prompt manuscript runs are outside this scoped release.'}
(DEST/'COVERAGE.json').write_text(json.dumps(coverage,indent=2)+'\n',encoding='utf-8')
readme=['# TOSEM closure experiments — local review release','',
 'Human audit labels are pending. This package contains the scoped fair RQ3 run, both original bot-test generators, '
 'the routing checks, and the TAXONOMY-ONLY follow-up. It is prepared locally for review; nothing has been published.', '',
 '**Coverage:** 728 exact system/user message sets and 1,456 final responses: 492 fair original responses, '
 '640 original bot-test responses, and 324 TAXONOMY-ONLY responses. All requested automated scores and raw '
 'attempt/judge ledgers are included. Incomplete historical attempts remain in ledgers and are not represented '
 'as successful final responses. COVERAGE.json states the scope and exclusions.', '',
 'Nextcloud #2131 is retained as generated but excluded from every analysis (eight response records across '
 'the fair original and TAXONOMY-ONLY conditions). It was fixed by merged PR #4470; its received taxonomy '
 'label was not repaired retrospectively. Tracker evidence, not taxonomy class, is the correctness reference.', '',
 '## Verification and use','',
 'Run `python verify_release.py` from this directory. This checks every file hash plus the original prompt '
 'and response hashes without API calls. `data/messages_all.jsonl` and `data/responses_all.jsonl` provide '
 'one canonical index across all runs; provider envelopes remain in the individual run files.', '',
 'Use `final_exp/audit_sheet.csv` as a blank template only; the working human sheet remains outside the '
 'release. The package deliberately contains no partial human labels. Do not inspect audit keys or automated '
 'scores while labeling. Arm masking does not erase prior knowledge of aggregate results.', '',
 'The final runner uses only OPENAI_API_KEY and GEMINI_API_KEY environment variables. No credentials are '
 'bundled. Run `python final_exp/run_final.py --help` for stages. Generation requires provider access and '
 'uses the exact stored prompts/settings. Outputs are resumable. Do not regenerate a scientific result '
 'into these frozen files; make a separate working copy for a new run.', '',
 'All machine-specific source paths have been replaced with portable relative references in exported copies. '
 'SOURCE_INVENTORY.csv retains original and exported hashes for traceability. Absolute personal-profile '
 'prefixes quoted in tracker logs/titles are deidentified in exported copies only. The original experiment '
 'files remain unchanged outside this release. Original text hashes are retained alongside new exported '
 'hashes; regeneration from the deidentified export is not an exact-text replay for affected inputs. '
 'Archival helper scripts are supplied '
 'for provenance; some earlier source-verification workflows refer to optional external sources that are '
 'not part of this scoped package. Historical source-freeze manifests describe their original run, so the '
 'release-wide manifest and canonical text hashes are authoritative for this export.', '',
 'The code and paper are not modified at their original locations. Metadata caveats (reconstructed '
 'tracker fields, truncated legacy body excerpts, missing URLs, and bounded provenance timelines) remain '
 'documented in source reports. The Table 1 reference archive is included to identify the exact comparison '
 'snapshot, not as an edited manuscript. The complete provenance scans belong to the recorded snapshot; '
 'V1/V2 differences are sensitivity results, not human-adjudicated gold.', '',
 'No primary human-label rates, two-test Holm family, or agreement kappas have been substituted with '
 'automated labels. Those analyses wait for the completed audit sheet.', '', '## File inventory','']
paths=sorted(p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file() and p.name not in ['README.md','MANIFEST_SHA256.json'])
readme += ['- `'+p+'`' for p in paths]+['- `README.md`','- `MANIFEST_SHA256.json`','']
(DEST/'README.md').write_text('\n'.join(readme),encoding='utf-8')

# The user requires no local paths in the release. Third-party issue logs also
# contain personal profile prefixes. Deidentify only exported copies, retaining
# original content hashes and independently hashing the exported text.
profile=re.compile(r'(?<![A-Za-z0-9.])/(?:Users|home)/[^/\s\"\x27]+/|[A-Za-z]:[\\/]+(?i:Users)[\\/]+[^\\/\s\"\x27]+[\\/]+')
redacted_files=[]
def repair_hashes(obj):
    if isinstance(obj,list):return [repair_hashes(v) for v in obj]
    if not isinstance(obj,dict):return obj
    obj={k:repair_hashes(v) for k,v in obj.items()}
    if isinstance(obj.get('messages'),list) and 'messages_sha256' in obj:
        new=textsha(json.dumps(obj['messages'],sort_keys=True,ensure_ascii=False))
        if new!=obj['messages_sha256']:
            obj['original_messages_sha256']=obj['messages_sha256'];obj['messages_sha256']=new
    for content,field in [('response','response_sha256'),('user_message','user_message_sha256')]:
        if isinstance(obj.get(content),str) and field in obj:
            new=textsha(obj[content])
            if new!=obj[field]:obj['original_'+field]=obj[field];obj[field]=new
    return obj
for p in sorted(DEST.rglob('*')):
    if not p.is_file() or p.suffix.lower()=='.zip':continue
    raw=p.read_bytes();text=raw.decode('utf-8-sig')
    clean,count=profile.subn('[LOCAL_PROFILE]/',text)
    if not count:continue
    redacted_files.append({'file':p.relative_to(DEST).as_posix(),'profile_prefixes_redacted':count})
    if p.suffix=='.jsonl':
        rows=[repair_hashes(json.loads(s)) for s in clean.splitlines() if s.strip()]
        jsonl(p,rows)
    elif p.suffix=='.json':p.write_text(json.dumps(repair_hashes(json.loads(clean)),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    else:p.write_bytes(clean.encode('utf-8'))
exported_messages=read(DEST/'data/messages_all.jsonl');exported_responses=read(DEST/'data/responses_all.jsonl')
changed_messages=sum('original_messages_sha256' in r for r in exported_messages)
changed_responses=sum('original_response_sha256' in r for r in exported_responses)
for r in exported_messages:assert textsha(json.dumps(r['messages'],sort_keys=True,ensure_ascii=False))==r['messages_sha256']
for r in exported_responses:assert textsha(r['response'])==r['response_sha256']
export_prep=load(DEST/'final_exp/preparation_manifest.json')
export_prep['original_outputs_sha256']=export_prep['outputs_sha256'].copy()
for name in ['inputs_taxonomy_only.jsonl','generation_settings.json','system_prompt_exact_utf8.txt']:
    export_prep['outputs_sha256'][name]=sha(DEST/'final_exp'/name)
export_prep['release_profile_path_deidentification']=True
(DEST/'final_exp/preparation_manifest.json').write_text(json.dumps(export_prep,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
for item in inventory:item['release_sha256']=sha(DEST/item['release_file'])
with (DEST/'SOURCE_INVENTORY.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
deid={'scope':'Exported copies only; original prompts, responses, and scans are unchanged.',
 'canonical_message_sets_with_deidentified_profile_prefixes':changed_messages,
 'canonical_response_texts_with_deidentified_profile_prefixes':changed_responses,'files':redacted_files,
 'hash_policy':'Original text hashes retained as original_*_sha256; exported text gets its own verified hash.'}
(DEST/'DEIDENTIFICATION.json').write_text(json.dumps(deid,indent=2)+'\n',encoding='utf-8')
with (DEST/'README.md').open('a',encoding='utf-8') as f:
    f.write(f'\n- `DEIDENTIFICATION.json`: profile-prefix replacements affect {changed_messages} canonical message sets and {changed_responses} response texts. Original experiment files are unchanged.\n')

# Check every exported text and compressed text member for credentials/host paths.
secrets=re.compile(r'(?:sk-proj-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\bAIza[A-Za-z0-9_-]{25,}|\bAQ\.[A-Za-z0-9_-]{25,})')
hostpath=re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+|/'+r'Users/|/'+r'home/[^/\s]+/|/'+r'mnt/data/|/'+r'tmp/')
violations=[]
def check(text,label):
    if secrets.search(text):violations.append(label+': credential-like value')
    if hostpath.search(text):violations.append(label+': absolute local path')
for p in DEST.rglob('*'):
    if not p.is_file():continue
    if p.suffix.lower()=='.zip':
        with zipfile.ZipFile(p) as z:
            for member in z.namelist():
                if Path(member).suffix.lower() in ['.tex','.txt','.json','.csv','.py','.md','.xml']:check(z.read(member).decode('utf-8',errors='replace'),p.name+'!'+member)
    else:
        check(p.read_text(encoding='utf-8-sig',errors='replace'),p.relative_to(DEST).as_posix())
assert not violations,'Release scan failed: '+json.dumps(violations)
hashes={p.relative_to(DEST).as_posix():sha(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
(DEST/'MANIFEST_SHA256.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
report={'files':len(hashes)+1,'message_sets':728,'responses':1456,'credential_scan':'passed','local_path_scan':'passed',
    'exported_prompt_hashes':'passed','exported_response_hashes':'passed','original_hashes_retained':True,
    'deidentified_message_sets':changed_messages,'deidentified_response_texts':changed_responses,'human_labels_pending':True,
    'manifest_sha256':sha(DEST/'MANIFEST_SHA256.json')}
(OUT/'release_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
