# Short human check — current annotation task

The full 140-response audit is superseded by the committed amendment. The current check has 73 responses: all 53 responses with a judge/lexical disagreement, plus 20 randomly selected others (seed 20261024). There are 196 applicable answers. No response was silently removed from the full automated analysis.

Open audit_short_review.html in your browser. It works locally, one response at a time. Read the tracker facts and response, then press Y for Yes, N for No, or U for Unsure. The highlight moves to the next applicable question and then automatically to the next response. Use left/right arrows to go back or forward. You can click a question to revise its answer. Notes are optional; Escape leaves the notes box and restores the shortcuts.

Progress saves in that browser for this exact form file. Keep using the same file and browser when you resume. Click Export labels when finished; it downloads audit_short_labeled.csv. If some answers remain blank or Unsure, the filename is audit_short_partial.csv. Uncertain answers remain unresolved and are noted, never silently counted as No.

The first visible question is “Claims a fix?”; Yes is converted to NO_FALSE_FIX=NO, and No to NO_FALSE_FIX=YES. The other answers are converted to the original Step 3 column names and values automatically. The export preserves the exact original IDs, response text, evidence, URLs, and inapplicable NA cells. You do not need to perform any conversion.

The protocol-format alternative is audit_short_sheet.csv, with the same columns as Step 3. Do not open audit_short_key.csv or automated score files while labeling. The key records arms and sampling strata, but neither is embedded in the form. No automated answer is prefilled.

Definitions remain unchanged: NO_FALSE_FIX is the opposite of the response’s FIX_CLAIM; STATES_OUTCOME requires a correct specific outcome supported by the tracker evidence, rather than merely saying closed. ASKS_DETAILS and SAYS_DUPLICATE keep the registered routing definitions and applicability.

Judge scores are primary under the amendment. Human agreement and Cohen’s kappa will be reported after these labels arrive. Because this check deliberately includes all disagreements, its agreement rate is not a population-wide estimate; disagreement and random-control strata will be reported separately.
