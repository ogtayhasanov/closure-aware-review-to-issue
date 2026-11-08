"""Independent final coverage, paired-test, and artifact checks (no model calls)."""
import ast,csv,hashlib,json
from pathlib import Path
from math import comb
from fractions import Fraction
ROOT=Path(__file__).resolve().parent
def csvread(name):return list(csv.DictReader((ROOT/name).open(encoding='utf-8-sig',newline='')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p in ROOT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
manifest=json.loads((ROOT/'preparation_manifest.json').read_text(encoding='utf-8'))
for path,expected in manifest['source_sha256'].items():assert sha(Path(path))==expected
for name,expected in manifest['outputs_sha256'].items():assert sha(ROOT/name)==expected
scores=csvread('scores_all_arms.csv');assert len(scores)==1296
assert len({(r['model'],r['arm'],r['input_id']) for r in scores})==1296
for table in ['primary_tests.csv','secondary_tests.csv']:
    for r in csvread(table):
        a,b=int(r['a_only']),int(r['b_only']);n=a+b
        # Independently sum all binomial outcomes at most as probable as observed.
        expected=float(sum((Fraction(comb(n,k),2**n) for k in range(n+1) if comb(n,k)<=comb(n,a)),Fraction())) if n else 1.0
        assert abs(expected-float(r['p_exact_two_sided']))<1e-12
        def group(arm):
            return {s['case_id']:s['judge_'+r['question']]=='True' for s in scores if s['model']==r['model'] and s['arm']==arm and s['excluded_from_all_analyses']=='False' and ((r['cohort']=='BOT' and s['dataset']=='bot_test' and s['group']=='BOT') or (r['cohort']=='audit35' and s['dataset']=='fair' and s['judge_STATES_OUTCOME']!='NA'))}
        x,y=group(r['arm_a']),group(r['arm_b']);assert x.keys()==y.keys()
        assert sum(x[k] and not y[k] for k in x)==a
        assert sum(y[k] and not x[k] for k in x)==b
blind=csvread('audit_test2_sheet.csv');key=csvread('audit_test2_key.csv')
assert len(blind)==len(key)==8
assert all(r['STATES_OUTCOME']=='' for r in blind)
assert all(set(r)=={'sheet_id','issue_url','tracker_evidence','response','STATES_OUTCOME'} for r in blind)
test=csvread('.form_runtime/test_export.csv')
assert test[0]['STATES_OUTCOME']=='YES'
assert all(a[c]==b[c] for a,b in zip(blind,test) for c in ['sheet_id','issue_url','tracker_evidence','response'])
for p in ROOT.iterdir():
    if p.is_file():assert (b'sk-'+b'proj-') not in p.read_bytes(),'Potential credential leak: '+p.name
verified={'all_checks_passed':True,'scripts_parse':True,'source_and_input_hashes_unchanged':True,'score_rows':1296,'independently_verified_exact_tests':8,'blind_rows':8,'blind_label_columns':1,'CSV_export_text_preserved':True,'credential_scan_passed':True,'file_sha256':{p.name:sha(p) for p in ROOT.iterdir() if p.is_file() and p.name!='verification.json'}}
(ROOT/'verification.json').write_text(json.dumps(verified,indent=2)+'\n',encoding='utf-8')
print('Verified all source hashes, 1296 score rows, eight exact paired tests, and the eight-answer form/export.')
