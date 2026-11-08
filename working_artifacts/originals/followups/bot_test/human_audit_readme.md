# Blind human audit

Open `blind_sheet.csv` and keep `blind_key.csv` closed until all annotations are finished. Do not consult the model responses by condition, sample groups, or automated labels while annotating.

For each response, enter `yes` or `no` in all three columns:

- **DECLINED:** says or implies that the developers decided not to fix or build it, rejected it, or marked it "won't fix" as their decision.
- **FIX_CLAIM:** says the problem is fixed, resolved, or coming in an update.
- **INACTIVITY:** says it was closed for inactivity, for no recent activity, or automatically.

Judge what the response says. Do not infer the issue's real status from outside information. A negated assertion (for example, "not fixed") does not affirm a fix. Use the notes column for ambiguity. Preserve all rows and blind IDs.

The sheet includes every response where automated judge and lexical diagnostic disagree on at least one question, plus a random 25% of the remaining responses, rounded up. Rows are shuffled with seed 20261024. Neither automatic labels nor the reason for selection is displayed.

The current `results.md` reports automated judge labels and remains provisional until this audit is completed. Review all selected rows before revealing the key; keep an unchanged copy of the original blank sheet.
