"""Checkpoint 2: inspect existing input evidence and cohort sources, never score responses."""
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
from inspect_sources import xlsx_rows
OUT=Path(__file__).resolve().parent
DL=Path(r'C:\Users\Ogtay\Downloads')
KIT=DL/'TOSEM_RQ3_Run/tosem_rq3_fair'
PRIVATE=KIT/'private_working'
BOT=OUT.parent/'bot_test'
ARMS=('binary_state','raw_metadata','closure_aware')
SOURCES={
    'cases':PRIVATE/'real_82_native_staged.jsonl',
    'fair_responses':PRIVATE/'new_responses_246.jsonl',
    'fair_saved_inputs':PRIVATE/'fair_prompts_246_dryrun.jsonl',
    'protocol':KIT/'rq3_protocol.py',
    'quality_review':PRIVATE/'quality_review_82.csv',
    'audit_worklist':PRIVATE/'audit36_verification_worklist.csv',
    'preflight':PRIVATE/'preflight_quality_report.json',
    'staging_code':KIT/'prepare_staged_native.py',
    'historical_diagnostic':DL/'haring_rrf_final_diagnostic_20260808/nonresolved_36_case_diagnostic.csv',
    'human_taxonomy':Path(r'C:\Users\Ogtay\Desktop\test\taxonomy_annotation_pack_FORMATTED.xlsx'),
    'human_taxonomy_copy':DL/'taxonomy_annotation_pack_FORMATTED (1).xlsx',
    'second_annotator':DL/'closure_taxonomy_second_annotator_pack.xlsx',
    'human_status_72':DL/'blinded_status_annotation_72_FORMATTED.xlsx',
    'paper_archive':DL/'TOSEM_Overleaf_ready_2026-08-09.zip',
    'gemma_responses':BOT/'main_responses_gemma.jsonl',
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before={name:sha(p) for name,p in SOURCES.items()}
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def csvwrite(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,data): (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('frozen_rq3_protocol',SOURCES['protocol'])
protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
cases=read(SOURCES['cases']);byid={r['case_id']:r for r in cases}
assert len(cases)==len(byid)==82
protocol.validate(cases)
inputs=read(SOURCES['fair_saved_inputs']);prompts={(r['case_id'],r['arm']):r for r in inputs}
expected={(c['case_id'],a) for c in cases for a in ARMS}
assert len(inputs)==len(prompts)==246 and set(prompts)==expected
for (cid,arm),r in prompts.items():
    assert r['messages']==protocol.render(byid[cid],arm)
# Use the original generator's exact serialization to authenticate prompts.
def message_hash(messages):return hashlib.sha256(json.dumps(messages,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
# The generator uses separators with spaces (json.dumps default).
for r in inputs:assert message_hash(r['messages'])==r['messages_sha256']
for model,name in [('gpt-4o-mini','fair_responses'),('gemma','gemma_responses')]:
    records=read(SOURCES[name]);indexed={(r['case_id'],r['arm']):r for r in records}
    assert len(records)==len(indexed)==246 and set(indexed)==expected
    for k,r in indexed.items():
        assert r['messages_sha256']==prompts[k]['messages_sha256']
        assert r['finish_reason']=='stop' and r['response'].strip()

# Human taxonomy assignments are keyed by app/repository AND issue number.
human=[]
for name in ['human_taxonomy','human_taxonomy_copy']:
    for sheet,rows in xlsx_rows(SOURCES[name]):
        if sheet!='Annotation':continue
        for row in rows[1:]:
            cells={re.sub(r'\d','',k):v for k,v in row.items()}
            human.append({'app':cells.get('D',''),'number':cells.get('E',''),
                          'l1':cells.get('A',''),'subtype':cells.get('B',''),'source':str(SOURCES[name])})
def app(r):
    return 'Firefox' if 'Bugzilla' in r['repository'] else 'Nextcloud' if 'nextcloud' in r['repository'] else 'VLC'
human_bykey=collections.defaultdict(list)
for h in human:human_bykey[h['app'].lower(),h['number']].append(h)
qa={r['case_id']:r for r in csvread(SOURCES['quality_review'])}
assert all(not r['verified_against_source'].strip() and not r['neutral_reference_evidence'].strip() for r in qa.values())
diagnostic=csvread(SOURCES['historical_diagnostic'])
assert {r['pair_key'] for r in diagnostic}=={r['case_id'] for r in cases if protocol.audit(r)}
registry=[]
for c in sorted(cases,key=lambda r:r['case_id']):
    hits=human_bykey.get((app(c).lower(),c['display_issue_id']),[])
    assert not hits,'Unexpected human class overlap requires explicit adjudication'
    needs=c['binary_state']=='closed' and c['subtype']=='NEEDS_INFO'
    dup=c['binary_state']=='closed' and c['l1_class']=='REDIRECTED'
    cohort='NEEDS_INFO' if needs else 'REDIRECTED' if dup else ''
    reason='' if cohort else 'OPEN: outside closed routing cohorts' if c['binary_state']=='open' else f"Outside routing cohorts: {c['l1_class']}/{c['subtype']}"
    registry.append({'case_id':c['case_id'],'app':app(c),'repository':c['repository'],'issue_number':c['display_issue_id'],
                     'original_display_issue_id':c['original_display_issue_id'],'issue_url':c['issue_url'],
                     'binary_state':c['binary_state'],'selected_l1_class':c['l1_class'],'selected_subtype':c['subtype'],
                     'class_source':'taxonomy_arm_input_fallback','human_class_match':False,
                     'class_source_file':str(SOURCES['cases']),'cohort':cohort,'included_routing':bool(cohort),
                     'routing_exclusion_reason':reason,'nonresolved_taxonomy_cohort':protocol.audit(c),
                     'qa_flags':qa[c['case_id']]['qa_flags'],'source_verification':c['data_provenance_status'],
                     'raw_closure_evidence':json.dumps(c['raw_tracker_fields'],ensure_ascii=False,sort_keys=True)})
csvwrite('case_registry.csv',registry)
csvwrite('exclusions.csv',[r for r in registry if not r['included_routing']])
registry_byid={r['case_id']:r for r in registry}

# Input availability audit only. Generic conditional system instructions do not
# establish a case-specific outcome. WORKSFORME is a cannot-reproduce proxy,
# not proof of missing reporter information or a tracker-verified gold label.
audit=[]
for c in cases:
    raw=c['raw_tracker_fields'];resolution=str(raw.get('resolution','')).lower()
    labels=raw.get('labels',[])
    missing_lines=[f'- resolution: {raw["resolution"]}'] if resolution in {'incomplete','worksforme'} else []
    if any(re.search(r'needs? info|cannot.reproduce|can.t.reproduce',str(l),re.I) for l in labels):
        missing_lines.append('- labels: '+json.dumps(labels,ensure_ascii=False,sort_keys=True))
    duplicate_lines=[f'- resolution: {raw["resolution"]}'] if resolution=='duplicate' else []
    common=protocol.render(c,'binary_state')[1]['content']
    # Record incomplete issue templates separately from evidence of closure reason.
    blanks=re.findall(r'(?im)^(Android version|Device model|Nextcloud app version|Nextcloud server version):[^\S\r\n]*\r?$',common)
    for arm in ARMS:
        user=prompts[c['case_id'],arm]['messages'][1]['content']
        need=[s for s in missing_lines if s in user]
        dup=[s for s in duplicate_lines if s in user]
        if arm=='closure_aware' and c['subtype']=='NEEDS_INFO':need.append('- subtype: NEEDS_INFO')
        if arm=='closure_aware' and c['l1_class']=='REDIRECTED':dup.append('- l1_class: REDIRECTED')
        # A literal mention of duplicate in a user complaint is not a tracker
        # assertion that the retrieved issue was closed as a duplicate.
        literal_common=bool(re.search(r'\bduplicate\b',common,re.I))
        audit.append({'case_id':c['case_id'],'app':app(c),'issue_number':c['display_issue_id'],
                      'cohort':registry_byid[c['case_id']]['cohort'],'arm':arm,
                      'missing_info_or_cannot_reproduce_closure_signal':bool(need),
                      'missing_info_signal_quotes':'\n'.join(need),
                      'duplicate_closure_signal':bool(dup),'duplicate_signal_quotes':'\n'.join(dup),
                      'incomplete_template_fields_hint':'; '.join(blanks),
                      'duplicate_word_in_common_review_or_body':literal_common,
                      'canonical_duplicate_target_present':False,'canonical_target_number_or_url':'',
                      'canonical_audit_status':'Inspected full user input: no duplicate target supplied' if c['l1_class']=='REDIRECTED' else 'No supplied duplicate-target field or affirmative target statement; not a REDIRECTED test case',
                      'generic_system_needs_info_instruction':True,'generic_system_duplicate_instruction':True,
                      'messages_sha256':prompts[c['case_id'],arm]['messages_sha256']})
csvwrite('input_evidence_audit.csv',audit)
with (OUT/'fair_inputs_snapshot.jsonl').open('w',encoding='utf-8',newline='\n') as f:
    for r in sorted(inputs,key=lambda r:(r['case_id'],r['arm'])):f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')

counts=collections.Counter((r['selected_l1_class'],r['selected_subtype']) for r in registry)
cohorts=collections.Counter(r['cohort'] for r in registry if r['cohort'])
unknown=[r for r in registry if 'UNKNOWN_CLOSING_REASON' in r['qa_flags']]
assert len(unknown)==2 and cohorts=={'NEEDS_INFO':16,'REDIRECTED':7}
csvwrite('nonresolved_34_vs_36.csv',[dict(r,old_export_closure_signal=qa[r['case_id']]['signal_from_old_export'],
    reconciliation='Included in taxonomy-defined 36; cannot establish true non-resolution from retained closure evidence') for r in unknown])
summaries=[]
for cohort in ['ALL','NEEDS_INFO','REDIRECTED']:
    for arm in ARMS:
        rows=[r for r in audit if r['arm']==arm and (cohort=='ALL' or r['cohort']==cohort)]
        summaries.append({'cohort':cohort,'arm':arm,'cases':len(rows),
            'missing_info_or_cannot_reproduce_closure_signal':sum(r['missing_info_or_cannot_reproduce_closure_signal'] for r in rows),
            'duplicate_closure_signal':sum(r['duplicate_closure_signal'] for r in rows),
            'incomplete_template_fields_hint':sum(bool(r['incomplete_template_fields_hint']) for r in rows),
            'canonical_duplicate_target_present':sum(r['canonical_duplicate_target_present'] for r in rows)})
csvwrite('input_evidence_summary.csv',summaries)
with zipfile.ZipFile(SOURCES['paper_archive']) as z:
    paper=z.read('main.tex').decode('utf-8').splitlines()
paper_excerpt='\n'.join(f'{i+1}: {paper[i]}' for i in range(1223,1284))
(OUT/'paper_routing_excerpt.txt').write_text(paper_excerpt+'\n',encoding='utf-8')
lines=['# Fair routing setup — Checkpoint 2','',
    'Existing outputs and inputs only. No response scoring or new generation. All 82 cases are accounted for.', '',
    '## Files and matching','',
    *[f'- {name}: `{SOURCES[name]}`' for name in ['fair_responses','cases','fair_saved_inputs','protocol','gemma_responses']], '',
    'The saved 246 message records exactly match the original renderer applied to the 82 staged cases. '
    'All 246 prompt hashes match both the GPT-4o-mini fair responses and the Gemma main rerun. '
    'Both models have one complete response for every case/arm pair. The shared system prompt is identical in all arms. '
    'A full input snapshot is in `fair_inputs_snapshot.jsonl`; source hashes are in `setup_manifest.json`.', '',
    '## Class source for all 82 cases','',
    '`case_registry.csv` lists every case, selected class/subtype, source, cohort membership, and exclusions. '
    'All 82 use the class supplied to the taxonomy arm, explicitly flagged `taxonomy_arm_input_fallback`. '
    'These labels select routing cohorts only. They are not correctness ground truth or proof of true fix status.', '',
    'The completed taxonomy workbook has 120 assignments (70 AnkiDroid, 50 Signal), with zero matching fair-run issues. '
    'Its downloaded copy has the same coverage. The independent second-annotator fields are blank. '
    'The completed 72-row status workbook labels earlier generated responses for status correctness; '
    'its expected class column is prefilled, not a new human class adjudication. It cannot supply independently corrected classes for this step. '
    'The fair-run 82-row quality worklist has blank verification/reference columns. See `annotation_inventory.json`.', '',
    '| Class | Subtype | Cases |','|---|---|---:|',
    *[f'| {a} | {b} | {n} |' for (a,b),n in sorted(counts.items())], '',
    '## Routing populations and exclusions','',
    '**NEEDS_INFO: 16. REDIRECTED: 7. Both equal the paper’s denominators.** '
    'The original final-RRF 36-case diagnostic contains the same 36 audit case IDs. '
    'These are 23 case-response pairs per arm, 69 responses per model for the prospective blind sheets.', '',
    'The other 59 cases remain in the registry and appear individually in `exclusions.csv`: '
    '35 RESOLVED/fixed, 11 OPEN, 6 REJECTED, 5 ABANDONED/STALE, and 2 ABANDONED/OTHER. '
    'Their reason is outside the two routing cohorts. None was excluded because of its generated response.', '',
    'The 16 NEEDS_INFO inputs have eight WORKSFORME/worksforme resolutions, four INCOMPLETE/incomplete resolutions, '
    'and four Nextcloud `needs info/discussion` labels. WORKSFORME is treated here as a cannot-reproduce signal, '
    'as grouped by the supplied cohort definition, not as proof that the reporter failed to provide details. '
    'The original case source remains marked reconstructed and unverified.', '',
    '## Reconciling 34 and 36','',
    'The fair input file, original validation rule, saved audit flags, historical diagnostic, and paper all retain '
    '**36 taxonomy-defined closed non-resolved cases** (23 ABANDONED + 7 REDIRECTED + 6 REJECTED). '
    'There is no missing response or missing case in the fair run.', '',
    'A 34-case set results if the two ABANDONED/OTHER fallbacks are excluded: '
    '**Nextcloud #3425** (`87831fab6bcb4385370984002df5fd01c47237340bab72d52d0ffc1be943515d`) and '
    '**Nextcloud #2131** (`fdb3e658e38d05422ec9cd14d85214590bc61d1b87394fc6d434493865fcfa97`). '
    'Their archived closure signal says GitHub enrichment failed with API 403/rate limit and no confirmed resolution. '
    'They have only closed state and ordinary bug/feature labels in the retained input. The staging code marks '
    '`CLOSING_REASON_UNAVAILABLE_API_RATE_LIMIT` and `UNKNOWN_CLOSING_REASON_AS_ABANDONED_OTHER_GOLD`. '
    'Thus 34 evidence-bearing cases versus 36 taxonomy-assigned cases explains the numerical difference. '
    '**I did not locate a saved selection rule or case list for the earlier 34-case check, so this is a reproducible '
    'reconciliation, not a verified reconstruction of that earlier check.** These two remain visible here; '
    'they must not become NOT FIXED in Step 5 solely from ABANDONED/OTHER.', '',
    'Also, the paper’s **34/36** is a count of status-correct responses, not a 34-case population. '
    'The saved paper excerpt distinguishes the numerator from the 36-case audit denominator.', '',
    '## Evidence available to each arm','',
    'The table counts case-specific closure signals in the user message. The shared system message contains '
    'generic conditional instructions about asking for details and routing duplicates in every arm. '
    'Those instructions do not identify an individual case’s outcome. Empty fields in a body template are recorded '
    'separately in the detailed audit and are not treated as evidence of why an issue was closed.', '',
    '| Population | Arm | n | Missing info / cannot reproduce signal | Duplicate closure signal | Canonical target |',
    '|---|---|---:|---:|---:|---:|',
    *[f"| {s['cohort']} | {s['arm']} | {s['cases']} | {s['missing_info_or_cannot_reproduce_closure_signal']} | {s['duplicate_closure_signal']} | {s['canonical_duplicate_target_present']} |" for s in summaries], '',
    'Raw metadata provides the missing-info/cannot-reproduce signal for all 16 NEEDS_INFO cases and the native '
    'duplicate resolution for all seven REDIRECTED cases. Taxonomy inputs retain the same raw fields and append '
    'normalized class/subtype/action fields. Binary inputs omit those closure blocks. '
    'The all-82 total of 19 missing-info signals includes three cases outside the NEEDS_INFO cohort: '
    'Nextcloud #3376 and #5910 (STALE, with both stale and needs-info labels), and #6443 (OPEN, with a needs-info label). '
    'Those labels do not silently change the registered cohort membership. '
    'VLC #20777’s review says “duplicate” in a user complaint, which is retained in all arms; '
    'it does not assert that the retrieved issue is a duplicate. The literal mention is flagged separately.', '',
    '**No canonical duplicate target number or link is supplied in any arm for any of the seven REDIRECTED cases.** '
    'No taxonomy-only canonical reference exists. The retrieved issue’s own number is not its canonical target; '
    'the QA column `canonical_display_id` corrects the retrieved issue ID and does not name a duplicate target. '
    'Likewise numeric pandas row indexes in truncated body text are not target issue references.', '',
    'Consequently GIVES_CANONICAL does not qualify as a comparative test under the registered rule. '
    'It can only be descriptive, and target correctness cannot be established from these inputs. '
    'SAYS_DUPLICATE remains scoreable under the new fixed definition.', '',
    'The inspected paper describes the old 7/7 routing endpoint as explicitly saying tracked elsewhere or directing '
    'users to related discussion. It does not require a canonical number and explicitly says that merely stating '
    '“duplicate” did not count. The new SAYS_DUPLICATE definition does count an explicit duplicate statement, '
    'so the new endpoint is broader than that old descriptive endpoint. The new fixed definition is preserved.', '',
    'Per-case/per-arm evidence quotations and flags are in `input_evidence_audit.csv` (246 rows). '
    'No generation outcomes were examined to decide these flags.', '',
    '**Stopped at CHECKPOINT 2.** No routing lexical patterns, blind sheets, response scores, or statistical analysis have been created.']
(OUT/'checkpoint2.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
assert before=={name:sha(p) for name,p in SOURCES.items()}
dump('setup_manifest.json',{'preregistration_commit':'0b83e2c','stage':'CHECKPOINT 2','no_new_generation':True,
    'source_files':{name:{'path':str(p),'sha256':before[name],'unchanged_after_inspection':True} for name,p in SOURCES.items()},
    'cases':82,'responses_per_model':246,'complete_matched_case_arm_pairs':246,'class_sources':{'taxonomy_arm_input_fallback':82,'human_audited_class':0},
    'routing_cohorts':dict(cohorts),'routing_exclusions':59,'input_evidence_summaries':summaries,
    'uncertain_closure_fallbacks':[r['case_id'] for r in unknown],
    'prior_34_case_selection_rule_found':False,'canonical_target_test_eligible':False})
print(json.dumps({'cohorts':dict(cohorts),'summaries':summaries,'sources_unchanged':True},indent=2))
