**LATEST:** The original 246-row historical CSV was uploaded and converted into real 82-case preflight files. Begin with `START_HERE_WITH_REAL_CSV.md` (supersedes the older input-missing instructions below). **No new model generations have been executed.**

# TOSEM RQ3 fair-prompt rerun kit — 20 October 2026

**Status: prompt/code frozen and tested; no real generation has been executed.** This kit is a preparation artifact, not experimental evidence. It does not overwrite earlier labels, outputs, or manuscript results. It addresses items 1–3 in the current RQ3 revision plan and adds a preliminary action-realization screen (item 5).

## Input required

Export the **same 82 fixed final-RRF review→retrieved-issue cases** used in the original experiment, as JSONL (one JSON object per line). Required per-case keys:

`case_id`, `review_text`, `repository`, `display_issue_id`, `issue_title`, `binary_state`, `l1_class`, `subtype`, `action_l1`, `raw_tracker_fields`.

Also supply `issue_body`, `issue_url`, and a **neutral reference_evidence** synopsis, independently checked against original issue metadata and closing comments. The full 82-case population must contain exactly 36 closed non-resolved cases (L1 REJECTED/ABANDONED/REDIRECTED). The code validates both counts. The reference synopsis should document the *actual issue outcome*, not a prediction copied from a generation arm; a provenance pointer to original tracker evidence should be retained outside the blind evaluation.

`raw_tracker_fields` must be a JSON object of **unmodified native tracker closure fields** such as `resolution`, `state_reason`, `labels`, `closed_at` and where grounded, `closed_by`. Do not accidentally substitute a taxonomy-derived field such as a postprocessed `resolution_signal` for the true native field: that leaks interpretation into the raw condition. Keep the raw field selection frozen across raw and structured arms. Exclude taxonomy and labels from the binary closure section (both arms continue to have the same issue title/body context). The source review and issue text are **not** in the public GitHub artifact; see its `DATA_AVAILABILITY.md`.

**Original data export located:** the older research script `run_haring_rrf_threeway_final.py` reads `C:\Users\Ogtay\Downloads\haring_rrf_e2e_generation_20260808\rrf_closure_aware_responses_and_judgments.csv` and creates `C:\Users\Ogtay\Downloads\haring_rrf_threeway_generation_20260808\rrf_threeway_responses_and_judgments.csv`. Either CSV contains the 82 fixed review–issue inputs needed. The helper `import_legacy_csv.py` deduplicates these files into 82 JSONL cases and drops all historical model responses and judgments. If it must use the old derived `resolution_signal`, be explicit that this is a **legacy signal**, not independently verified native tracker metadata.

Convert the **private** historical CSV to JSONL (do not use public text-free score tables):

```bash
python import_legacy_csv.py --input rrf_threeway_responses_and_judgments.csv \
  --output real_82.jsonl --allow-legacy-signal
```

If the CSV also contains unmodified `resolution`/`state_reason` source columns, prefer `--native-fields`. If neither original source fields nor the legacy signal are reliable, recover the native tracker metadata before executing the fair test. Fill the `reference_evidence` values independently before the human audit; the importer deliberately leaves them blank rather than manufacturing an answer key.

A toy dataset with 3 cases is included solely to test the script. **Never report toy outputs as research results.**

## Execute

Run with Python 3.9+ and no extra packages. First inspect and validate request payloads **without calling a model**:

```bash
python -m unittest discover -s tests -v
python run_rq3.py --input real_82.jsonl --output requests_dryrun.jsonl --dry-run
```

Freeze `RUBRIC_FROZEN.md` and the shared prompt hash *before* executing the actual API generation. To run for all 82 reviews (246 calls), securely set `OPENAI_API_KEY` **in your local shell environment**; never paste it into ChatGPT or files. Then:

```bash
python run_rq3.py --input real_82.jsonl --output responses_v1.jsonl
```

The run is resumable: completed `(case_id, arm)` keys are skipped, and the script refuses to mix prompt or model versions. All 246 responses must be complete before evaluating the full dataset. The model ID is pinned to the historical gpt-4o-mini snapshot and temperature 0, 220 max tokens; API-side seed/fingerprint are logged because perfect repeatability is not guaranteed.

## Blind the 36-case human subset **before examining model outputs**

```bash
python blind_and_score.py blind --input real_82.jsonl \
  --responses responses_v1.jsonl \
  --audit-only --blind-csv blind_annotations.csv \
  --key-jsonl .private_blind_key.jsonl
```

Keep `.private_blind_key.jsonl` closed and inaccessible to the annotator until the entire sheet is frozen. The blind CSV has 108 rows in randomized order with no case IDs or arm names. Fill the four required fields using `RUBRIC_FROZEN.md` (`status_correct`, `unsupported_fix_claim`, `other_unsupported_claim`, `required_action_present`) and any notes. Then:

```bash
python blind_and_score.py score --blind-csv blind_annotations.csv \
  --key-jsonl .private_blind_key.jsonl --report human_paired_report.json
```

For the 82-case automatic lexical **diagnostics** (not accuracy judgments):

```bash
python lexical_checks.py --input real_82.jsonl \
  --responses responses_v1.jsonl --output lexical_screen_246.csv
```

Report full 36-case status correctness, raw vs structured paired disagreements, pairwise tests, and action-realization denominators. Do not read `response` text as a measure of retrieval relevance; the retrieved top-1 is held fixed by design. Automated **LLM-judge** scores from independent model families are a separate subsequent experiment, not created by this kit.

## Why this is a fairer comparison

All arms share the exact same system prompt (`SYSTEM_PROMPT` in `rq3_protocol.py`). All share issue title/body/URL, and differ **only** in closure-related fields. The binary arm is not told "closed means fixed". The structured arm receives all raw fields plus `l1_class`, `subtype`, and `action_l1`, but no extra action-specific text. Thus raw vs structured is a controlled measure of the information added by normalization, not privileged model instructions.

The prior manuscript's 34/36 versus 1/36 result and 34/36 raw metadata count belong to the old unequal-prompt setup. They must **not** be relabelled or quoted as outcomes of this rerun. `APPENDIX_A3_DRAFT.tex` is a proposed prospective appendix, **not an edit of the submitted manuscript**.

## Safety / traceability

- Do not publish the internal 82-review JSONL or generated response text without checking third-party redistribution rights.
- Preserve the original dataset, frozen retrieval ranking, closure mappings, and prior responses unchanged for provenance. Date/time-stamp the run and record model fingerprint.
- Missing or truncation-affected completions must be rerun *before* decoding arms, using a documented criterion independent of condition. Review all `finish_reason` values before blinding.
- The lexical redirection expression is intentionally stricter than just finding "duplicate"; manual judgments remain authoritative.
