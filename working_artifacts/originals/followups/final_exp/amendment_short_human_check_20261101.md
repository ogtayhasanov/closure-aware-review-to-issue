# User amendment: automated primary scores and a short human check

User instruction, received 1 November 2026. Commit before scoring or selecting the short sheet.

Replace the full human audit with automated scoring plus a short human check.

1. Score STATES_OUTCOME with the same judge, using the definition in Step 3. Give the judge only the tracker evidence and the response, with no arm. NO_FALSE_FIX is the opposite of FIX_CLAIM. Keep the existing scores for ASKS_DETAILS and SAYS_DUPLICATE.
2. Make a short blind sheet: every response where the judge and the lexical check disagree on any question, plus 20 random others (seed 20261024). Remove the arm. Use the same columns as Step 3.
3. In Step 6, use the judge scores as primary, and report their agreement with the user's labels on the short sheet.

## Implementation fixed before selection

- Retain the registered 35-case / 140-response GPT-4o-mini audit population and all prior exclusions. Nextcloud #2131 remains excluded from every analysis.
- Reuse the completed STATES_OUTCOME judge pass only after verifying its prompt, evidence/response input, lack of arm metadata, reference model snapshot, and hashes. No new call is needed if those checks pass.
- NO_FALSE_FIX is calculated as the logical opposite of the saved response-only FIX_CLAIM judge flag. The earlier separate NO_FALSE_FIX audit judgment is retained as provenance but does not replace that calculation.
- Preserve the existing ASKS_DETAILS and SAYS_DUPLICATE judge and frozen lexical scores, applying each only to its registered cohort. NA cells never create disagreements.
- Select the union of responses with at least one disagreement on an applicable, assessable question. Include any response with an unavailable applicable automated score as a visible unresolved case rather than silently omitting it; document this separately in the key and manifest.
- Sort remaining responses by the existing sheet_id, sample 20 without replacement using Python random.Random(20261024), then shuffle the combined selection using that same random generator. If fewer than 20 remain, retain all remaining responses and report the shortfall explicitly.
- Preserve the original shuffled audit IDs and exact tracker_evidence and response strings. The short sheet has the same columns as Step 3 and contains no arm, automated score, disagreement flag, or selection reason. Those mappings stay in a separate key. Human label cells remain blank, with the original inapplicable NA cells retained.
- Automated rates and the registered primary two-test Holm family may now be computed using judge scores. Agreement with the short human check remains pending. Agreement on this deliberately disagreement-enriched sample is not population-wide agreement; report selection strata and denominators.
- Do not alter prior prompts, responses, frozen lexical rules, existing scores, the old audit sheets, or the manuscript. Put new outputs in final_exp/.
