# User-authorized provisional analysis — 1 November 2026

The user authorized Steps 1–3 without waiting for human response labels: refresh Nextcloud #3425 and #2131, report the frozen lexical routing checks provisionally, and split existing FIX_CLAIM scores by tracker-supported status. Steps 4–10 in the user's new list are deferred until after Masaryk. No new generation or judging is authorized or needed for this phase.

The earlier blind sheets remain available and unchanged for later human annotation. Human response labels remain the intended primary analysis. The lexical-only report is explicitly provisional; it will not be described as human validation. Use the already committed routing lexical version unchanged, including its limitations. GIVES_CANONICAL remains descriptive/unassessable without canonical target evidence in the original inputs.

Routing reporting follows the registered case cohorts (16 NEEDS_INFO and 7 REDIRECTED), all three arms, Wilson 95% confidence intervals, and exact two-sided McNemar comparing taxonomy with raw. Holm adjustment is across ASKS_DETAILS and SAYS_DUPLICATE separately within each generator. Binary is reference only. No lexical patterns will be changed after observing results. Agreement with human labels is unavailable until annotation.

For Step 5, the user's amendment replaces the unavailable independent human class assignments with tracker evidence:

- FIXED: a closed Bugzilla/Trac case with native resolution FIXED/fixed, or a specifically verified GitHub closing commit/merged fix PR. Generic GitHub completed state, taxonomy RESOLVED, milestone, and ordinary bug labels are insufficient.
- NOT FIXED: closed cases with native resolution WORKSFORME, INCOMPLETE, INVALID, or DUPLICATE (case-insensitive), exactly the codes requested by the user.
- UNCERTAIN: everything else. In particular, notvlc, stale/needs-info labels alone, open cases, manual configuration-advice closure, and unverified GitHub completed cases do not silently become NOT FIXED or FIXED.

All 82 input cases remain in the status registry, including repeated retrieved issues paired with different reviews. Native codes are taken from the retained tracker fields, whose original reconstructed/unverified provenance is preserved. The two refreshed issues have current issue snapshots, full comments, and complete timeline pages retained as additional evidence. Any GitHub FIXED override must cite a merged fix PR explicitly closing the case and temporally matching its final closure. The supplementary refresh does not replace or repair any original generation input, cohort assignment, or response.

Reuse the existing bot_test FIX_CLAIM judge scores for all 246 GPT-4o-mini fair responses and 246 Gemma main-rerun responses, authenticated by response hash. Report the already saved lexical FIX_CLAIM scores separately as a sensitivity check. False-fix denominator is NOT FIXED; missed-fix denominator is FIXED. Report UNCERTAIN explicitly, including its FIX_CLAIM occurrences without treating them as false claims. Missing or duplicate judgments must cause a visible failure, never an implicit negative label.

These are tracker-status errors, not a test of whether every response was faithful to its supplied evidence. A newly verified fix may have been absent from the frozen input. No taxonomy value serves as correctness ground truth. No human labels are fabricated. No manuscript edits are made.
