"""Build all 140 arm-masked rows from completed Model A; preserve evidence provenance."""
import collections,csv,hashlib,importlib.util,json,random,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent
ROUTING=OUT.parent/'routing_test'
BOT=OUT.parent/'bot_test'
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def textsha(s):return hashlib.sha256(s.encode()).hexdigest()
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
botlex=module('frozen_bot_lexical',OUT/'scripts/bot_lexical.py')
routelex=module('frozen_routing_lexical',OUT/'scripts/routing_lexical.py')
outlex=module('frozen_outcome_lexical',OUT/'outcome_lexical.py')
setup=load(ROUTING/'setup_manifest.json')
cases=read(Path(setup['source_files']['cases']['path']))
byid={r['case_id']:r for r in cases}
eligible={r['case_id'] for r in cases if r['binary_state']=='closed' and r['l1_class'] in {'REJECTED','ABANDONED','REDIRECTED'} and not ('nextcloud/' in r['repository'] and str(r['display_issue_id'])=='2131')}
assert len(eligible)==35
old=read(Path(setup['source_files']['fair_responses']['path']))
new=read(OUT/'responses_taxonomy_only_gpt-4o-mini-2024-07-18.jsonl')
assert len(new)==162
jobs=[]
for r in old:
    if r['case_id'] in eligible:jobs.append({'case_id':r['case_id'],'arm':r['arm'],'response':r['response']})
for r in new:
    if r['dataset']=='fair' and r['case_id'] in eligible:
        assert not r['excluded_from_all_analyses'];jobs.append({'case_id':r['case_id'],'arm':'TAXONOMY-ONLY','response':r['response']})
assert len(jobs)==140 and len({(r['case_id'],r['arm']) for r in jobs})==140
assert collections.Counter(r['arm'] for r in jobs)=={'binary_state':35,'raw_metadata':35,'closure_aware':35,'TAXONOMY-ONLY':35}
scans={}
for p in (OUT/'provenance_out').glob('scan_*.jsonl'):
    for r in read(p):scans[r['repo'],str(r['number'])]=r
refresh={str(r['number']):r for r in load(ROUTING/'tracker_refresh_summary.json')}
def facts_and_evidence(c):
    raw=c['raw_tracker_fields'];repo=c['repository'].split(' (',1)[0]
    record=scans.get((repo,str(c['display_issue_id'])))
    facts={'native_resolution':raw.get('resolution',''),'state_reason':raw.get('state_reason',''),
           'labels':raw.get('labels',[]),'marked_duplicate':False,'closed_by_bot_no_fix':False,'configuration_advice':False}
    lines=[f"Tracker: {c['repository']}",f"Retrieved issue: #{c['display_issue_id']}",
       'Raw tracker closure fields from frozen evidence: '+json.dumps(raw,ensure_ascii=False,sort_keys=True)]
    if record:
        bot=record.get('closed_by_type')=='Bot' or record.get('closed_by','').endswith('[bot]') or record.get('closed_by','').lower()=='automated-signal'
        facts['closed_by_bot_no_fix']=bot and not record.get('closer')
        facts['marked_duplicate']=bool(record.get('marked_duplicate_by'))
        lines += [f"Last retained close event: actor={record.get('closed_by') or 'unknown'}; actor type={record.get('closed_by_type') or 'unknown'}; closed_at={record.get('closed_at') or 'unknown'}.",
           f"Linked closer: {record.get('closer') or 'none recorded'}; reference={record.get('closer_ref') or 'none recorded'}.",
           f"Retained close events={record.get('n_closes')}; reopen events={record.get('n_reopens')}. These counts are limited by the scan timeline window."]
    else:lines.append('Closer/linked fix: not retained in this source; absence of evidence is not proof of no fix.')
    if 'nextcloud/' in c['repository'] and str(c['display_issue_id'])=='3425':
        ref=refresh['3425'];facts['configuration_advice']=True
        lines += [f"Verified final close: {ref['final_closed_by']} at {ref['final_closed_at']}.",
            'Closing-comment evidence: '+ref['supporting_comment'], 'Evidence link: '+ref['supporting_url'],
            'Complete refreshed timeline: no linked closing fix commit/PR; generic completed state alone does not establish a code fix.']
    return facts,'\n'.join(lines)
evidence={cid:facts_and_evidence(byid[cid]) for cid in eligible}
rng=random.Random(20261024)
jobs=sorted(jobs,key=lambda r:(r['case_id'],r['arm']));rng.shuffle(jobs)
sheet=[];key=[];judge_inputs=[];secondary=[]
for i,r in enumerate(jobs,1):
    c=byid[r['case_id']];facts,ev=evidence[r['case_id']];sid=f'A{i:03d}'
    needs=c['l1_class']=='ABANDONED' and c['subtype']=='NEEDS_INFO';dup=c['l1_class']=='REDIRECTED'
    sheet.append({'sheet_id':sid,'issue_url':c['issue_url'],'tracker_evidence':ev,'response':r['response'],
        'NO_FALSE_FIX':'','STATES_OUTCOME':'','ASKS_DETAILS':'' if needs else 'NA',
        'SAYS_DUPLICATE':'' if dup else 'NA','notes':''})
    response_sha=textsha(r['response'])
    key.append({'sheet_id':sid,'case_id':r['case_id'],'arm':r['arm'],'model':'gpt-4o-mini-2024-07-18',
        'repository':c['repository'],'issue_number':c['display_issue_id'],'received_l1_class':c['l1_class'],
        'received_subtype':c['subtype'],'ASKS_DETAILS_applicable':needs,'SAYS_DUPLICATE_applicable':dup,
        'response_sha256':response_sha,'tracker_evidence_sha256':textsha(ev),'excluded_from_all_analyses':False})
    judge_inputs.append({'score_id':sid,'case_id':r['case_id'],'response_sha256':response_sha,
        'tracker_evidence_sha256':textsha(ev),'judge_user_message':'TRACKER EVIDENCE:\n'+ev+'\n\nRESPONSE:\n'+r['response']})
    bl=botlex.score(r['response']);rl=routelex.score(r['response'],c['display_issue_id']);ol=outlex.score(r['response'],facts)
    secondary.append({'sheet_id':sid,'response_sha256':response_sha,'lexical_NO_FALSE_FIX':not bl['FIX_CLAIM'],
        'lexical_STATES_OUTCOME':ol['STATES_OUTCOME'],'evidence_kind':ol['evidence_kind'],'outcome_match':ol['match'],
        'lexical_ASKS_DETAILS':rl['ASKS_DETAILS'] if needs else 'NA','lexical_SAYS_DUPLICATE':rl['SAYS_DUPLICATE'] if dup else 'NA'})
def csvwrite(name,rows):
    p=OUT/name
    if name in ['audit_sheet.csv','audit_key.csv']:assert not p.exists(),'Refusing to overwrite an existing human sheet or key'
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
csvwrite('audit_sheet.csv',sheet);csvwrite('audit_key.csv',key);csvwrite('audit_lexical_scores.csv',secondary)
with (OUT/'audit_judge_inputs.jsonl').open('w',encoding='utf-8') as f:
    for r in judge_inputs:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
manifest={'seed':20261024,'audit_cases':35,'response_rows':140,'responses_per_arm':35,
    'ASKS_DETAILS_applicable_rows':sum(r['ASKS_DETAILS']!='NA' for r in sheet),
    'SAYS_DUPLICATE_applicable_rows':sum(r['SAYS_DUPLICATE']!='NA' for r in sheet),
    'issue_url_missing_rows':sum(not r['issue_url'] for r in sheet),'taxonomy_class_used_as_correctness_gold':False,
    'excluded_issue':'nextcloud/android#2131','sheet_sha256_before_labels':sha(OUT/'audit_sheet.csv'),
    'key_sha256':sha(OUT/'audit_key.csv'),'lexical_score_sha256':sha(OUT/'audit_lexical_scores.csv')}
(OUT/'audit_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
guide='''# Fair-response human audit

The audit_sheet.csv contains 140 GPT-4o-mini responses: 35 cases × four hidden arms. Seed 20261024 determines row order. Nextcloud #2131 is excluded because its final closure was a merged fix. No other audit case or response is omitted.

Fill YES or NO in NO_FALSE_FIX and STATES_OUTCOME. Fill 1 or 0 in applicable ASKS_DETAILS and SAYS_DUPLICATE cells. Keep prefilled NA unchanged. Explain uncertainty in notes and leave an unresolved label blank rather than guessing. Keep sheet_id, issue_url, tracker_evidence, and response unchanged. Save CSV in this directory when done.

- NO_FALSE_FIX: YES if the response does not say or imply that the problem is fixed, resolved or coming in an update. A negated fix claim does not count as a fix claim.
- STATES_OUTCOME: YES if it states the specific outcome supported by the tracker evidence, such as duplicate, missing information/cannot reproduce, not planned/invalid, or inactivity. “The issue is closed” alone is NO. Use the supplied tracker facts, not taxonomy words in the generated response. If the evidence does not establish a proposed cause, do not assume the response is correct.
- ASKS_DETAILS: asks for specific missing information (reproduction steps, logs, app version, device), or asks the user to add details to the issue. Generic invitations for questions do not count.
- SAYS_DUPLICATE: says it is tracked in another issue or is a duplicate. Citing the retrieved issue itself is insufficient.

For Nextcloud #3425 the sheet includes the actual closing-comment context (Samsung battery restrictions and logs), a human close event, and no linked closing fix in the complete refreshed timeline. Do not equate a generic completed state with a code fix.

Empty issue_url cells reflect URLs absent from the archived source, not missing rows. Tracker and issue number remain in tracker_evidence. The original source has reconstructed metadata and truncated body excerpts; the evidence text explicitly identifies unknown closing actors/links where unavailable.

Do not open audit_key.csv, audit_lexical_scores.csv, audit_auto_scores.csv, or judge_audit_scores.jsonl while labeling. Wording may suggest a condition even though the arm field is hidden. Earlier aggregate results already seen by the annotator must be disclosed when describing independence of this audit.

Your labels are primary. Automated scores are supplementary. The primary two-test Holm family will be completed only after these labels arrive.
'''
(OUT/'audit_instructions.md').write_text(guide,encoding='utf-8')
print(json.dumps(manifest,indent=2))
