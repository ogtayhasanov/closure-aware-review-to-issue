import collections,csv,json,re,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
from inspect_sources import xlsx_rows
DL=Path(r'C:\Users\Ogtay\Downloads')
FAIR=DL/'TOSEM_RQ3_Run/tosem_rq3_fair/private_working'
cases=[json.loads(s) for s in (FAIR/'real_82_native_staged.jsonl').read_text().splitlines()]
print('CLASSES',collections.Counter((r['l1_class'],r['subtype']) for r in cases))
print('REPOS',collections.Counter(r['repository'] for r in cases))
for p in [Path(r'C:\Users\Ogtay\Desktop\test\taxonomy_annotation_pack_FORMATTED.xlsx'),DL/'taxonomy_annotation_pack_FORMATTED (1).xlsx']:
    rows=dict(xlsx_rows(p))['Annotation']
    data=[]
    for row in rows[1:]:
        d={re.sub(r'\d','',k):v for k,v in row.items()}
        data.append(d)
    print('HUMAN_APPS',str(p),collections.Counter(d.get('D') for d in data))
    overlap=[(r['case_id'],r['repository'],r['display_issue_id'],d.get('A'),d.get('B')) for r in cases for d in data if r['display_issue_id']==d.get('E')]
    print('NUMBER_OVERLAP_REQUIRE_REPO_CHECK',overlap)
for r in cases:
    if r['subtype']=='NEEDS_INFO' or r['l1_class']=='REDIRECTED' or (r['l1_class']=='ABANDONED' and r['subtype']=='OTHER'):
        print('CASE',json.dumps(r,ensure_ascii=False))
archives=['TOSEM_Overleaf_ready_2026-08-09.zip','TOSEM_arXiv_source_2026-08-09.zip','TOSEM_REVISED_PENDING_HUMAN_STATUS_AUDIT_2026-08-08.zip']
for name in archives:
    p=DL/name
    if not p.exists():continue
    with zipfile.ZipFile(p) as z:
        for member in z.namelist():
            if not member.endswith('.tex'):continue
            text=z.read(member).decode('utf-8',errors='replace')
            lines=text.splitlines()
            hits=[(i+1,l) for i,l in enumerate(lines) if re.search(r'16/16|4/16|7/7|0/7|34/36|canonical|NEEDS_INFO|non.resolved',l,re.I)]
            if hits: print('PAPER',name,member,json.dumps(hits,ensure_ascii=False))
