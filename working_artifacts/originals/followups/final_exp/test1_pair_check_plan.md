# Second short check: test 1 discordant pairs

User request: make a second blind sheet with only the 24 responses from the 12 discordant pairs in test 1, shuffled, with only STATES_OUTCOME as a label column. Also report judge–lexical agreement on DECLINED for the new TAXONOMY-ONLY bot responses.

Select the 12 cases where the existing primary judge STATES_OUTCOME scores differ between TAXONOMY-ONLY and raw_metadata. Retain both responses from each case; no other arm or case is included. Sort by case ID and arm, shuffle all 24 responses using seed 20261024, and assign fresh neutral IDs after shuffling. Preserve the exact original issue_url, tracker_evidence, and response. The sheet has four context columns (sheet_id, issue_url, tracker_evidence, response) and one blank answer column, STATES_OUTCOME. A separate key retains source IDs, pair/case links, and arms. No model call, lexical change, or score correction is needed.

This is a second sheet; prior sheets and primary automated results remain unchanged. Its human results concern a deliberately selected judge-discordant subset, not overall accuracy or an unbiased estimate for all 35 cases.

For DECLINED agreement, use the already frozen judge and lexical flags in auto_scores.csv, authenticated against the new response hashes. Report the 50 BOT cases separately for each generator as the main comparison. Also report the 30 HUMAN and all-80 bot-test strata separately to remove ambiguity about the phrase “bot responses.” Include 2×2 counts, observed agreement, Wilson 95% interval, and Cohen's kappa. If both scorers are constant and expected agreement is one, kappa is undefined, not zero or one. Agreement between automated procedures is not accuracy against human truth.
