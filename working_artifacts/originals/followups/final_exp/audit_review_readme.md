# Readable human-audit workbook

Use audit_review.xlsx for annotation. It preserves the 140 record IDs, original shuffled order, applicability rules, and research scoring definitions. The original audit_sheet.csv is unchanged.

The Review tab shows readable tracker facts beside each response. The original words and citation URLs in responses are preserved; Markdown link punctuation is normalized for reading. Tracker fields are rendered as plain facts rather than serialized JSON. The closing-comment evidence for Nextcloud #3425 is preserved in full. Blue record IDs link to the original tracker when a source URL exists. The Guide tab contains the labeling definitions.

Only answer and notes cells are unlocked. Inapplicable NA cells, source text, IDs, and progress formulas are locked against accidental edits. Filtering and row/column resizing remain available. Dropdowns offer Yes, No, or Unsure. Unsure is unresolved, not a negative label, and does not count as completed.

The visible first question is phrased positively as “Claims a fix?” for readability. Its coding is inverted when converted back to the registered NO_FALSE_FIX metric: Yes becomes NO, and No becomes YES. The other three questions retain their original direction. ASKS_DETAILS and SAYS_DUPLICATE Yes/No values become 1/0. The exact column/value mapping and original/display text hashes are in audit_review_layout.json. No experiment definition or model output has been changed.

Save the workbook after labeling. It can be read directly for analysis; the user does not need to export CSV. A later import must validate all IDs, displayed response hashes, and NA applicability before accepting labels. It must preserve Unsure or blanks as unresolved and report them explicitly.

No arm identifiers, model comparisons, automated scores, or answer key are included in the workbook. The change is a user-requested presentation redesign, not an analysis or a new experiment.
