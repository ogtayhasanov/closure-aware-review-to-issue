# Curated working artifacts

The public snapshot retains selected text-free decisions and archived scripts. Raw source text, platform review identifiers, workbooks, generation logs, private working notes and the full manuscript archive are excluded from the current snapshot. Historical Git versions may still contain material removed from this version.

## Curated evidence

- `curated/taxonomy_tracker_fields_120.csv`: the 120 human and rule labels with the tracker state and label fields needed to recompute the rule output; issue numbers and descriptions are omitted.
- `curated/raw_metadata_human_36.csv`: 36 first-author re-annotation decisions from 8 November 2026. The earlier labels were not retained. These `R` identifiers are local to this file.
- `curated/retrieval_query_scores_82_with_bge_ft.csv`: 82 text-free retrieval records, including the BGE-FT rank.
- `curated/ai_relevance_labels_796.csv`: final Yes/No/Unsure labels, confidence, and review-pass metadata from the exploratory AI audit.
- `curated/ai_relevance_ranked_1066.csv`: the text-free system, query, rank and pair mapping for those labels. The `A` query identifiers are local to this DeepMatcher audit and are not the `Q` identifiers in the main retrieval snapshot.
- `curated/deepmatcher_comparison_82.csv`: cached-reproduction and originally released ranks on the same 82 audit queries.
- `curated/ai_relevance_protocol.json`: the audit protocol. A single ChatGPT evaluator produced the labels; the second pass was not an independent human annotation and the exact model snapshot is not recorded.
- `curated/manuscript_figure1_prevalence_9.csv`: the nine project numerators and denominators transcribed from Figure 1 of the 8 November 2026 manuscript. These allow the published pooled arithmetic to be checked but are not the underlying historical issue-level data.

The `originals/` directory retains historical Python scripts as methodological records. Personal absolute paths in these copies have been replaced with paths rooted at `legacy_inputs/`. The original experiments required external datasets, model services, packages, and checkpoints that are not included; these scripts are not a standalone rerun kit. Use `python scripts/verify_submission.py` for the supported offline reproduction.

`SOURCE_MANIFEST.json` records checksums of the curated public copies, not checksums of the unmodified historical files. `MANIFEST.sha256` at the repository root covers the complete current snapshot.
