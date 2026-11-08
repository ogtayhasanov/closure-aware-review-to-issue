# TOSEM fair RQ3 — real CSV incorporated (20 October 2026)

**Data status: PREPARED, NOT RERUN.** The user-provided 246-row historical CSV has been checked, deduplicated and staged. The 246 **new** shared-prompt request payloads were generated locally, with no model calls and no new accuracy labels.

## Confirmed input

- 82 fixed review-to-retrieved-issue pairs, three historical arms per pair.
- 36 prespecified audit cases: 16 NEEDS_INFO, 7 REDIRECTED, 5 REJECTED/invalid, 1 REJECTED/notvlc, 5 STALE, and 2 ABANDONED/OTHER.
- All arm-invariant source fields match within each group; 246 new prospective request payloads were generated and the existing protocol tests pass.
- The 82-case source dataset and prospective prompts contain **third-party review and tracker text: KEEP PRIVATE**. The blinded audit worklist also contains original case identifiers. Do not deposit these publicly pending a rights review.

## Source-data integrity issues (important before publishing results)

1. **11 incorrect Nextcloud display IDs** are actually large GitHub database identifiers, not issue numbers. The staging importer corrected them from supplied `https://github.com/nextcloud/android/issues/NUMBER` URLs. The full 82-case QA sheet records old and corrected values. This changes an erroneous citation field but does **not** alter retrieval ranking.
2. **28 Firefox issue bodies** are truncated Pandas Series representations (for example `Name: raw_text, dtype: object`), not the original full issue descriptions. The staged experiment retains the exact legacy body text and flags each case, so inputs are stable across arms. Restore actual archived issue bodies before a definitive clean-evidence experiment, or explicitly state this limitation/sensitivity.
3. **9 GitHub cases** had selected descriptive label-based old `resolution_signal` values (stale/needs-info), but original native `state_reason` was not preserved in the 246-row CSV. The importer preserves only available native label names and never guesses a state reason.
4. **2 Nextcloud closed cases** have *no verified closing reason* because the historical GitHub enrichment was rate-limited. These are presently labelled `ABANDONED/OTHER`; verify original closing comments or treat them as ambiguous in a prespecified sensitivity analysis. An old API error is not evidence of abandonment.
5. **49 source issue URLs missing** in the historical CSV; mostly Bugzilla/Trac fields. These are blank in the staged inputs; no invented links.
6. All 82 raw tracker field blocks were reconstructed from available legacy source columns and **not independently verified**; the staged file is a practical preflight, not a gold archival reconstruction.

## Files

- `private_working/real_82_native_staged.jsonl`: prepared 82 fixed input pairs, with corrected Nextcloud numbers and best-effort native field extraction.
- `private_working/fair_prompts_246_dryrun.jsonl`: actual ready-to-send chat request messages; **not model completions**.
- `private_working/audit36_verification_worklist.csv`: 36 case outcome/source verification worksheet.
- `private_working/quality_review_82.csv`: 82 case metadata/quality verification worksheet. Work from this for finalization (36 audit rows are a subset).
- `private_working/preflight_quality_report.json`: machine-readable integrity counts.
- `prepare_staged_native.py`: transparent converter for the user-provided CSV.
- `finalize_verified_evidence.py`: copies verified reference summaries into a final cases JSONL after the user independently checks the tracker records.
- `rq3_protocol.py`, `run_rq3.py`, `blind_and_score.py`, `lexical_checks.py`: shared-prompt runner and evaluators.
- `APPENDIX_A3_DRAFT.tex`, `RUBRIC_FROZEN.md`: prospective manuscript protocol and frozen rubric.

## Next commands — from folder containing `run_rq3.py`

To inspect the already-prepared requests (NO API key needed):

```powershell
python -m unittest discover -s tests -v
python run_rq3.py --input private_working/real_82_native_staged.jsonl --output private_working/test_request_copy.jsonl --dry-run
```

**Before claiming a definitive fair test**, independently verify source fields in the 82-row QA spreadsheet. Fill `verified_against_source=yes` for a row only after checking it against an original tracker snapshot; for the 36 audit rows also fill `neutral_reference_evidence` (a neutral, outcome-focused statement) and `reference_citation_or_link`. If source fields need correcting, update `real_82_native_staged.jsonl` as well, record the exact changes and retain the original source CSV. Then run:

```powershell
python finalize_verified_evidence.py --input private_working/real_82_native_staged.jsonl --worklist private_working/quality_review_82.csv --output private_working/real_82_verified.jsonl --require-all-82
```

For a **local exploratory pilot** before all 82 are independently verified, you can run the staged JSONL, but results must be marked exploratory and the metadata caveats disclosed. To generate on your own OpenAI API account, securely configure the `OPENAI_API_KEY` environmental variable on your machine and execute:

```powershell
python run_rq3.py --input private_working/real_82_verified.jsonl --output private_working/new_responses_246.jsonl
```

*This chat environment cannot make OpenAI API calls and has no `OPENAI_API_KEY` configured. Never paste API keys into chat.*

After **all** 246 new completions exist, check finish reasons and response count, then blind **only** the audit 36 (108 rows):

```powershell
python blind_and_score.py blind --input private_working/real_82_verified.jsonl --responses private_working/new_responses_246.jsonl --audit-only --blind-csv private_working/blind_annotations_108.csv --key-jsonl private_working/PRIVATE_blind_key.jsonl
```

**Do not open the private key while annotating**. Fill the frozen 0/1 and NA columns in a single arm-masked pass. Finally run:

```powershell
python blind_and_score.py score --blind-csv private_working/blind_annotations_108.csv --key-jsonl private_working/PRIVATE_blind_key.jsonl --report private_working/fair_human_report.json
python lexical_checks.py --input private_working/real_82_verified.jsonl --responses private_working/new_responses_246.jsonl --output private_working/lexical_screens_246.csv
```

Do not call the **historical** 34/36 vs 1/36 and 34/36 counts new results. No new generator outputs or human scores are in this bundle.
