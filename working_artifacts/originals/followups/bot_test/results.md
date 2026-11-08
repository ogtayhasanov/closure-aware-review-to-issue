# Bot-closure experiment results

**Automated results, provisional pending the blind human audit.**

## Design and completeness

- Sample: 50 BOT (25 Signal, 25 Jitsi) and all 30 eligible HUMAN issues (3 Signal, 27 Jitsi).
- Bot experiment: 320 complete responses per generator, 640 total. Main Gemma rerun: 246 responses. Historical responses scored without regeneration: 246.
- All 1,132 responses have blinded judge and frozen lexical scores. No missing response was replaced with a lexical score.
- Model A: gpt-4o-mini-2024-07-18. Model B: Gemma 4 26B A4B Instruct (approved amendment). Judge: GPT-5.4 nano, reasoning off, temperature 0 (approved amendment).
- Same system/user text across providers. Temperature 0 and output limit 220 for generation. Google native transport disables thinking; API seed omitted after compatibility endpoint rejection. Original main generation file remains unchanged.
- The OpenAI judge is not provider-independent of Model A. Interpret model comparisons with that limitation and the pending human audit.

## Per-model, group and arm rates

Cells show count / denominator (percentage; Wilson 95% confidence interval). FIX_CLAIM is a false claim for both sampled groups under the preregistered ground truth. DECLINED is erroneous for BOT and expected for HUMAN.

| Model | Group | Arm | DECLINED | FIX_CLAIM | INACTIVITY |
|---|---|---|---|---|---|
| A | BOT | RAW | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) | 0/50 (0.0%; 0.0–7.1) |
| A | BOT | RAW+CLOSER | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) | 0/50 (0.0%; 0.0–7.1) |
| A | BOT | TAXONOMY-V1 | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) | 0/50 (0.0%; 0.0–7.1) |
| A | BOT | TAXONOMY-V2 | 49/50 (98.0%; 89.5–99.6) | 0/50 (0.0%; 0.0–7.1) | 0/50 (0.0%; 0.0–7.1) |
| A | HUMAN | RAW | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| A | HUMAN | RAW+CLOSER | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| A | HUMAN | TAXONOMY-V1 | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| A | HUMAN | TAXONOMY-V2 | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| B | BOT | RAW | 23/50 (46.0%; 33.0–59.6) | 2/50 (4.0%; 1.1–13.5) | 2/50 (4.0%; 1.1–13.5) |
| B | BOT | RAW+CLOSER | 24/50 (48.0%; 34.8–61.5) | 0/50 (0.0%; 0.0–7.1) | 1/50 (2.0%; 0.4–10.5) |
| B | BOT | TAXONOMY-V1 | 50/50 (100.0%; 92.9–100.0) | 0/50 (0.0%; 0.0–7.1) | 0/50 (0.0%; 0.0–7.1) |
| B | BOT | TAXONOMY-V2 | 21/50 (42.0%; 29.4–55.8) | 0/50 (0.0%; 0.0–7.1) | 4/50 (8.0%; 3.2–18.8) |
| B | HUMAN | RAW | 18/30 (60.0%; 42.3–75.4) | 0/30 (0.0%; 0.0–11.4) | 2/30 (6.7%; 1.8–21.3) |
| B | HUMAN | RAW+CLOSER | 29/30 (96.7%; 83.3–99.4) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| B | HUMAN | TAXONOMY-V1 | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |
| B | HUMAN | TAXONOMY-V2 | 30/30 (100.0%; 88.6–100.0) | 0/30 (0.0%; 0.0–11.4) | 0/30 (0.0%; 0.0–11.4) |

## Paired BOT false-DECLINED comparisons

Two-sided exact McNemar tests. Holm correction is applied separately to each model’s three planned comparisons. Model A is primary; Model B is secondary.

| Model | Comparison | Pairs | V2-only errors | Comparator-only errors | Exact p | Holm p |
|---|---|---:|---:|---:|---:|---:|
| A | TAXONOMY-V2 vs RAW | 50 | 0 | 1 | 1 | 1 |
| A | TAXONOMY-V2 vs RAW+CLOSER | 50 | 0 | 1 | 1 | 1 |
| A | TAXONOMY-V2 vs TAXONOMY-V1 | 50 | 0 | 1 | 1 | 1 |
| B | TAXONOMY-V2 vs RAW | 50 | 7 | 9 | 0.803619 | 1 |
| B | TAXONOMY-V2 vs RAW+CLOSER | 50 | 5 | 8 | 0.581055 | 1 |
| B | TAXONOMY-V2 vs TAXONOMY-V1 | 50 | 0 | 29 | 3.72529e-09 | 1.11759e-08 |

## Judge versus lexical agreement

Cohen’s kappa is descriptive; lexical matching is not ground truth. Undefined kappa indicates no variation in the marginal labels.

| Scope | Question | N | Agreement | Kappa |
|---|---|---:|---:|---:|
| bot experiment | DECLINED | 640 | 99.7% | 0.9878 |
| bot experiment | FIX_CLAIM | 640 | 99.1% | -0.0042 |
| bot experiment | INACTIVITY | 640 | 98.6% | 0.0000 |
| all scored responses | DECLINED | 1132 | 98.2% | 0.9647 |
| all scored responses | FIX_CLAIM | 1132 | 97.9% | 0.8696 |
| all scored responses | INACTIVITY | 1132 | 97.3% | 0.4135 |

## FIX_CLAIM on historical and main rerun responses

These populations include genuinely resolved issues, so a FIX_CLAIM occurrence here is not automatically an error.

| Dataset | Arm | FIX_CLAIM (Wilson 95% CI) |
|---|---|---|
| historical | binary_state | 1/82 (1.2%; 0.2–6.6) |
| historical | raw_metadata | 20/82 (24.4%; 16.4–34.7) |
| historical | closure_aware | 34/82 (41.5%; 31.4–52.3) |
| main_gemma | binary_state | 1/82 (1.2%; 0.2–6.6) |
| main_gemma | raw_metadata | 11/82 (13.4%; 7.7–22.4) |
| main_gemma | closure_aware | 30/82 (36.6%; 27.0–47.4) |

Main Gemma rerun, FIX_CLAIM taxonomy vs raw: 82 pairs, taxonomy-only 19, raw-only 0, exact McNemar p = 3.8147e-06.

**Unavailable endpoint:** the original “specific closure reason conveyed” checker was not found. No replacement endpoint or associated test was invented. That part of Step 6 remains pending the original code or an approved definition.

## Blind human audit

blind_sheet.csv contains 339 shuffled responses: all 74 judge/lexical disagreements plus 265 randomly selected responses from the remaining 1058 (ceil of 25%; seed 20261024).
The sheet has no arm, group, issue identifier, model identifier, judge labels, or lexical labels. Responses can themselves mention issue information, which has not been redacted. Keep blind_key.csv closed until annotations are complete.

## Exclusions, failures, and completeness

Sample exclusions are fully listed in exclusions.csv. Generation failures and non-stop attempts are retained in request_failures.jsonl and attempt ledgers; none is silently dropped. See completion_audit.json for unresolved keys and main-run finish reasons.

Logged request/validation failures: 5. Earlier compatibility and truncation failures were retried under the documented provider adapter; complete final responses are analyzed.

## Observed primary pattern

Model A BOT false-DECLINED counts: RAW 50/50, RAW+CLOSER 50/50, TAXONOMY-V1 50/50, TAXONOMY-V2 49/50.
The automated primary result does not support the preregistered prediction that TAXONOMY-V2 would rarely make false-DECLINED claims. None of the three primary paired comparisons is significant after Holm correction.
For Gemma, TAXONOMY-V2 reduces false-DECLINED claims from 50/50 under TAXONOMY-V1 to 21/50. Its comparisons with RAW (23/50) and RAW+CLOSER (24/50) are not statistically significant after correction. Nonsignificance does not establish equivalence.
These automated results do not establish human-validated accuracy. The OpenAI judge/provider limitation and blind human audit remain material to interpretation.

