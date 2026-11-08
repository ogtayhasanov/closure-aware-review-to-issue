
Existing outputs and inputs only. No response scoring or new generation. All 82 cases are accounted for.

## Files and matching
# Fair routing setup — Checkpoint 2

- fair_responses: `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\private_working\new_responses_246.jsonl`
- cases: `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\private_working\real_82_native_staged.jsonl`
- fair_saved_inputs: `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\private_working\fair_prompts_246_dryrun.jsonl`
- protocol: `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\rq3_protocol.py`
- gemma_responses: `C:\Users\Ogtay\Documents\Codex\2026-10-24\check-x20\outputs\bot_test\main_responses_gemma.jsonl`

The saved 246 message records exactly match the original renderer applied to the 82 staged cases. All 246 prompt hashes match both the GPT-4o-mini fair responses and the Gemma main rerun. Both models have one complete response for every case/arm pair. The shared system prompt is identical in all arms. A full input snapshot is in `fair_inputs_snapshot.jsonl`; source hashes are in `setup_manifest.json`.

## Class source for all 82 cases

`case_registry.csv` lists every case, selected class/subtype, source, cohort membership, and exclusions. All 82 use the class supplied to the taxonomy arm, explicitly flagged `taxonomy_arm_input_fallback`. These labels select routing cohorts only. They are not correctness ground truth or proof of true fix status.

The completed taxonomy workbook has 120 assignments (70 AnkiDroid, 50 Signal), with zero matching fair-run issues. Its downloaded copy has the same coverage. The independent second-annotator fields are blank. The completed 72-row status workbook labels earlier generated responses for status correctness; its expected class column is prefilled, not a new human class adjudication. It cannot supply independently corrected classes for this step. The fair-run 82-row quality worklist has blank verification/reference columns. See `annotation_inventory.json`.

| Class | Subtype | Cases |
|---|---|---:|
| ABANDONED | NEEDS_INFO | 16 |
| ABANDONED | OTHER | 2 |
| ABANDONED | STALE | 5 |
| OPEN | OPEN | 11 |
| REDIRECTED | duplicate | 7 |
| REJECTED | invalid | 5 |
| REJECTED | notvlc | 1 |
| RESOLVED | fixed | 35 |

## Routing populations and exclusions

**NEEDS_INFO: 16. REDIRECTED: 7. Both equal the paper’s denominators.** The original final-RRF 36-case diagnostic contains the same 36 audit case IDs. These are 23 case-response pairs per arm, 69 responses per model for the prospective blind sheets.

The other 59 cases remain in the registry and appear individually in `exclusions.csv`: 35 RESOLVED/fixed, 11 OPEN, 6 REJECTED, 5 ABANDONED/STALE, and 2 ABANDONED/OTHER. Their reason is outside the two routing cohorts. None was excluded because of its generated response.

The 16 NEEDS_INFO inputs have eight WORKSFORME/worksforme resolutions, four INCOMPLETE/incomplete resolutions, and four Nextcloud `needs info/discussion` labels. WORKSFORME is treated here as a cannot-reproduce signal, as grouped by the supplied cohort definition, not as proof that the reporter failed to provide details. The original case source remains marked reconstructed and unverified.

## Reconciling 34 and 36

The fair input file, original validation rule, saved audit flags, historical diagnostic, and paper all retain **36 taxonomy-defined closed non-resolved cases** (23 ABANDONED + 7 REDIRECTED + 6 REJECTED). There is no missing response or missing case in the fair run.

A 34-case set results if the two ABANDONED/OTHER fallbacks are excluded: **Nextcloud #3425** (`87831fab6bcb4385370984002df5fd01c47237340bab72d52d0ffc1be943515d`) and **Nextcloud #2131** (`fdb3e658e38d05422ec9cd14d85214590bc61d1b87394fc6d434493865fcfa97`). Their archived closure signal says GitHub enrichment failed with API 403/rate limit and no confirmed resolution. They have only closed state and ordinary bug/feature labels in the retained input. The staging code marks `CLOSING_REASON_UNAVAILABLE_API_RATE_LIMIT` and `UNKNOWN_CLOSING_REASON_AS_ABANDONED_OTHER_GOLD`. Thus 34 evidence-bearing cases versus 36 taxonomy-assigned cases explains the numerical difference. **I did not locate a saved selection rule or case list for the earlier 34-case check, so this is a reproducible reconciliation, not a verified reconstruction of that earlier check.** These two remain visible here; they must not become NOT FIXED in Step 5 solely from ABANDONED/OTHER.

Also, the paper’s **34/36** is a count of status-correct responses, not a 34-case population. The saved paper excerpt distinguishes the numerator from the 36-case audit denominator.

## Evidence available to each arm

The table counts case-specific closure signals in the user message. The shared system message contains generic conditional instructions about asking for details and routing duplicates in every arm. Those instructions do not identify an individual case’s outcome. Empty fields in a body template are recorded separately in the detailed audit and are not treated as evidence of why an issue was closed.

| Population | Arm | n | Missing info / cannot reproduce signal | Duplicate closure signal | Canonical target |
|---|---|---:|---:|---:|---:|
| ALL | binary_state | 82 | 0 | 0 | 0 |
| ALL | raw_metadata | 82 | 19 | 7 | 0 |
| ALL | closure_aware | 82 | 19 | 7 | 0 |
| NEEDS_INFO | binary_state | 16 | 0 | 0 | 0 |
| NEEDS_INFO | raw_metadata | 16 | 16 | 0 | 0 |
| NEEDS_INFO | closure_aware | 16 | 16 | 0 | 0 |
| REDIRECTED | binary_state | 7 | 0 | 0 | 0 |
| REDIRECTED | raw_metadata | 7 | 0 | 7 | 0 |
| REDIRECTED | closure_aware | 7 | 0 | 7 | 0 |

Raw metadata provides the missing-info/cannot-reproduce signal for all 16 NEEDS_INFO cases and the native duplicate resolution for all seven REDIRECTED cases. Taxonomy inputs retain the same raw fields and append normalized class/subtype/action fields. Binary inputs omit those closure blocks. The all-82 total of 19 missing-info signals includes three cases outside the NEEDS_INFO cohort: Nextcloud #3376 and #5910 (STALE, with both stale and needs-info labels), and #6443 (OPEN, with a needs-info label). Those labels do not silently change the registered cohort membership. VLC #20777’s review says “duplicate” in a user complaint, which is retained in all arms; it does not assert that the retrieved issue is a duplicate. The literal mention is flagged separately.

**No canonical duplicate target number or link is supplied in any arm for any of the seven REDIRECTED cases.** No taxonomy-only canonical reference exists. The retrieved issue’s own number is not its canonical target; the QA column `canonical_display_id` corrects the retrieved issue ID and does not name a duplicate target. Likewise numeric pandas row indexes in truncated body text are not target issue references.

Consequently GIVES_CANONICAL does not qualify as a comparative test under the registered rule. It can only be descriptive, and target correctness cannot be established from these inputs. SAYS_DUPLICATE remains scoreable under the new fixed definition.

The inspected paper describes the old 7/7 routing endpoint as explicitly saying tracked elsewhere or directing users to related discussion. It does not require a canonical number and explicitly says that merely stating “duplicate” did not count. The new SAYS_DUPLICATE definition does count an explicit duplicate statement, so the new endpoint is broader than that old descriptive endpoint. The new fixed definition is preserved.

Per-case/per-arm evidence quotations and flags are in `input_evidence_audit.csv` (246 rows). No generation outcomes were examined to decide these flags.

**Stopped at CHECKPOINT 2.** No routing lexical patterns, blind sheets, response scores, or statistical analysis have been created.
