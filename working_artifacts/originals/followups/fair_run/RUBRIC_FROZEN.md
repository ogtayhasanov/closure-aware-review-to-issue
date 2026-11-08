# Fair RQ3: prospective blinded human annotation rubric

Version: `fair-rq3-rubric-v1-2026-10-20`. **Freeze before examining newly generated responses.** All arms are independently rated in one arm-masked, shuffled pass. A case may appear three times; do not group by case or reveal the key before completing the full sheet.

## Information shown to human annotator

- A verified *neutral reference-evidence synopsis*, independently assembled from original tracker facts and, when necessary, closing comments; the synopsis cannot be copied from a generated response or use the arm name.
- One generated response with its case/arm identity concealed. The reference may reveal the true outcome, but not which evidence representation a generator received.

## Fields in `blind_annotations.csv`

1. `status_correct` (REQUIRED, 0/1): **1** only if the response communicates the correct closure status/outcome without a false fix implication; **0** if it wrongly says a closed non-resolved issue was fixed, fails to convey a critical outcome, or makes an incompatible claim. An abstention that does not actually convey the known outcome is **0** under this strict metric. For open issues, identify them as open, not necessarily being actively worked on.
2. `unsupported_fix_claim` (REQUIRED, 0/1): **1** if the response asserts or strongly implies a fix, patch, release, or verified resolution that the reference evidence does not support. Otherwise **0**. A statement such as "there is no confirmed fix" does **not** count as a fix claim.
3. `other_unsupported_claim` (REQUIRED, 0/1): **1** for a material invented claim about staffing, active investigation, canonical ticket, release, cause, status, promises, etc. A generic acknowledgement is not an unsupported fact.
4. `required_action_present` (REQUIRED, 0/1/NA): score **1** for NEEDS_INFO only when it explicitly requests at least one diagnostic artifact (reproduction steps, app version, device information, or logs). Merely mentioning logs without asking fails. For REDIRECTED, **1** requires explicit routing to a different/original/linked issue, tracker, or discussion; the isolated word "duplicate" fails. For other cases, use `NA` (do not assume absence is a failure). For KNOWN_BUG, additionally flag ungrounded claims of active developer work under `other_unsupported_claim`.
5. `note` (optional): concise explanation, preferably with a quote or verbatim evidence phrase.

## Analysis rules frozen now

- Audit population: the fixed 36 final-RRF cases whose retrieved issue is **closed** and in REJECTED/ABANDONED/REDIRECTED; use all 3 arms (108 responses). The 82-case set contains all 246 outputs; do not mistake 82 for 82 non-resolved issues.
- Primary endpoint: **human status correctness** on the 36-case subset. Report all three proportions and per-case paired exact two-sided McNemar comparisons, reporting discordant cells. Declare which comparison is primary **before** labels; suggested primary: taxonomy vs raw metadata (incremental normalization). Binary vs raw is a secondary information-availability contrast. If making multiple confirmatory claims, Holm-correct accordingly.
- Separate mechanism endpoints: human `required_action_present` for the frozen NEEDS_INFO and REDIRECTED subsets, with their denominators; automatic regex screens are auxiliary only.
- Lexical screens on all 82 × 3 outputs are diagnostic, not model accuracy scores. New external LLM judges require independent model families and explicit agreement against the new human labels.
- Do not reuse the **old** 34/36 vs 1/36 counts or old McNemar p-values as if they were produced with this common prompt. They are from the deliberately unequal original protocol.
- Keep `blind_key.jsonl` separate from the annotation CSV; unlock only after all annotations are completed. Missing labels must not be scored.
- One annotator does not establish inter-rater reliability. State single-annotator limitation, and ideally obtain an independent second rater on a subset.

The annotator should not see identifiers such as `binary_state`, `raw_metadata`, or `closure_aware` in separate columns. Revealing references to closure classes is acceptable for defining ground truth, but can increase outcome priming; evaluate that possibility as a construct-validity limitation.
