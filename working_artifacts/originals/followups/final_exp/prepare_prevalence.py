"""Use complete frozen scans and unchanged V1/V2 code; report deviations without tuning."""
import collections,csv,hashlib,importlib.util,json,shutil,subprocess,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
OUT=Path(__file__).resolve().parent
SOURCE=Path(r'C:\Users\Ogtay\Desktop\test\provenance_out')
DEST=OUT/'provenance_out'
PAPER=Path(r'C:\Users\Ogtay\Downloads\TOSEM_Overleaf_ready_2026-08-09.zip')
PROJECTS=[('Jitsi','jitsi/jitsi-meet',6929,42.5),('Nextcloud','nextcloud/android',7156,34.9),
 ('AnkiDroid','ankidroid/Anki-Android',8952,27.5),('Brave','brave/brave-browser',44238,20.3),
 ('Signal','signalapp/Signal-Android',11269,18.2),('K-9 Mail','thunderbird/thunderbird-android',5024,13.3),
 ('PPSSPP','hrydgard/ppsspp',8711,5.7)]
EXTRA={'automated-signal'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
DEST.mkdir(exist_ok=True)
sources={};completeness=[]
for project,repo,n,pct in PROJECTS:
    stem='scan_'+repo.replace('/','__')
    for ext in ['.jsonl','.cursor']:
        p=SOURCE/(stem+ext);assert p.exists(),f'Missing scan: {repo}'
        if ext=='.cursor':assert p.read_text().strip()=='DONE',f'Incomplete scan: {repo}'
        sources[str(p)]=sha(p)
        target=DEST/p.name
        if not target.exists():shutil.copyfile(p,target)
        assert sha(target)==sha(p),'Existing copied scan differs; do not overwrite'
    completeness.append({'project':project,'repository':repo,'scan_complete':True,'new_scan_needed':False})
result=subprocess.run([sys.executable,str(OUT/'scripts/closure_provenance.py'),'summarize','--extra-bots','automated-signal'],cwd=OUT,text=True,encoding='utf-8',capture_output=True)
assert result.returncode==0,result.stderr
(OUT/'provenance_summarize.txt').write_text(result.stdout.replace(str(OUT),'.'),encoding='utf-8')
spec=importlib.util.spec_from_file_location('frozen_provenance',OUT/'scripts/closure_provenance.py')
cp=importlib.util.module_from_spec(spec);spec.loader.exec_module(cp)
base=list(csv.DictReader((DEST/'summary_by_repo.csv').open(encoding='utf-8-sig')))
base={r['repo']:r for r in base};rows=[]
for project,repo,paper_n,paper_rate in PROJECTS:
    records=[json.loads(s) for s in (DEST/('scan_'+repo.replace('/','__')+'.jsonl')).read_text(encoding='utf-8').splitlines() if s.strip()]
    assert len({r['number'] for r in records})==len(records),f'Duplicate scan rows: {repo}'
    n=len(records);v1=collections.Counter(cp.classify(r,EXTRA,False)[0] for r in records);v2=collections.Counter(cp.classify(r,EXTRA,True)[0] for r in records)
    nr1=n-v1['RESOLVED'];nr2=n-v2['RESOLVED'];r1=100*nr1/n;r2=100*nr2/n
    assert int(base[repo]['closed'])==n and int(base[repo]['nonres_v1'])==nr1 and int(base[repo]['nonres_v2'])==nr2
    rejected=[r for r in records if any(cp.RX_REJECT.search(l) for l in r['labels'])]
    label_instances=[cp.label_added_by(r,label) for r in rejected for label in r['labels'] if cp.RX_REJECT.search(label)]
    added_bot=sum(cp.is_bot(login,typ,EXTRA) for login,typ in label_instances)
    unknown=sum(login=='?' for login,typ in label_instances)
    closed_bot=sum(cp.bot_closed_without_fix(r,EXTRA) for r in rejected)
    all_bot_no_fix=sum(cp.bot_closed_without_fix(r,EXTRA) for r in records)
    rows.append({'project':project,'repository':repo,'closed_issues':n,'paper_table1_closed_issues':paper_n,
       'closed_count_difference':n-paper_n,'nonresolved_v1_count':nr1,'nonresolved_v1_pct':r1,
       'nonresolved_v2_count':nr2,'nonresolved_v2_pct':r2,'v2_minus_v1_percentage_points':r2-r1,
       'paper_table1_nonresolved_pct':paper_rate,'v1_minus_paper_percentage_points':r1-paper_rate,
       'within_0_5_percentage_points':abs(r1-paper_rate)<=.5,
       'issues_with_any_rejection_label':len(rejected),'rejection_label_instances':len(label_instances),
       'rejection_labels_added_by_bot':added_bot,'rejection_label_adder_unknown':unknown,
       'rejection_labels_added_by_bot_pct_all_label_instances':100*added_bot/len(label_instances) if label_instances else None,
       'rejection_labels_added_by_bot_pct_known_adders':100*added_bot/(len(label_instances)-unknown) if len(label_instances)>unknown else None,
       'rejection_labeled_issues_closed_by_bot_no_fix':closed_bot,
       'rejection_labeled_issues_closed_by_bot_no_fix_pct':100*closed_bot/len(rejected) if rejected else None,
       'all_issues_closed_by_bot_no_fix':all_bot_no_fix,'all_issues_closed_by_bot_no_fix_pct':100*all_bot_no_fix/n,
       'script_v1_rejected_by_label':int(base[repo]['reject_by_label']),
       'script_v1_reject_label_added_by_bot':int(base[repo]['reject_label_added_by_bot']),
       'script_v1_reject_closed_by_bot_no_fix':int(base[repo]['reject_closed_by_bot_no_fix'])})
with (OUT/'prevalence_sensitivity.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with zipfile.ZipFile(PAPER) as z:
    text=z.read('main.tex').decode('utf-8').splitlines()
(OUT/'table1_source_excerpt.txt').write_text('\n'.join(text[278:312])+'\n',encoding='utf-8')
lines=['# Prevalence sensitivity: unchanged V1 versus V2','',
 'All seven GitHub projects in the paper’s Table 1 have completed scans (DONE cursors). No missing project and no new network scan. '
 'The original closure_provenance.py was copied byte for byte and run with `summarize --extra-bots automated-signal`; no rule was tuned. '
 'The inference that automated-signal is automation is the same declared addition used in bot_test.', '',
 '| Project | Closed | Paper V1 % | Recomputed V1 % | V2 % | V1−paper pp | Within 0.5 pp | Rejection-labeled issues | Labels added by bot % | Such issues bot-closed/no fix % |',
 '|---|---:|---:|---:|---:|---:|---|---:|---:|---:|']
for r in rows:
    bot_labels='n/a' if r['rejection_labels_added_by_bot_pct_all_label_instances'] is None else f"{r['rejection_labels_added_by_bot_pct_all_label_instances']:.1f}"
    bot_closed='n/a' if r['rejection_labeled_issues_closed_by_bot_no_fix_pct'] is None else f"{r['rejection_labeled_issues_closed_by_bot_no_fix_pct']:.1f}"
    lines.append(f"| {r['project']} | {r['closed_issues']} | {r['paper_table1_nonresolved_pct']:.1f} | {r['nonresolved_v1_pct']:.2f} | {r['nonresolved_v2_pct']:.2f} | {r['v1_minus_paper_percentage_points']:+.2f} | {'yes' if r['within_0_5_percentage_points'] else 'NO'} | {r['issues_with_any_rejection_label']} | {bot_labels} | {bot_closed} |")
lines += ['', '**Differences are reported without changing the mapping.** Scan totals are reported alongside the paper’s historical totals in the CSV. '
 'A difference can reflect time/snapshot changes, a different original mapping, or extraction differences; the current artifacts alone '
 'do not identify which caused it. A failure of the 0.5-point reproduction check is not described as successful replication.', '',
 'The rejection-label population includes every issue with any raw label matching the unchanged RX_REJECT, even when duplicate '
 'precedence makes its V1 class REDIRECTED. “Labels added by bot” uses matching issue-label instances as the denominator, '
 'with the last retained add event per label. Unknown adders remain in that denominator and are separately counted in the CSV; '
 'the known-adder-only percentage is also provided. This is an observed bot-attribution share, not an assumption that unknown '
 'actors are human. “Such issues bot-closed/no fix” is conditional on rejection-labeled issues. The all-closed-issue share is '
 'also in the CSV. The unchanged script’s narrower V1 REJECTED-by-label counts are retained in separate columns.', '',
 'The source GraphQL scan retains only its configured label/timeline windows, so an unknown adder or absent linked closer '
 'may reflect incomplete historical provenance. V2 is a rule sensitivity analysis, not independently adjudicated truth. '
 'Firefox/Bugzilla and VLC/Trac are not GitHub projects and are not recomputed by this GitHub-only script. '
 'The manuscript and its tables are unchanged. Full source hashes and scan completeness are in prevalence_manifest.json.']
(OUT/'prevalence_sensitivity.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
assert all(sha(Path(p))==h for p,h in sources.items())
(OUT/'prevalence_manifest.json').write_text(json.dumps({'extra_bots':sorted(EXTRA),'source_scan_sha256':sources,
 'scan_completeness':completeness,'all_sources_unchanged':True,'script_sha256':sha(OUT/'scripts/closure_provenance.py'),
 'table1_archive_sha256':sha(PAPER),'projects_failing_0_5_point_check':[r['project'] for r in rows if not r['within_0_5_percentage_points']],
 'rows':rows},indent=2)+'\n',encoding='utf-8')
print(json.dumps([{'project':r['project'],'V1':round(r['nonresolved_v1_pct'],2),'V2':round(r['nonresolved_v2_pct'],2),'difference_pp':round(r['v1_minus_paper_percentage_points'],2)} for r in rows],indent=2))
