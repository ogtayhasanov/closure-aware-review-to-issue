"""Validate and analyze the returned 24-response blind check, without rescoring."""
import csv
import hashlib
import json
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/Ogtay/Downloads/audit_test1_pairs_labeled.csv')

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def flag(value):
    assert value in ('True', 'False'), value
    return value == 'True'

def agreement(rows, field):
    pairs = [(r['human_STATES_OUTCOME'] == 'YES', flag(r[field])) for r in rows]
    counts = Counter(pairs)
    n = len(pairs)
    same = sum(a == b for a, b in pairs)
    hp = sum(a for a, _ in pairs) / n
    ap = sum(b for _, b in pairs) / n
    expected = hp * ap + (1 - hp) * (1 - ap)
    kappa = ((same / n - expected) / (1 - expected)) if expected < 1 else None
    return {'n': n, 'agree': same, 'agreement_pct': 100 * same / n,
            'kappa': kappa, 'human_yes_auto_yes': counts[True, True],
            'human_yes_auto_no': counts[True, False],
            'human_no_auto_yes': counts[False, True],
            'human_no_auto_no': counts[False, False]}

def main():
    columns, returned = read(SOURCE)
    template_columns, template = read(ROOT / 'audit_test1_pairs_sheet.csv')
    assert columns == template_columns
    assert len(returned) == 24
    assert len({r['sheet_id'] for r in returned}) == 24
    expected = {r['sheet_id']: r for r in template}
    assert {r['sheet_id'] for r in returned} == set(expected)
    key = {r['sheet_id']: r for r in read(ROOT / 'audit_test1_pairs_key.csv')[1]}
    scores = {r['sheet_id']: r for r in read(ROOT / 'audit_primary_scores.csv')[1]}
    joined = []
    for row in returned:
        sid = row['sheet_id']
        for col in columns:
            if col != 'STATES_OUTCOME':
                assert row[col] == expected[sid][col], (sid, col)
        assert row['STATES_OUTCOME'] in ('YES', 'NO'), (sid, row['STATES_OUTCOME'])
        k = key[sid]
        assert hashlib.sha256(row['response'].encode()).hexdigest() == k['response_sha256']
        assert hashlib.sha256(row['tracker_evidence'].encode()).hexdigest() == k['tracker_evidence_sha256']
        s = scores[k['source_sheet_id']]
        assert s['case_id'] == k['case_id'] and s['arm'] == k['arm']
        joined.append({**k, 'human_STATES_OUTCOME': row['STATES_OUTCOME'],
                       'judge_STATES_OUTCOME': s['judge_STATES_OUTCOME'],
                       'lexical_STATES_OUTCOME': s['lexical_STATES_OUTCOME']})
    paired = defaultdict(dict)
    for r in joined:
        assert r['arm'] not in paired[r['case_id']]
        paired[r['case_id']][r['arm']] = r['human_STATES_OUTCOME'] == 'YES'
    assert len(paired) == 12
    assert all(set(p) == {'raw_metadata', 'TAXONOMY-ONLY'} for p in paired.values())
    cells = Counter((p['TAXONOMY-ONLY'], p['raw_metadata']) for p in paired.values())
    a, b = cells[True, False], cells[False, True]
    discordant = a + b
    pvalue = min(1.0, 2 * sum(math.comb(discordant, i) for i in range(min(a, b) + 1)) / 2 ** discordant) if discordant else 1.0
    stats = {
        'source_filename': SOURCE.name, 'source_sha256': sha(SOURCE),
        'rows': 24, 'pairs': 12, 'missing': 0, 'unsure': 0, 'exclusions': [],
        'context_and_response_match': True,
        'human_labels': dict(Counter(r['human_STATES_OUTCOME'] for r in joined)),
        'judge_human': agreement(joined, 'judge_STATES_OUTCOME'),
        'lexical_human': agreement(joined, 'lexical_STATES_OUTCOME'),
        'human_by_arm': {arm: {'yes': sum(r['human_STATES_OUTCOME'] == 'YES' for r in joined if r['arm'] == arm), 'n': 12} for arm in ('raw_metadata', 'TAXONOMY-ONLY')},
        'human_paired_selected_subset': {'both_yes': cells[True, True], 'taxonomy_only_yes': a, 'raw_only_yes': b, 'both_no': cells[False, False], 'exact_mcnemar_p_unadjusted': pvalue},
        'limitation': 'Selected on judge discordance in test 1. Agreement and paired results describe these 24 responses/12 cases only, not the full 35-case population. Primary automated scores and tests remain unchanged.'
    }
    destination = ROOT / SOURCE.name
    assert not destination.exists(), 'Do not overwrite an imported human-label file.'
    shutil.copyfile(SOURCE, destination)
    with (ROOT / 'test1_human_check_joined.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(joined[0]))
        w.writeheader()
        w.writerows(joined)
    (ROOT / 'test1_human_check_statistics.json').write_text(json.dumps(stats, indent=2) + '\n', encoding='utf-8')
    j, l = stats['judge_human'], stats['lexical_human']
    lines = [
        '# Human check of test 1 discordant pairs', '',
        'The returned blind sheet has 24 completed YES/NO answers from 12 pairs. No blank or unsure answers, exclusions, duplicate IDs, or altered evidence/response text were found. The original exported file is preserved byte for byte.', '',
        '## Agreement with human labels', '',
        '| Automated method | Agreement | Cohen’s κ | Human YES / automated YES | Human YES / automated NO | Human NO / automated YES | Human NO / automated NO |',
        '|---|---:|---:|---:|---:|---:|---:|'
    ]
    for name, s in [('Judge', j), ('Lexical', l)]:
        lines.append(f"| {name} | {s['agree']}/24 ({s['agreement_pct']:.1f}%) | {s['kappa']:.4f} | {s['human_yes_auto_yes']} | {s['human_yes_auto_no']} | {s['human_no_auto_yes']} | {s['human_no_auto_no']} |")
    lines += ['', '## Human outcomes within the selected pairs', '', '| Arm | STATES_OUTCOME = YES |', '|---|---:|']
    for arm, s in stats['human_by_arm'].items():
        lines.append(f"| {arm} | {s['yes']}/12 ({100*s['yes']/12:.1f}%) |")
    lines += ['', f'Human pair counts: both YES {cells[True, True]}; TAXONOMY-ONLY only YES {a}; raw only YES {b}; both NO {cells[False, False]}.', '',
              f'Exploratory exact two-sided McNemar on these 12 selected pairs: p = {pvalue:.8g}, unadjusted. This is not a replacement for the prespecified 35-case primary test or its Holm correction.', '',
              stats['limitation'], '',
              'This check labels STATES_OUTCOME in fair-case responses. It does not validate BOT DECLINED labels or the other routing questions. No new model calls or lexical-pattern changes were made.', '',
              f"Imported source SHA-256: `{stats['source_sha256']}`.", '']
    report = '\n'.join(lines)
    (ROOT / 'test1_human_check_results.md').write_text(report, encoding='utf-8')
    results = ROOT / 'results.md'
    existing = results.read_text(encoding='utf-8')
    assert '## Completed 24-response human check' not in existing
    results.write_text(existing + '\n## Completed 24-response human check\n\n' +
        f"The later 24-response blind check is complete: 24 YES/NO labels, no missing/unsure answers or exclusions, with exact response/evidence matches. Judge–human agreement is {j['agree']}/24 ({j['agreement_pct']:.1f}%), κ = {j['kappa']:.4f}; lexical–human agreement is {l['agree']}/24 ({l['agreement_pct']:.1f}%), κ = {l['kappa']:.4f}. These apply only to the 12 judge-discordant pairs selected from test 1. See `test1_human_check_results.md` for arm counts, contingencies, and limitations. The earlier 73-response sheet remains uncompleted; its pending agreement is not replaced with this selected-subset estimate. Primary automated results above remain unchanged.\n", encoding='utf-8')
    print(json.dumps(stats, indent=2))

if __name__ == '__main__':
    main()
