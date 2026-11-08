# Automated checks and later human agreement

The original three-question bot judge prompt is reused byte for byte with the same requested model, reference model snapshot, temperature, reasoning setting, and 80-token limit. The original bot lexical.py is unchanged. The original routing lexical.py is unchanged, including its documented false-positive limitations.

ASKS_DETAILS and SAYS_DUPLICATE require an additional two-question judge prompt because the old bot judge did not score those endpoints. Their definitions are copied from the user's registered routing definitions. This additional response-only pass uses the same GPT-5.4 nano model and settings and is logged separately. Every new response receives both passes.

For agreement with the user's later NO_FALSE_FIX and STATES_OUTCOME labels, an additional evidence-based audit pass covers all 140 fair-audit responses, with generation arm and taxonomy class withheld. The judge receives only the response and raw tracker evidence, including actual closing actors/links and #3425's recorded closing comment. NO_FALSE_FIX follows the exact user definition, even though its name might otherwise suggest a conditional metric. These are supplemental automated labels, not human labels.

The supplemental lexical STATES_OUTCOME screen uses native resolution codes, literal raw labels, closing-event facts, and recorded closing-comment evidence. It does not consult received_l1_class, subtype, action, generation arm, or the TAXONOMY-ONLY meaning. NO_FALSE_FIX is the inverse of the frozen lexical FIX_CLAIM. ASK/DUP checks use the original frozen routing patterns. The screen is secondary and its evidence-matching limitations will be reported.

The response-only routing pass also covers the old audit responses so that judge agreement can be computed for all applicable audit rows. Already scored identical response text is reused by exact SHA-256 with the same judge prompt/model; all reuse links are logged. Other audit responses receive the same two-question response-only routing pass. This does not change definitions or expose tracker evidence to that pass.

Nextcloud #2131 is generated and scored for completeness but excluded from every analysis. Every other registered case is retained. No statistical tests or human-audit rates will be substituted for the user's pending primary labels. The primary Holm family will not be completed until those labels arrive.

The corpus is sent only to the already authorized generation/judge providers. No credentials are stored in request/response ledgers or the release. The temporary encrypted credential directory is excluded from Git and release packaging.
