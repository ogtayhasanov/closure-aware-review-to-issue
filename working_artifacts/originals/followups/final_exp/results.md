# Final experiments: automated primary results

User amendment committed as `dbfeb186e02996c4749b1ef67caf54e5d01fff18` before recombining scores or selecting the short human check. Judge scores are primary under this amendment. Human agreement remains pending; these are not human-validated results.

## Main findings

The expected reduction in bot false-decline claims is observed: GPT-4o-mini falls from 50/50 under RAW to 12/50 under TAXONOMY-ONLY (Holm p = 1.45519e-11). Gemma falls from 23/50 to 0/50 (secondary, uncorrected p = 2.38419e-7). Automatic/inactivity statements increase from 0/50 to 39/50 for GPT-4o-mini and from 2/50 to 20/50 for Gemma.

**The expected fair-case match on STATES_OUTCOME is not supported by the primary judge:** TAXONOMY-ONLY scores 23/35 versus 33/35 for raw_metadata, a lower observed success rate (Holm p = 0.00634766). NO_FALSE_FIX is 35/35 in both arms. This is an observed tie on that question, not proof of equivalence. The short human check is necessary to assess judge error; 47 of the judge/lexical disagreements concern STATES_OUTCOME and are not automatically judge mistakes.

## Fair-response audit (35 cases × four arms)

STATES_OUTCOME reuses the verified GPT-5.4 nano pass that received only tracker evidence and the response. NO_FALSE_FIX is the logical opposite of the response-only FIX_CLAIM judge flag. The earlier independent NO_FALSE_FIX audit judgment is not substituted for this calculation. Existing ASKS_DETAILS and SAYS_DUPLICATE scores and cohort applicability are preserved. Entries show count/denominator, percentage, and Wilson 95% interval.

| Arm | NO_FALSE_FIX | STATES_OUTCOME | ASKS_DETAILS | SAYS_DUPLICATE |
|---|---|---|---|---|
| binary_state | 35/35 (100.0%; 90.1–100.0) | 20/35 (57.1%; 40.9–72.0) | 14/16 (87.5%; 64.0–96.5) | 1/7 (14.3%; 2.6–51.3) |
| raw_metadata | 35/35 (100.0%; 90.1–100.0) | 33/35 (94.3%; 81.4–98.4) | 15/16 (93.8%; 71.7–98.9) | 7/7 (100.0%; 64.6–100.0) |
| closure_aware | 35/35 (100.0%; 90.1–100.0) | 30/35 (85.7%; 70.6–93.7) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |
| TAXONOMY-ONLY | 35/35 (100.0%; 90.1–100.0) | 23/35 (65.7%; 49.2–79.2) | 16/16 (100.0%; 80.6–100.0) | 7/7 (100.0%; 64.6–100.0) |

## Primary paired tests: Holm across exactly two

| Test | Pairs | A only | B only | Exact p | Holm p |
|---|---:|---:|---:|---:|---:|
| 1: STATES_OUTCOME, TAXONOMY-ONLY vs raw_metadata | 35 | 1 | 11 | 0.00634766 | 0.00634766 |
| 2: BOT false DECLINED, TAXONOMY-ONLY vs RAW, GPT-4o-mini | 50 | 0 | 38 | 7.27596e-12 | 1.45519e-11 |

For test 1, A/B-only cells are TAXONOMY-ONLY/raw successes. For test 2 they are TAXONOMY-ONLY/RAW false-decline errors. All tests are exact two-sided McNemar, paired by case. Non-significance does not establish equivalence.

## BOT responses: false decline and automatic/inactivity statements

The 50 BOT cases are selected from closing/label actor and linked-fix tracker provenance, not from taxonomy as correctness gold. The protocol treats an attributed maintainer decision not to fix as a false DECLINED claim in this cohort. INACTIVITY includes an explicit automatic/bot-closing statement under the frozen definition.

| Model | Arm | False DECLINED | INACTIVITY / automatic closing |
|---|---|---|---|
| gpt-4o-mini-2024-07-18 | RAW | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | RAW+CLOSER | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | TAXONOMY-V1 | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | TAXONOMY-V2 | 49/50 (98.0%; 89.5–99.6) | 0/50 (0.0%; 0.0–7.1) |
| gpt-4o-mini-2024-07-18 | TAXONOMY-ONLY | 12/50 (24.0%; 14.3–37.4) | 39/50 (78.0%; 64.8–87.2) |
| gemma-4-26b-a4b-it | RAW | 23/50 (46.0%; 33.0–59.6) | 2/50 (4.0%; 1.1–13.5) |
| gemma-4-26b-a4b-it | RAW+CLOSER | 24/50 (48.0%; 34.8–61.5) | 1/50 (2.0%; 0.4–10.5) |
| gemma-4-26b-a4b-it | TAXONOMY-V1 | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) |
| gemma-4-26b-a4b-it | TAXONOMY-V2 | 21/50 (42.0%; 29.4–55.8) | 4/50 (8.0%; 3.2–18.8) |
| gemma-4-26b-a4b-it | TAXONOMY-ONLY | 0/50 (0.0%; 0.0–7.1) | 20/50 (40.0%; 27.6–53.8) |

## Secondary comparisons (uncorrected)

| Comparison | Pairs | A only | B only | Exact p |
|---|---:|---:|---:|---:|
| closure_aware vs raw_metadata: NO_FALSE_FIX | 35 | 0 | 0 | 1 |
| closure_aware vs raw_metadata: STATES_OUTCOME | 35 | 1 | 4 | 0.375 |
| closure_aware vs raw_metadata: ASKS_DETAILS | 16 | 1 | 0 | 1 |
| closure_aware vs raw_metadata: SAYS_DUPLICATE | 7 | 0 | 0 | 1 |
| Gemma BOT false DECLINED: TAXONOMY-ONLY vs RAW | 50 | 0 | 23 | 2.38419e-07 |

These are explicitly secondary, uncorrected comparisons. Binary is a reference arm, not an additional primary test.

## TAXONOMY-ONLY FIX_CLAIM by tracker-supported true status

Nextcloud #2131 is excluded here as in every other analysis, leaving 81 fair inputs: 15 FIXED, 24 NOT FIXED, and 42 UNCERTAIN. The status registry comes from the earlier tracker-code/verified-fix rules. No taxonomy class is used as correctness truth. Retained native code provenance remains reconstructed/unverified where previously documented; generic GitHub completed cases remain UNCERTAIN without a specific verified fix.

| Model | False fixes / NOT FIXED | Missed fixes / FIXED | UNCERTAIN | Fix claims within UNCERTAIN |
|---|---|---|---:|---:|
| gpt-4o-mini-2024-07-18 | 0/24 (0.0%; 0.0–13.8) | 0/15 (0.0%; 0.0–20.4) | 42 | 20 |
| gemma-4-26b-a4b-it | 0/24 (0.0%; 0.0–13.8) | 2/15 (13.3%; 3.7–37.9) | 42 | 19 |

UNCERTAIN fix claims are not counted as false claims. Newly supplied meaning lines may contain claims not independently supported by a fix link; generated adherence to those lines is not itself proof of tracker correctness.

## Short human check and agreement

The short sheet contains **73 responses**: 53 mandatory responses plus 20 random others. There are 53 responses with a judge/lexical disagreement and 0 with an unavailable applicable score. It requires 196 applicable judgments instead of the full sheet’s 372.

The sheet preserves the Step 3 columns, exact responses/evidence, and NA applicability. It contains no arm, automated labels, or selection reason. The separate key records selection strata. Seed 20261024 and the precommitted ordering/sample/shuffle rule determine the 20 controls and final order.

Judge/human and lexical/human agreement and Cohen’s kappa are pending. Report them on this short selected sample, including disagreement and random-control strata separately; this enriched sample does not estimate overall population agreement. This fair-case check also does not independently validate the BOT DECLINED labels. Original prompts, responses, frozen lexical checks, previous sheets, and the paper remain unchanged. No new model calls were made for this amendment.

The encoding contrast replaces raw metadata with a class plus a plain-language explanation. Its effect cannot be attributed to class codes alone. Automated-primary findings are subject to judge error and the documented same-provider judge/generator limitation. The short human check will assess that error.

## Completed 24-response human check

The later 24-response blind check is complete: 24 YES/NO labels, no missing/unsure answers or exclusions, with exact response/evidence matches. Judge–human agreement is 18/24 (75.0%), κ = 0.5000; lexical–human agreement is 13/24 (54.2%), κ = 0.0571. These apply only to the 12 judge-discordant pairs selected from test 1. See `test1_human_check_results.md` for arm counts, contingencies, and limitations. The earlier 73-response sheet remains uncompleted; its pending agreement is not replaced with this selected-subset estimate. Primary automated results above remain unchanged.
