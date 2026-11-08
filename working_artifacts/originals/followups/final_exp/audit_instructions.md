# Fair-response human audit

The audit_sheet.csv contains 140 GPT-4o-mini responses: 35 cases × four hidden arms. Seed 20261024 determines row order. Nextcloud #2131 is excluded because its final closure was a merged fix. No other audit case or response is omitted.

Fill YES or NO in NO_FALSE_FIX and STATES_OUTCOME. Fill 1 or 0 in applicable ASKS_DETAILS and SAYS_DUPLICATE cells. Keep prefilled NA unchanged. Explain uncertainty in notes and leave an unresolved label blank rather than guessing. Keep sheet_id, issue_url, tracker_evidence, and response unchanged. Save CSV in this directory when done.

- NO_FALSE_FIX: YES if the response does not say or imply that the problem is fixed, resolved or coming in an update. A negated fix claim does not count as a fix claim.
- STATES_OUTCOME: YES if it states the specific outcome supported by the tracker evidence, such as duplicate, missing information/cannot reproduce, not planned/invalid, or inactivity. “The issue is closed” alone is NO. Use the supplied tracker facts, not taxonomy words in the generated response. If the evidence does not establish a proposed cause, do not assume the response is correct.
- ASKS_DETAILS: asks for specific missing information (reproduction steps, logs, app version, device), or asks the user to add details to the issue. Generic invitations for questions do not count.
- SAYS_DUPLICATE: says it is tracked in another issue or is a duplicate. Citing the retrieved issue itself is insufficient.

For Nextcloud #3425 the sheet includes the actual closing-comment context (Samsung battery restrictions and logs), a human close event, and no linked closing fix in the complete refreshed timeline. Do not equate a generic completed state with a code fix.

Empty issue_url cells reflect URLs absent from the archived source, not missing rows. Tracker and issue number remain in tracker_evidence. The original source has reconstructed metadata and truncated body excerpts; the evidence text explicitly identifies unknown closing actors/links where unavailable.

Do not open audit_key.csv, audit_lexical_scores.csv, audit_auto_scores.csv, or judge_audit_scores.jsonl while labeling. Wording may suggest a condition even though the arm field is hidden. Earlier aggregate results already seen by the annotator must be disclosed when describing independence of this audit.

Your labels are primary. Automated scores are supplementary. The primary two-test Holm family will be completed only after these labels arrive.
