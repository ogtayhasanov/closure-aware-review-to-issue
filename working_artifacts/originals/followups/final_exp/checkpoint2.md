# Final experiments — Checkpoint 2

The authorized work through Checkpoint 2 is complete. The manuscript and all earlier prompts, responses, and scan sources remain unchanged. No primary tests or human-audit rates have been substituted with automated labels.

## Generation and scoring

- 162 TAXONOMY-ONLY inputs × two registered generators = 324 complete responses. Every final response is nonblank and stop-terminated; none is silently omitted.
- GPT-4o-mini-2024-07-18 and gemma-4-26b-a4b-it use the saved provider/model settings, shared system prompt, temperature 0, and 220-token generation limit. Gemma thinking tokens are zero. All actual request payloads were verified against the registered inputs.
- Every new response has GPT-5.4 nano and frozen lexical scores for DECLINED, FIX_CLAIM, INACTIVITY, ASKS_DETAILS, and SAYS_DUPLICATE in auto_scores.csv.
- The 140 audit responses have additional evidence-based NO_FALSE_FIX/STATES_OUTCOME judge labels and response-only routing labels for later agreement checks. Thirty-five identical response-only routing judgments were reused with exact text hashes; the other 105 audit routing responses were scored separately. These are supplemental labels, never human labels.
- Source snapshots and execution-source hashes are retained. The unchanged core judge prompt and both original lexical files match their sources byte for byte. API usage is recorded in api_usage.csv. No final response or score is missing.

## Human audit ready

audit_sheet.csv contains 140 GPT-4o-mini responses: 35 cases × four hidden arms. The seed is 20261024. The four arms are binary_state, raw_metadata, closure_aware, and TAXONOMY-ONLY. Their names are present only in the separate audit_key.csv.

Nextcloud #2131 was generated as received but excluded from every analysis because its final closure was merged fix PR #4470. The audit retains #3425 and supplies its actual closing-comment context: Samsung battery restrictions and logs, with manual closure and no linked code fix in its complete refreshed timeline.

NO_FALSE_FIX and STATES_OUTCOME are blank for labeling. ASKS_DETAILS is applicable for 64 rows (16 cases × four arms), and SAYS_DUPLICATE for 28 rows (seven cases × four arms); all other cells in those two columns are NA. No original case is excluded except #2131. The 100 blank issue_url cells correspond to 25 archived cases without URLs, not to dropped responses; tracker and issue number remain in the evidence column.

Use audit_instructions.md. Keep sheet_id, tracker evidence, response text, and prefilled NA cells unchanged. Do not open keys or automated-score files while labeling. Your working sheet has not been cleared or replaced by the release's blank template.

## Prevalence sensitivity

All seven GitHub projects in Table 1 have complete DONE scans, so no new scan or GitHub token was needed. The original closure_provenance.py was run unchanged with the same extra-bot list, automated-signal. No mapping rule was tuned.

| Project | V1 non-resolved % | V2 non-resolved % | V1 minus Table 1 (points) | Within 0.5 points |
|---|---:|---:|---:|---|
| Jitsi | 42.52 | 42.58 | +0.02 | yes |
| Nextcloud | 42.52 | 42.58 | +7.62 | NO |
| AnkiDroid | 27.66 | 27.95 | +0.16 | yes |
| Brave | 23.66 | 23.68 | +3.36 | NO |
| Signal | 18.66 | 28.44 | +0.46 | yes |
| K-9 Mail | 20.38 | 21.60 | +7.08 | NO |
| PPSSPP | 11.24 | 11.24 | +5.54 | NO |

Only three of seven projects reproduce the paper's rate within the requested tolerance. The other four are explicitly reported as failures of that check. Snapshot timing, extraction, and original-rule differences cannot be disentangled from the current artifacts alone. Full counts, rejection-label attribution, unknown adders, bot-close/no-linked-fix shares, and denominator definitions are in prevalence_sensitivity.csv and prevalence_sensitivity.md. Firefox/Bugzilla and VLC/Trac are outside this GitHub script.

## Release package

release/ contains every scoped system/user message set, final response, automated score, relevant source script, raw attempt ledger, complete scan snapshot, source inventory, README, and SHA-256 manifest. The scope is the fair RQ3 run, bot test, routing checks, and TAXONOMY-ONLY follow-up: 728 unique message sets and 1,456 final responses. Older unequal-prompt manuscript runs are explicitly outside this scoped package.

The release passes credential and absolute-profile/workspace-path scans. Original tracker logs and titles contain personal local paths, so exported copies deidentify those profile prefixes. Five canonical message sets are affected; zero response texts are changed. Original hashes are retained alongside export hashes in the package. The actual experimental prompts, responses, and scans outside the release remain untouched. DEIDENTIFICATION.json records the transformations. Regeneration from those five sanitized messages is not an exact-text replay of the original experiment.

The standalone verify_release.py checks every packaged file hash and all canonical prompt/response hashes. All exported Python scripts pass syntax parsing. Line-ending conversion is disabled for these artifacts so their recorded byte hashes remain stable. Temporary encrypted OpenAI/Google credential files were removed after all model calls completed; no credentials are packaged.

## Waiting at Checkpoint 2

Waiting for the completed audit_sheet.csv. Then calculate the registered primary two-test Holm family, human rates and Wilson intervals, secondary comparisons, tracker-status FIX_CLAIM split, and human/lexical/judge agreement. #2131 will remain excluded from every analysis. No manuscript changes are authorized by this preparation step.
