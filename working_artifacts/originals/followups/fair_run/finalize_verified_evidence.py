#!/usr/bin/env python3
"""Attach independently verified reference summaries and approval flags to RQ3 cases.

To support a confirmatory 82-case experiment, verify all 82 input sources
against archived tracker records and fill source_verified=yes, including fixing
any incorrect/incomplete field values in the source JSONL itself.
This script does NOT modify raw tracker fields or hallucinate issue evidence.
"""
import argparse, csv, json
from pathlib import Path
from rq3_protocol import audit,validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,help='real_82_native_staged.jsonl')
    parser.add_argument('--worklist',required=True,help='quality_review_82.csv with approvals and 36 audit reference summaries')
    parser.add_argument('--output',required=True)
    parser.add_argument('--require-all-82',action='store_true',help='Block completion until all 82 inputs are approved')
    a=parser.parse_args()
    path=Path(a.output)
    if path.exists():raise FileExistsError(f'Refuse overwrite {path}')
    cases=[json.loads(s) for s in Path(a.input).read_text(encoding='utf-8').splitlines() if s.strip()]
    validate(cases)
    with open(a.worklist,encoding='utf-8-sig',newline='') as f:work=list(csv.DictReader(f))
    refs={r['case_id']:r for r in work}
    if len(work)!=82 or len(refs)!=82 or set(refs)!={r['case_id'] for r in cases}:
        raise ValueError('QA worklist must contain exactly the original 82 unique cases')
    for c in cases:
        row=refs[c['case_id']]
        agreed=row.get('verified_against_source','').strip().lower() in ('yes','y','true','1')
        c['metadata_source_verified']=agreed
        if a.require_all_82 and not agreed:
            raise ValueError(f"No source verification for {c['case_id']} (all 82 required)")
        if audit(c):
            evidence=row.get('neutral_reference_evidence','').strip()
            cite=row.get('reference_citation_or_link','').strip()
            if not agreed or not evidence or not cite:
                raise ValueError(f"Missing independently verified source, evidence, or citation for audit36 case {c['case_id']}")
            c['reference_evidence']=evidence
            c['reference_citation_or_link']=cite
    with path.open('w',encoding='utf-8') as f:
        for c in cases:f.write(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n')
    print('Verified audit references attached:',sum(bool(c['reference_evidence']) for c in cases))
    print('Verified source cases:',sum(c['metadata_source_verified'] for c in cases),'/82')
    print('Output saved:',path)
if __name__=='__main__':main()
