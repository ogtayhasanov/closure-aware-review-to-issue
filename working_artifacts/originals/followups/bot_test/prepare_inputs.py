"""Prepare Checkpoint 1. No generation or scoring is performed."""
import ast
import contextlib
import difflib
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = Path(r'C:\Users\Ogtay\Desktop\test')
RUN = Path(r'C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair')
LEGACY = Path(r'C:\Users\Ogtay\Downloads\run_haring_rrf_frozen_e2e.py')
sys.path[:0] = [str(ROOT), str(RUN)]
import closure_provenance as provenance
import rq3_protocol as protocol
import run_rq3 as runner
from build_sample import EXTRA_BOTS

def read(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    # Reuse the existing summarize implementation; redirect only its output files.
    provenance.OUT = str(ROOT / 'provenance_out')
    original_writer = provenance.write_csv
    provenance.write_csv = lambda path, rows: original_writer(str(OUT / Path(path).name), rows)
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        provenance.run_summarize(EXTRA_BOTS)
    provenance.write_csv = original_writer
    (OUT / 'provenance_summary.txt').write_text(stream.getvalue().replace(str(ROOT / 'provenance_out'), str(OUT)), encoding='utf-8')

    # Read exact existing taxonomy tuples without executing the old research pipeline.
    tuples = set()
    for node in ast.walk(ast.parse(LEGACY.read_text(encoding='utf-8-sig'))):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
            try:
                tuples.add(tuple(ast.literal_eval(x) for x in node.value.elts[:3]))
            except (ValueError, TypeError):
                pass
    rejected = ('REJECTED', 'wontfix', 'REJECTED')
    abandoned = ('ABANDONED', 'OTHER', 'ABANDONED')
    assert rejected in tuples and abandoned in tuples

    # Check the actual completed run rather than relying on README defaults.
    historical = read(RUN / 'private_working/new_responses_246.jsonl')
    cases = read(RUN / 'private_working/real_82_native_staged.jsonl')
    case_map = {r['case_id']: r for r in cases}
    assert len(historical) == 246 and len(case_map) == 82
    assert len({(r['case_id'], r['arm']) for r in historical}) == 246
    for r in historical:
        assert r['system_sha256'] == protocol.PROMPT_SHA256
        messages = protocol.render(case_map[r['case_id']], r['arm'])
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        assert digest == r['messages_sha256'], (r['case_id'], r['arm'])
    tree = ast.parse((RUN / 'run_rq3.py').read_text(encoding='utf-8'))
    payloads = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'payload' for t in n.targets)]
    assert len(payloads) == 1
    payload = payloads[0].value
    settings = {k.value: ast.literal_eval(v) for k, v in zip(payload.keys, payload.values) if k.value in ('temperature', 'max_tokens')}
    settings.update(seed=runner.SEED, model_requested=runner.MODEL)
    assert {r['model_requested'] for r in historical} == {runner.MODEL}
    assert {r['seed'] for r in historical} == {runner.SEED}

    sampled = read(OUT / 'sample_records.jsonl')
    bodies = {(r['repo'], r['number']): r['issue'] for r in read(OUT / 'issue_bodies.jsonl')}
    assert len(bodies) == len(sampled)
    prompts, drift = [], []
    suffix = '\n\nWrite a response to the review.'
    for r in sampled:
        issue = bodies[r['repo'], r['number']]
        assert issue['state'] == 'closed'
        labels = [x['name'] if isinstance(x, dict) else x for x in (issue['labels'] or [])]
        assert r['wontfix_label'] in labels
        # Use current native fields from GET issue; keep snapshot title as preregistered.
        raw_fields = {k: issue[k] for k in ('closed_at', 'state', 'state_reason') if issue.get(k) is not None}
        raw_fields['labels'] = labels
        for name, old, new in [('title', r['title'], issue['title']), ('labels', r['labels'], labels),
                               ('state_reason', r['state_reason'].lower(), issue.get('state_reason')),
                               ('closed_at', r['closed_at'], issue.get('closed_at'))]:
            if old != new:
                drift.append({'repo': r['repo'], 'number': r['number'], 'field': name, 'scan': old, 'rest': new})
        row = {'case_id': f"{r['repo']}#{r['number']}", 'review_text': r['title'],
               'repository': r['repo'] + ' (GitHub)', 'display_issue_id': r['number'],
               'issue_title': r['title'], 'issue_body': issue['body'], 'issue_url': r['url'],
               'binary_state': 'closed', 'raw_tracker_fields': raw_fields}
        raw_message = protocol.render(row, 'raw_metadata')[1]['content']
        assert raw_message.endswith(suffix)
        closer_type = 'Bot' if provenance.is_bot(r['closed_by'], r['closed_by_type'], EXTRA_BOTS) else 'User'
        label_type = 'Bot' if provenance.is_bot(r['label_added_by'], r['label_added_by_type'], EXTRA_BOTS) else 'User'
        provenance_lines = (f"\nclosed_by: {r['closed_by']} ({closer_type})"
                            f"\nclosed_via: {r['closer_ref'] or 'none'}"
                            f"\nwontfix label added by: {r['label_added_by']} ({label_type})")
        messages = {'RAW': raw_message, 'RAW+CLOSER': raw_message[:-len(suffix)] + provenance_lines + suffix}
        for arm, cls in [('TAXONOMY-V1', r['v1_class']), ('TAXONOMY-V2', r['v2_class'])]:
            profile = rejected if cls == 'REJECTED' else abandoned
            assert profile[0] == cls
            normalized = dict(zip(('l1_class', 'subtype', 'action_l1'), profile))
            messages[arm] = protocol.render({**row, **normalized}, 'closure_aware')[1]['content']
        prefix = raw_message.split('\n\nRAW TRACKER CLOSURE FIELDS:', 1)[0]
        for arm, message in messages.items():
            assert message.startswith(prefix + '\n\nRAW TRACKER CLOSURE FIELDS:') and message.endswith(suffix)
            prompts.append({'repo': r['repo'], 'number': r['number'], 'arm': arm,
                            'system_sha256': protocol.PROMPT_SHA256, 'user_message': message})
        if r['group'] == 'HUMAN':
            assert messages['TAXONOMY-V1'] == messages['TAXONOMY-V2']
    assert len(prompts) == 320
    (OUT / 'inputs.jsonl').write_text(''.join(json.dumps(x, sort_keys=True, ensure_ascii=False)+'\n' for x in prompts), encoding='utf-8')
    (OUT / 'metadata_drift.json').write_text(json.dumps(drift, indent=2, ensure_ascii=False), encoding='utf-8')
    (OUT / 'system_prompt.txt').write_text(protocol.SYSTEM_PROMPT, encoding='utf-8')
    report = json.loads((OUT / 'sample_report.json').read_text())
    examples = [next(r for r in sampled if r['group'] == 'BOT' and r['repo'] == repo) for repo in ('signalapp/Signal-Android', 'jitsi/jitsi-meet')]
    examples.append(next(r for r in sampled if r['group'] == 'HUMAN'))
    text = ['# Bot-closure experiment — Checkpoint 1', '',
            'Status: preparation complete. No new model calls or scoring. Awaiting user OK.', '',
            'Preregistration commit: `e0bf6d9` in `C:\\Users\\Ogtay\\Desktop\\test`.', '',
            '## Reused files', '',
            f'- `{RUN / "rq3_protocol.py"}`: identical SYSTEM_PROMPT and render().',
            f'- `{RUN / "run_rq3.py"}`: call_openai(), model, seed and generation settings.',
            f'- `{RUN / "private_working/new_responses_246.jsonl"}`: completed historical run (read only).',
            f'- `{RUN / "private_working/real_82_native_staged.jsonl"}`: main rerun inputs (read only).',
            f'- `{ROOT / "closure_provenance.py"}`: imported classification and actor functions.',
            f'- `{LEGACY}`: AST-read existing taxonomy tuples; pipeline never executed.', '',
            'All 246 historical message hashes reproduce exactly from the saved 82 cases and current renderer.',
            f'System SHA-256: `{protocol.PROMPT_SHA256}`.',
            f'Generation settings read from code: `{json.dumps(settings, sort_keys=True)}`.',
            'Historical returned model IDs: ' + ', '.join(sorted({r['model_returned'] for r in historical})) + '.', '',
            '## Sample', '', '| Group | Signal | Jitsi | Total |', '|---|---:|---:|---:|',
            '| BOT | 25 | 25 | 50 |', '| HUMAN | 3 | 27 | 30 |', '',
            'Eligible pools: BOT 1,687 Signal + 1,290 Jitsi; HUMAN 3 Signal + 27 Jitsi.',
            'The HUMAN group is smaller than 50 because only 30 qualify. All 30 are retained.',
            'Seed: 20261024. No classification exceptions. No duplicate scan rows.',
            '18,290 unique scanned issues = 80 sampled + 18,210 excluded. Every exclusion is in exclusions.csv.', '',
            '| Exclusion reason (overlapping) | Count |', '|---|---:|']
    text.extend(f'| {k} | {v} |' for k, v in report['exclusion_reasons_nonexclusive'].items())
    text += ['', 'Unknown label-adder exclusions: 0. Mixed bot/human cases after eligibility filters: 348.',
             'Sampling exclusions: 2,927 eligible BOT issues. No eligible HUMAN issue was dropped.', '',
             '## Preparation decisions for review', '',
             '- Extra bot: automated-signal (API type User). Inferred automation from account name and bulk scan closures on 2018-04-02; the public profile has no explanatory bio. No wontfix-labelled issue uses this closer, so the choice has no effect on either sample group.',
             '- Both scan cursors are DONE. Original summarize() was rerun; its output files were redirected here to preserve existing provenance outputs.',
             '- All 80 issue bodies were fetched through the GitHub connector GET-issue operation. No comments were fetched for sampled issues or supplied to prompts. Body excerpt remains exactly the original renderer limit of 1,200 characters.',
             '- Review and issue title use the scan title verbatim. Current REST native closure metadata is shared across arms. Every scan/REST difference is in metadata_drift.json; there are no exclusions caused by differences.',
             '- The original shared prompt has no prose class descriptions. Existing REJECTED/wontfix/REJECTED and ABANDONED/OTHER/ABANDONED tuples are reused. OTHER avoids adding a new subtype or inferring an inactivity reason solely from the bot closer. No legacy unequal system prompt or action description is imported.',
             '- RAW is the unmodified renderer output. RAW+CLOSER appends exactly the three prescribed provenance lines. Both taxonomy arms use unmodified closure_aware rendering with the corresponding existing tuple.',
             '- Every issue has four prompts with identical common prefix and final instruction; only closure data differ. All 30 HUMAN taxonomy prompt pairs are byte-identical.', '',
             '## Later-stage dependency', '',
             'The reused 246-run kit provides lexical action diagnostics and a human status rubric, but no implemented metric explicitly named specific closure reason conveyed. No replacement metric has been written. Its original implementation or an agreed definition must be established before the Model B main-run analysis.', '',
             '## Representative full prompts and differences', '',
             'The system message is identical for all 320 prompts and saved in system_prompt.txt. Full user messages follow. Diffs compare each alternative with RAW.']
    for r in examples:
        relevant = [p for p in prompts if (p['repo'],p['number']) == (r['repo'],r['number'])]
        text += ['', f"### {r['group']}: {r['repo']}#{r['number']}", '', r['url']]
        for p in relevant:
            text += ['', f"#### {p['arm']}", '', '```text', p['user_message'], '```']
        for p in relevant[1:]:
            diff = ''.join(difflib.unified_diff((relevant[0]['user_message']+'\n').splitlines(True), (p['user_message']+'\n').splitlines(True), fromfile='RAW', tofile=p['arm']))
            text += ['', '```diff', diff.rstrip(), '```']
    (OUT / 'checkpoint1.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    files = [ROOT/'bot_closure_test.md', ROOT/'closure_provenance.py', RUN/'rq3_protocol.py', RUN/'run_rq3.py',
             RUN/'private_working/new_responses_246.jsonl', RUN/'private_working/real_82_native_staged.jsonl', LEGACY]
    manifest = {'status': 'checkpoint_1_awaiting_ok', 'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
                'preregistration_commit': 'e0bf6d9', 'generation_settings': settings, 'system_sha256': protocol.PROMPT_SHA256,
                'historical_requests_verified': 246, 'sample_seed': 20261024, 'sample_count': 80, 'input_count': 320,
                'new_model_calls': 0, 'source_sha256': {str(p): sha(p) for p in files},
                'output_sha256': {p.name: sha(p) for p in OUT.iterdir() if p.is_file() and p.name != 'preparation_manifest.json'}}
    (OUT / 'preparation_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'sample': 80, 'prompts': len(prompts), 'historical_hash_checks': 246, 'drift_entries': len(drift), 'new_model_calls': 0}))

if __name__ == '__main__':
    main()
