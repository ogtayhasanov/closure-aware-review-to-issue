"""Build the preregistered sample without making model calls."""
import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
SOURCE = Path(r'C:\Users\Ogtay\Desktop\test')
sys.path.insert(0, str(SOURCE))
from closure_provenance import classify, is_bot, label_added_by, first_match

REPOS = ('signalapp/Signal-Android', 'jitsi/jitsi-meet')
SEED = 20261024
EXTRA_BOTS = {'automated-signal'}
RX = re.compile(r"won'?t[\s_-]?fix", re.I)
OUT = Path(__file__).resolve().parent

def csv_write(name, rows, fields=None):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def main():
    pools = {(g, repo): [] for g in ('BOT', 'HUMAN') for repo in REPOS}
    excluded, duplicates, exceptions = [], [], []
    scan_counts = {}
    for repo in REPOS:
        stem = SOURCE / 'provenance_out' / ('scan_' + repo.replace('/', '__'))
        assert stem.with_suffix('.cursor').read_text().strip() == 'DONE', repo
        records = {}
        for line in stem.with_suffix('.jsonl').read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r['number'] in records:
                duplicates.append({'repo': repo, 'number': r['number'], 'reason': 'duplicate scan row; last record retained as in load_scans'})
            records[r['number']] = r
        scan_counts[repo] = len(records)
        for r in sorted(records.values(), key=lambda x: x['number']):
            label = first_match(r.get('labels', []), RX)
            v1 = classify(r, EXTRA_BOTS, bot_rule=False)[0]
            v2 = classify(r, EXTRA_BOTS, bot_rule=True)[0]
            login, typ = label_added_by(r, label) if label else ('?', '')
            reasons = []
            if not label: reasons.append('no_wontfix_label')
            if v1 == 'REDIRECTED': reasons.append('v1_redirected')
            if r.get('closer'): reasons.append('linked_fix')
            if r.get('n_closes') != 1: reasons.append('close_count_not_one')
            if r.get('n_reopens') != 0: reasons.append('reopened')
            if label and (not login or login == '?'): reasons.append('unknown_label_adder')
            group = None
            if not reasons:
                cb = is_bot(r.get('closed_by'), r.get('closed_by_type'), EXTRA_BOTS)
                lb = is_bot(login, typ, EXTRA_BOTS)
                if cb and lb:
                    group = 'BOT'
                elif not cb and not lb and r.get('closed_by_type') == 'User' and typ == 'User':
                    group = 'HUMAN'
                elif cb != lb and (cb or r.get('closed_by_type') == 'User') and (lb or typ == 'User'):
                    reasons.append('mixed_bot_human')
                else:
                    reasons.append('actor_not_known_bot_or_user')
            if reasons:
                excluded.append({'repo': repo, 'number': r['number'], 'reason': ';'.join(reasons)})
                continue
            expected = ('REJECTED', 'ABANDONED' if group == 'BOT' else 'REJECTED')
            if (v1, v2) != expected:
                exceptions.append({'repo': repo, 'number': r['number'], 'group': group, 'v1': v1, 'v2': v2})
            pools[group, repo].append({**r, 'group': group, 'wontfix_label': label,
                                      'label_added_by': login, 'label_added_by_type': typ,
                                      'v1_class': v1, 'v2_class': v2})
    rng = random.Random(SEED)
    selected = []
    for group in ('BOT', 'HUMAN'):
        chosen, remainder = [], []
        for repo in REPOS:
            pool = pools[group, repo]
            take = rng.sample(pool, min(25, len(pool)))
            chosen.extend(take)
            ids = {x['number'] for x in take}
            remainder.extend(x for x in pool if x['number'] not in ids)
        if len(chosen) < 50:
            chosen.extend(rng.sample(remainder, min(50 - len(chosen), len(remainder))))
        selected.extend(chosen)
        ids = {(x['repo'], x['number']) for x in chosen}
        for repo in REPOS:
            for r in pools[group, repo]:
                if (repo, r['number']) not in ids:
                    excluded.append({'repo': repo, 'number': r['number'], 'reason': 'eligible_not_sampled_' + group})
    selected.sort(key=lambda x: (x['group'], x['repo'], x['number']))
    fields = ['repo','number','url','title','group','closed_by','closed_by_type','wontfix_label',
              'label_added_by','state_reason','labels','v1_class','v2_class']
    csv_write('sample.csv', [{k: json.dumps(r[k], ensure_ascii=False) if k == 'labels' else r[k] for k in fields} for r in selected], fields)
    csv_write('exclusions.csv', excluded, ['repo','number','reason'])
    csv_write('duplicate_scan_rows.csv', duplicates, ['repo','number','reason'])
    (OUT / 'sample_records.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in selected), encoding='utf-8')
    report = {'seed': SEED, 'extra_bots': sorted(EXTRA_BOTS), 'scan_counts': scan_counts,
              'eligible': {g: {repo: len(pools[g, repo]) for repo in REPOS} for g in ('BOT','HUMAN')},
              'sample': {g: {repo: sum(r['group']==g and r['repo']==repo for r in selected) for repo in REPOS} for g in ('BOT','HUMAN')},
              'excluded_issue_count': len(excluded), 'exclusion_reasons_nonexclusive': dict(Counter(x for r in excluded for x in r['reason'].split(';'))),
              'duplicates': duplicates, 'class_exceptions': exceptions}
    assert sum(scan_counts.values()) == len(selected) + len(excluded)
    (OUT / 'sample_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if exceptions:
        raise SystemExit('Classification exceptions require review; no inputs generated.')

if __name__ == '__main__':
    main()
