# Provisional routing and tracker-status results — 1 November 2026

**Lexical-only routing results. Human validation is pending.** The user authorized this analysis on 1 November 2026, superseding the wait for labels for these provisional results. No new generation or judging was performed. The paper, original responses, prompts, earlier checkpoints, and human annotation sheets remain unchanged.

## Two refreshed Nextcloud closures

**[#2131](https://github.com/nextcloud/android/issues/2131) is FIXED under the requested evidence rule.** [PR #4470](https://github.com/nextcloud/android/pull/4470), “Normalize local target path in auto upload”, explicitly says “This closes #2131 and closes #4220.” It merged on 1 October 2019 at 09:15:30 UTC; the final issue-close event follows at 09:15:31 UTC. An earlier stale-bot closure on 23 May 2019 was reopened on 30 July. The historical ABANDONED/OTHER fallback therefore does not describe the final outcome.

**[#3425](https://github.com/nextcloud/android/issues/3425) was closed manually with configuration advice.** tobiasKaminsky closed it on 14 January 2019 at 06:48:34 UTC, at the same time as [advice about Samsung battery restrictions and logs](https://github.com/nextcloud/android/issues/3425#issuecomment-453913811). Its complete eight-event timeline contains no closing fix commit or PR. The current generic state_reason is completed, but that alone does not prove a code fix. It remains UNCERTAIN under the strict amended status rule. The observed context is configuration advice, not evidence of abandonment. Raw snapshots, comments, timelines, and the merged PR are retained in `tracker_refresh_20261101/`.

This refresh corrects the earlier interpretation that the two cases might simply be dropped from 36 to obtain 34 confirmed non-resolved cases: one is demonstrably fixed and the other lacks sufficient status evidence. The other 34 taxonomy-defined non-resolved cases are not all independently validated either. No frozen cohort or input was retrospectively repaired.

## Routing rates

The 23 registered routing cases are retained (16 NEEDS_INFO, 7 REDIRECTED), with all three responses per case for each model. The other 59 cases are individually accounted for in `exclusions.csv`. Routing cohorts use the registered taxonomy-input fallback only for selection; taxonomy is not an answer key. The already frozen lexical rules and 138 saved lexical records were verified against exact response hashes. Each entry below is positive count / case count, percentage, and Wilson 95% interval.

| Model | Arm | ASKS_DETAILS (n=16) | SAYS_DUPLICATE (n=7) |
|---|---|---|---|
| GPT-4o-mini | binary_state | 7/16 (43.8%; 23.1–66.8) | 1/7 (14.3%; 2.6–51.3) |
| GPT-4o-mini | raw_metadata | 12/16 (75.0%; 50.5–89.8) | 7/7 (100.0%; 64.6–100.0) |
| GPT-4o-mini | closure_aware | 14/16 (87.5%; 64.0–96.5) | 7/7 (100.0%; 64.6–100.0) |
| Gemma | binary_state | 12/16 (75.0%; 50.5–89.8) | 0/7 (0.0%; 0.0–35.4) |
| Gemma | raw_metadata | 14/16 (87.5%; 64.0–96.5) | 7/7 (100.0%; 64.6–100.0) |
| Gemma | closure_aware | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |

The frozen lexical check does not reproduce the old large raw-versus-taxonomy separation. With fair prompts, raw already requests details in 12/16 GPT-4o-mini cases and 14/16 Gemma cases, compared with 14/16 and 15/16 under taxonomy. Both arms flag duplicates in 7/7 cases for both models. This provisional evidence does not establish a taxonomy routing advantage; it also cannot prove equivalence.

A concrete lexical limitation is visible in the GPT-4o-mini binary SAYS_DUPLICATE count: the sole positive is VLC #20777, where the response says “duplicated entries”. That describes playlist content, not a duplicate tracker issue. The frozen lexical result remains 1/7 and is explicitly flagged here as a semantic false positive. It is not silently corrected or presented as a human-confirmed routing success.

### Paired taxonomy versus raw comparisons

Exact two-sided McNemar, paired by case. Holm adjustment is across the two routing questions within each generator. Binary is shown for reference only. These automated comparisons are provisional; they do not replace human coding. Non-significance does not establish equivalence.

| Model | Question | Pairs | Taxonomy only | Raw only | Exact p | Holm p |
|---|---|---:|---:|---:|---:|---:|
| GPT-4o-mini | ASKS_DETAILS | 16 | 3 | 1 | 0.625 | 1 |
| GPT-4o-mini | SAYS_DUPLICATE | 7 | 0 | 0 | 1 | 1 |
| Gemma | ASKS_DETAILS | 16 | 1 | 0 | 1 | 1 |
| Gemma | SAYS_DUPLICATE | 7 | 0 | 0 | 1 | 1 |

Canonical issue targets were absent from every original arm for all seven REDIRECTED cases. GIVES_CANONICAL therefore remains descriptive/unassessable; it is not counted as seven failures. The new SAYS_DUPLICATE definition includes an explicit duplicate statement. The old paper endpoint required explicit routing elsewhere and was narrower, so the old 7/7 versus 0/7 endpoint is not numerically interchangeable.

Human-label agreement and Cohen’s kappa are **unavailable**. Both 69-row blind sheets already exist for later annotation and were left unchanged. Any later annotation after seeing these results should be described as arm-masked, but not fully independent of the aggregate findings. Lexical patterns can miss paraphrases or misread requests and negation; no patterns were adjusted after inspecting outcomes.

## FIX_CLAIM by tracker-supported status

**82 input cases: 16 FIXED, 24 NOT FIXED, 42 UNCERTAIN.** These are review/issue cases, not 82 unique tracker issues. All three arms share the same status registry. Repeated issues are retained because the paired experiment contains different reviews; possible dependence between those cases limits inference.

- FIXED: 8 Bugzilla FIXED + 7 Trac fixed + Nextcloud #2131 with a verified closing merged fix PR.
- NOT FIXED: closed native WORKSFORME, INCOMPLETE, INVALID, or DUPLICATE codes (case-insensitive).
- UNCERTAIN: 11 open cases, 1 Trac notvlc case, and 30 GitHub closed cases without the specific FIXED/NOT FIXED evidence required here.

The 30 uncertain GitHub cases include repeated retrieved issues. Generic completed state and stale/needs-info labels do not establish a code fix or one of the requested resolution codes. This phase refreshed the two requested GitHub issues; it did not independently re-fetch and adjudicate every remaining GitHub case. Bugzilla/Trac codes are the retained native-resolution fields, originally reconstructed from the legacy export and not re-fetched in this phase. Those provenance limits are retained per row. No taxonomy class enters the status-assignment function. See `true_status_registry.csv` and the explicit 42-row uncertain list.

Reuse of the existing FIX_CLAIM judge labels is shown first (GPT-5.4 nano; no new calls). All 492 response hashes and judgments matched. Rates concern tracker-status errors: they are not equivalent to prompt faithfulness, especially where newly verified fix evidence was absent from the original input.

| Model | Arm | False fix claims / NOT FIXED | Missed fixes / FIXED | UNCERTAIN | FIX_CLAIM within UNCERTAIN |
|---|---|---|---|---:|---:|
| GPT-4o-mini | binary_state | 0/24 (0.0%; 0.0–13.8) | 15/16 (93.8%; 71.7–98.9) | 42 | 0 |
| GPT-4o-mini | raw_metadata | 0/24 (0.0%; 0.0–13.8) | 0/16 (0.0%; 0.0–19.4) | 42 | 4 |
| GPT-4o-mini | closure_aware | 0/24 (0.0%; 0.0–13.8) | 1/16 (6.2%; 1.1–28.3) | 42 | 19 |
| Gemma | binary_state | 0/24 (0.0%; 0.0–13.8) | 15/16 (93.8%; 71.7–98.9) | 42 | 0 |
| Gemma | raw_metadata | 0/24 (0.0%; 0.0–13.8) | 6/16 (37.5%; 18.5–61.4) | 42 | 1 |
| Gemma | closure_aware | 0/24 (0.0%; 0.0–13.8) | 3/16 (18.8%; 6.6–43.0) | 42 | 17 |

FIX_CLAIM occurrences in UNCERTAIN cases are not labeled false. No uncertain case was silently dropped, reclassified through taxonomy, or included in the false-fix or missed-fix denominators.

### Existing lexical FIX_CLAIM sensitivity check

| Model | Arm | False fix claims / 24 | Missed fixes / 16 | FIX_CLAIM within 42 UNCERTAIN |
|---|---|---:|---:|---:|
| GPT-4o-mini | binary_state | 1/24 | 15/16 | 0 |
| GPT-4o-mini | raw_metadata | 0/24 | 0/16 | 0 |
| GPT-4o-mini | closure_aware | 0/24 | 2/16 | 18 |
| Gemma | binary_state | 0/24 | 16/16 | 0 |
| Gemma | raw_metadata | 0/24 | 3/16 | 0 |
| Gemma | closure_aware | 1/24 | 1/16 | 20 |

Full Wilson intervals for both score sources are in `fix_claim_by_true_status.csv`. `fix_claim_case_scores.csv` retains all 492 case/arm scores with their status and response hash.

## Files, reproducibility, and pending work

- `provisional_routing_rates.csv` and `provisional_routing_paired_tests.csv`: lexical routing rates and paired tests.
- `provisional_statistics.json`: all provisional counts and statistical outputs.
- `true_status_registry.csv` and `uncertain_status_cases.csv`: evidence, source, reason, and status for every case.
- `tracker_refresh_summary.json`: the two refreshed closure histories and specific supporting links.
- `analysis_manifest_20261101.json`: source hashes, unchanged-file checks, amendments, and output hashes.

Authorized Steps 1–3 are complete. The intended primary human routing audit remains pending. Steps 4–10 in the user’s 1 November list are deferred until after Masaryk. No taxonomy-only arm, third generator/judge, specific-reason scorer, prevalence split, table recomputation, retrieval ablation, or release package was started in this phase. The manuscript remains unchanged.
