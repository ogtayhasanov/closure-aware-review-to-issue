# Routing annotation — Checkpoint 3

Label the two response sheets: `blind_sheet.csv` (GPT-4o-mini) and `gemma_blind_sheet.csv` (Gemma).
Each contains all 69 responses: 23 cases × three arms. Rows are independently shuffled and arm names are removed.
Use the sheets in this directory as the working copies. Keep the `blind_id` and `response` cells unchanged.
Save the labeled sheets as CSV in the same location when finished.

Do not open `blind_key.csv`, `gemma_blind_key.csv`, or `lexical_scores.jsonl` while annotating. These disclose conditions or secondary scores.
The response text is preserved exactly, including any citations. Blinding hides metadata, but wording can still suggest a condition.

Fill ASKS_DETAILS and SAYS_DUPLICATE as 1 (yes) or 0 (no) for every response. Judge only what the response says.
The hidden key will restrict each endpoint to its relevant case cohort in the later analysis.
Use U only if you genuinely cannot decide, and explain in notes. U is missing/uncertain, never a silent 0.

- **ASKS_DETAILS:** The response asks the user for specific missing information (steps to reproduce, logs, app version, device) or to add details to the issue. “Let us know if you have any questions” does not count. Merely mentioning diagnostic information without requesting it does not count.
- **SAYS_DUPLICATE:** The response says the problem is tracked in another issue or is a duplicate. Merely citing the retrieved issue does not establish another issue.
- **GIVES_CANONICAL:** SAYS_DUPLICATE, plus the canonical issue number or link. Step 2 found no supplied canonical target for these cases. Therefore this endpoint is descriptive only, and canonical correctness cannot be determined from these sheets. Enter U when the target cannot be established; use notes to record any apparent different-issue reference. Do not treat a citation to the retrieved issue itself as a canonical duplicate target.

The three label columns are deliberately blank initially. Your labels are primary; frozen lexical checks are secondary.
Do not use taxonomy class labels to decide whether a response is correct. This pass codes response behavior.
No outcomes or comparisons will be reported before your labels are available.

The source registry accounts for all 82 cases. The 59 cases outside NEEDS_INFO/REDIRECTED remain individually listed in `exclusions.csv`.
No routing case or response was excluded because of its text, length, or lexical score.

Lexical patterns were committed before scoring in `e163e4403204df517551eb9320b873862994252d`.
An earlier draft matched “The report already contains device details and logs” as a request. A synthetic check caught that noun/verb false positive, which was corrected and recommitted before any real response was scored.
GIVES_CANONICAL lexical values are null (unavailable), never assumed false; candidate references are retained separately.
No new model calls were made.

**Stopped at CHECKPOINT 3.** Label both sheets, then tell me when they are ready. Analysis and the true-status FIX_CLAIM split remain pending.
