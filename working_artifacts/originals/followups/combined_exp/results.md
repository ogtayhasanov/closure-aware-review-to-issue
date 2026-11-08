# RAW+MEANING and provenance-switch results

Instructions were committed before construction as `48d8b42`; interval and score-reuse methods were recorded as `1fd3aa8`. All 162 input checks passed. Both generators returned all 162 nonblank, stop-finished responses with the registered model IDs and exact settings. The shared system prompt is unchanged. Original prompts, responses, scores and the paper are unchanged.

## Primary tests

| Test | A positive | RAW positive | A only | RAW only | Exact McNemar p | Holm p |
|---|---:|---:|---:|---:|---:|---:|
| 1: BOT false DECLINED | 50/50 | 50/50 | 0 | 0 | 1 | 1 |
| 2: audit STATES_OUTCOME | 31/35 | 33/35 | 1 | 3 | 0.625 | 1 |

A is RAW+MEANING. DECLINED is an erroneous attributed maintainer rejection in the provenance-defined BOT cohort, so lower is better. STATES_OUTCOME is evidence-supported correctness, so higher is better. Holm covers exactly these two tests.

gpt-4o-mini-2024-07-18: STATES_OUTCOME difference RAW+MEANING minus RAW = -5.71 percentage points; paired-bootstrap 95% CI [-17.14, +5.71] points (35 pairs, 200,000 replicates, seed 20261024).
gemma-4-26b-a4b-it: STATES_OUTCOME difference RAW+MEANING minus RAW = +0.00 percentage points; paired-bootstrap 95% CI [-11.43, +11.43] points (35 pairs, 200,000 replicates, seed 20261024).

A non-significant test does not establish equivalence. The bootstrap interval resamples whole cases and is discrete at this sample size.

## BOT cohort: 50 issues per model

| Model | Arm | False DECLINED | INACTIVITY / automatic closure |
|---|---|---|---|
| gpt-4o-mini-2024-07-18 | RAW | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | TAXONOMY-ONLY | 12/50 (24.0%; 14.3–37.4) | 39/50 (78.0%; 64.8–87.2) |
| gpt-4o-mini-2024-07-18 | RAW+MEANING | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | SWITCH | 12/50 (24.0%; 14.3–37.4) | 39/50 (78.0%; 64.8–87.2) |
| gemma-4-26b-a4b-it | RAW | 23/50 (46.0%; 33.0–59.6) | 2/50 (4.0%; 1.1–13.5) |
| gemma-4-26b-a4b-it | TAXONOMY-ONLY | 0/50 (0.0%; 0.0–7.1) | 20/50 (40.0%; 27.6–53.8) |
| gemma-4-26b-a4b-it | RAW+MEANING | 0/50 (0.0%; 0.0–7.1) | 22/50 (44.0%; 31.2–57.7) |
| gemma-4-26b-a4b-it | SWITCH | 0/50 (0.0%; 0.0–7.1) | 20/50 (40.0%; 27.6–53.8) |

Rate intervals are Wilson 95%. These BOT correctness labels use tracker closing-actor/linked-fix provenance, not received taxonomy classes. INACTIVITY uses the frozen definition that also includes automatic closure.

## Fair audit: 35 cases per model

| Model | Arm | STATES_OUTCOME | NO_FALSE_FIX | ASKS_DETAILS (16) | SAYS_DUPLICATE (7) |
|---|---|---|---|---|---|
| gpt-4o-mini-2024-07-18 | RAW | 33/35 (94.3%; 81.4–98.4) | 35/35 (100.0%; 90.1–100.0) | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |
| gpt-4o-mini-2024-07-18 | TAXONOMY-ONLY | 23/35 (65.7%; 49.2–79.2) | 35/35 (100.0%; 90.1–100.0) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |
| gpt-4o-mini-2024-07-18 | RAW+MEANING | 31/35 (88.6%; 74.0–95.5) | 35/35 (100.0%; 90.1–100.0) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |
| gpt-4o-mini-2024-07-18 | SWITCH | 29/35 (82.9%; 67.3–91.9) | 35/35 (100.0%; 90.1–100.0) | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |
| gemma-4-26b-a4b-it | RAW | 31/35 (88.6%; 74.0–95.5) | 35/35 (100.0%; 90.1–100.0) | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |
| gemma-4-26b-a4b-it | TAXONOMY-ONLY | 21/35 (60.0%; 43.6–74.4) | 35/35 (100.0%; 90.1–100.0) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |
| gemma-4-26b-a4b-it | RAW+MEANING | 31/35 (88.6%; 74.0–95.5) | 35/35 (100.0%; 90.1–100.0) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |
| gemma-4-26b-a4b-it | SWITCH | 29/35 (82.9%; 67.3–91.9) | 35/35 (100.0%; 90.1–100.0) | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |

STATES_OUTCOME uses only the unchanged tracker evidence and response; no arm or taxonomy class is given to the judge. NO_FALSE_FIX is the opposite of FIX_CLAIM. Frozen lexical checks are secondary and recorded in `scores_all_arms.csv`; STATES_OUTCOME has no lexical score. Cohort applicability is retained from the earlier audit, without treating it as correctness truth.

## Secondary tests, uncorrected

| Model | Contrast | Question | Pairs | A only | B only | Exact p |
|---|---|---|---:|---:|---:|---:|
| gpt-4o-mini-2024-07-18 | RAW+MEANING vs TAXONOMY-ONLY | DECLINED | 50 | 38 | 0 | 7.2759576e-12 |
| gpt-4o-mini-2024-07-18 | RAW+MEANING vs TAXONOMY-ONLY | STATES_OUTCOME | 35 | 8 | 0 | 0.0078125 |
| gemma-4-26b-a4b-it | RAW+MEANING vs RAW | DECLINED | 50 | 0 | 23 | 2.3841858e-07 |
| gemma-4-26b-a4b-it | RAW+MEANING vs RAW | STATES_OUTCOME | 35 | 2 | 2 | 1 |
| gemma-4-26b-a4b-it | RAW+MEANING vs TAXONOMY-ONLY | DECLINED | 50 | 0 | 0 | 1 |
| gemma-4-26b-a4b-it | RAW+MEANING vs TAXONOMY-ONLY | STATES_OUTCOME | 35 | 10 | 0 | 0.001953125 |

## Switch provenance and coverage

The rule switches 50/80 bot-test inputs and 5/82 fair inputs, identically for both generators. All switch outputs are existing responses; no switch generation was performed. GitHub API issue records and complete REST timelines were refreshed for all 33 GitHub-hosted fair inputs. Other trackers (49) retain RAW. The five switching fair inputs are Nextcloud #3376, #2555, #4054, #4660, and #6443. All have a final bot closure and no commit/PR references in the complete returned timeline.

Nextcloud #5910 is currently open; its historical bot closure does not trigger the switch. The repeated retrieved issue #5454 occurs in four distinct fair inputs and #2152 in two; all distinct case IDs remain separate. Bot-test provenance is taken from sample.csv, with absence of linked closers verified against the matching sample_records.jsonl. The frozen extra bot list contains automated-signal. No received taxonomy class is consulted for switching.

Nextcloud #2131 is retained in generation and all score ledgers, but explicitly excluded from every analysis because verified PR #4470 fixed it. This leaves 81 fair inputs and the unchanged 35-case audit. No other case or response is excluded. Rates for HUMAN bot-test cases (30), the full included fair set (81), and INACTIVITY in all cohorts are in rates.csv. Switch selections, reasons and API provenance are retained individually.

All required combined, switch and audit-comparator scores are complete. The comprehensive ledger retains 102 additional original RAW rows with routing judgments marked NA because those judgments were not needed for these comparisons or switch selections. Their core and lexical scores remain present. STATES_OUTCOME is NA outside the 35-case audit; it is never silently coded false.

## Conditional blind human check

Test 2 has 4 discordant case pairs. Its blind sheet contains 8 shuffled responses and exactly 8 STATES_OUTCOME answers, with arms and automated answers hidden. The key is separate. Human labels are pending. This selected sheet does not estimate population agreement.

## Interpretation and limitations

The expected GPT bot improvement was not observed: 50/50 false DECLINED in both RAW+MEANING and RAW, with no automatic/inactivity statements. Gemma shows a different secondary result: 23/50 to 0/50 false DECLINED. The effect differs by generator. Fair-case RAW denotes the original raw_metadata arm. The switch scores 29/35 on STATES_OUTCOME for both models and therefore loses detail versus RAW; bot provenance alone does not ensure that a class/meaning-only response preserves a specific recorded closure reason.

The combined contrast adds the plain-language class/meaning block while retaining raw fields; it cannot isolate class codes from explanations. The switch is a deterministic post-processing policy on existing responses and is reported descriptively. Automated judge results are primary under the existing amendment; earlier human labels concern a different selected comparison and are not transferred to new responses. The same-provider GPT judge/generator limitation remains. Agreement between judge and lexical checks is not correctness validation.
