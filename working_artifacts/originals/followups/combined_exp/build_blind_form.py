"""Use the accepted one-question form for the conditional test-2 check."""
import csv,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;FINAL=ROOT.parent/'final_exp'
manifest=json.loads((ROOT/'blind_sheet_manifest.json').read_text(encoding='utf-8'))
if manifest['response_rows']==0:
    print('No discordant pairs: no human sheet or form required.')
    raise SystemExit(0)
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
sheet=rows(ROOT/'audit_test2_sheet.csv');key={r['sheet_id']:r for r in rows(ROOT/'audit_test2_key.csv')}
facts=json.loads((ROOT/'audit_case_display.json').read_text(encoding='utf-8'))
data={'version':1,'dataset_hash':hashlib.sha256((ROOT/'audit_test2_sheet.csv').read_bytes()).hexdigest(),'question_keys':['STATES_OUTCOME'],'columns':list(sheet[0]),'notes_enabled':False,'export_basename':'audit_test2','rows':[{**r,'friendly_facts':facts[key[r['sheet_id']]['case_id']],'display_response':r['response']} for r in sheet]}
template=(ROOT/'form_template.html').read_text(encoding='utf-8')
template=template.replace('Short response check',f'{len(sheet)}-response closure check').replace('Read once. Answer with your keyboard. Progress saves here.','One question per response. Press Y / N / U. Progress saves here.')
template=re.sub(r'<details id="help".*?</details>','<details id="help"><summary>What counts as correct?</summary><p>Answer Yes if the response states the specific closure outcome supported by the tracker evidence. Answer No if it gives a wrong reason or merely says the issue is closed. Use Unsure if the evidence does not let you decide.</p></details>',template,count=1,flags=re.S)
encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
(ROOT/'audit_test2_review.html').write_text(template.replace('@@DATA@@',encoded),encoding='utf-8')
assert all('arm' not in r for r in data['rows'])
print(f'Created blind form: {len(sheet)} responses, {len(sheet)} answers, only STATES_OUTCOME.')
