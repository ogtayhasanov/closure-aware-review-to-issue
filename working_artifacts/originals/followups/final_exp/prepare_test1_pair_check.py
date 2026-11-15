"""Create only the requested 12-pair blind check and report frozen-score agreement."""
import collections,csv,hashlib,json,math,random,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def read(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def textsha(s):return hashlib.sha256(s.encode()).hexdigest()
def boolean(s):
    assert s in ['True','False'],s
    return s=='True'
def writecsv(name,rows,protect=False):
    p=OUT/name
    if protect:assert not p.exists(),'Refusing to overwrite an existing human-check file'
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def wilson(k,n):
    z=1.959963984540054;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return max(0,c-h),min(1,c+h)
sources=[OUT/n for n in ['audit_sheet.csv','audit_key.csv','audit_primary_scores.csv','primary_paired_tests.csv','auto_scores.csv',
 'responses_taxonomy_only_gpt-4o-mini-2024-07-18.jsonl','responses_taxonomy_only_gemma-4-26b-a4b-it.jsonl']]
before={str(p):sha(p) for p in sources}
sheet={r['sheet_id']:r for r in csvread(OUT/'audit_sheet.csv')}
key={r['sheet_id']:r for r in csvread(OUT/'audit_key.csv')}
primary=csvread(OUT/'audit_primary_scores.csv')
cases=collections.defaultdict(dict)
for r in primary:
    if r['arm'] in ['raw_metadata','TAXONOMY-ONLY']:cases[r['case_id']][r['arm']]=r
assert len(cases)==35 and all(len(p)==2 for p in cases.values())
discordant=sorted(cid for cid,p in cases.items() if p['raw_metadata']['judge_STATES_OUTCOME']!=p['TAXONOMY-ONLY']['judge_STATES_OUTCOME'])
assert len(discordant)==12
aonly=sum(boolean(cases[c]['TAXONOMY-ONLY']['judge_STATES_OUTCOME']) for c in discordant)
assert aonly==1
test1=csvread(OUT/'primary_paired_tests.csv')[0]
assert int(test1['a_only'])==aonly and int(test1['b_only'])==12-aonly
selected=[cases[c][arm] for c in discordant for arm in ['TAXONOMY-ONLY','raw_metadata']]
random.Random(20261024).shuffle(selected)
rows=[];private=[]
for i,r in enumerate(selected,1):
    old=sheet[r['sheet_id']];k=key[r['sheet_id']];sid=f'C{i:03d}'
    assert textsha(old['response'])==r['response_sha256']==k['response_sha256']
    assert not ('nextcloud/' in k['repository'] and k['issue_number']=='2131')
    rows.append({'sheet_id':sid,'issue_url':old['issue_url'],'tracker_evidence':old['tracker_evidence'],
                 'response':old['response'],'STATES_OUTCOME':''})
    private.append({'sheet_id':sid,'source_sheet_id':r['sheet_id'],'case_id':r['case_id'],'arm':r['arm'],
        'model':k['model'],'repository':k['repository'],'issue_number':k['issue_number'],
        'response_sha256':k['response_sha256'],'tracker_evidence_sha256':k['tracker_evidence_sha256']})
assert len(rows)==24 and len({r['case_id'] for r in private})==12
assert collections.Counter(r['arm'] for r in private)=={'TAXONOMY-ONLY':12,'raw_metadata':12}
assert all('arm' not in r and r['STATES_OUTCOME']=='' for r in rows)
writecsv('audit_test1_pairs_sheet.csv',rows,True);writecsv('audit_test1_pairs_key.csv',private,True)

auto=csvread(OUT/'auto_scores.csv');agreement=[]
for model in ['gpt-4o-mini-2024-07-18','gemma-4-26b-a4b-it']:
    responses={r['input_id']:r for r in read(OUT/f'responses_taxonomy_only_{model}.jsonl')}
    bot=[r for r in auto if r['dataset']=='bot_test' and r['arm']=='TAXONOMY-ONLY' and r['model_requested']==model]
    assert len(bot)==80 and collections.Counter(r['group'] for r in bot)=={'BOT':50,'HUMAN':30}
    for r in bot:assert r['response_sha256']==responses[r['input_id']]['response_sha256']==textsha(responses[r['input_id']]['response'])
    for group in ['BOT','HUMAN','ALL_BOT_TEST']:
        rs=[r for r in bot if group=='ALL_BOT_TEST' or r['group']==group]
        counts=collections.Counter((boolean(r['judge_DECLINED']),boolean(r['lexical_DECLINED'])) for r in rs)
        a=counts[True,True];b=counts[True,False];c=counts[False,True];d=counts[False,False];n=len(rs)
        po=(a+d)/n;pj=(a+b)/n;pl=(a+c)/n;pe=pj*pl+(1-pj)*(1-pl)
        kap=(po-pe)/(1-pe) if abs(1-pe)>1e-14 else None
        lo,hi=wilson(a+d,n)
        agreement.append({'model':model,'group':group,'n':n,'judge_yes_lexical_yes':a,'judge_yes_lexical_no':b,
            'judge_no_lexical_yes':c,'judge_no_lexical_no':d,'judge_positive':a+b,'lexical_positive':a+c,
            'agree':a+d,'agreement_pct':100*po,'agreement_wilson95_lower':lo,'agreement_wilson95_upper':hi,
            'cohen_kappa':kap,'kappa_note':'Undefined: both scorers constant, expected agreement=1' if kap is None else ''})
writecsv('taxonomy_only_declined_agreement.csv',agreement)
report=['# DECLINED agreement: new TAXONOMY-ONLY bot-test responses','',
 'Existing frozen judge and lexical flags only; no new generation, judging, relabeling, or pattern changes. '
 'Every response hash was verified. Agreement is between two automated procedures, not accuracy against human truth.', '',
 '## Main comparison: the 50 BOT cases, separately per generator','',
 '| Model | Agreement | Wilson 95% interval | Cohen’s κ | Judge positive | Lexical positive |',
 '|---|---|---|---|---:|---:|']
for r in agreement:
    if r['group']!='BOT':continue
    k='undefined (both constant)' if r['cohen_kappa'] is None else f"{r['cohen_kappa']:.4f}"
    report.append(f"| {r['model']} | {r['agree']}/{r['n']} ({r['agreement_pct']:.1f}%) | {100*r['agreement_wilson95_lower']:.1f}–{100*r['agreement_wilson95_upper']:.1f}% | {k} | {r['judge_positive']} | {r['lexical_positive']} |")
report += ['', '### BOT-case contingency counts','',
 '| Model | Judge+/lexical+ | Judge+/lexical− | Judge−/lexical+ | Judge−/lexical− |',
 '|---|---:|---:|---:|---:|',
 *[f"| {r['model']} | {r['judge_yes_lexical_yes']} | {r['judge_yes_lexical_no']} | {r['judge_no_lexical_yes']} | {r['judge_no_lexical_no']} |" for r in agreement if r['group']=='BOT'], '',
 '## Supplement: HUMAN cases and the full 80-case bot-test population','',
 'These strata clarify the denominator; they are not pooled across generators. Marginal label prevalence '
 'differs sharply between BOT and HUMAN cases, so the all-80 kappa is not a substitute for BOT-only agreement.', '',
 '| Model | Group | n | Agreement | Cohen’s κ |','|---|---|---:|---|---|']
for r in agreement:
    if r['group']=='BOT':continue
    k='undefined (both constant)' if r['cohen_kappa'] is None else f"{r['cohen_kappa']:.4f}"
    report.append(f"| {r['model']} | {r['group']} | {r['n']} | {r['agree']}/{r['n']} ({r['agreement_pct']:.1f}%) | {k} |")
report += ['', 'A high observed agreement with no positive labels can have undefined kappa. Undefined is reported '
 'explicitly rather than replaced with zero or one. Full counts and intervals for every stratum are in the CSV.', '',
 'The new 24-response human sheet concerns STATES_OUTCOME in fair cases; it does not validate DECLINED '
 'on the BOT cases. Primary automated results and all earlier sheets remain unchanged.']
(OUT/'taxonomy_only_declined_agreement.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
assert before=={str(p):sha(p) for p in sources}
manifest={'selection_plan_commit':'45b12fd8ae8df5978d68f326a17f992a35cc9f61','seed':20261024,
 'test':'1: TAXONOMY-ONLY versus raw_metadata on primary-judge STATES_OUTCOME',
 'discordant_pairs':12,'response_rows':24,'required_human_answers':24,'label_columns':['STATES_OUTCOME'],
 'arm_hidden':True,'original_text_preserved':True,'prior_sheets_and_scores_unchanged':True,
 'response_rows_per_arm':12,'excluded_case':'nextcloud/android#2131','new_model_calls':0,
 'sheet_sha256':sha(OUT/'audit_test1_pairs_sheet.csv'),'key_sha256':sha(OUT/'audit_test1_pairs_key.csv'),
 'source_sha256':before,'selection_limitation':'Judge-discordant subset only; not a representative full-population check.'}
(OUT/'test1_pairs_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sheet_rows':24,'answers':24,'pairs':12,'BOT_DECLINED_agreement':[r for r in agreement if r['group']=='BOT']},indent=2))
