# Derived public data

All files in `derived/` are text-free transformations of frozen internal evidence.

- `human_status_72.csv`: paired human and automated status-correctness decisions.
- `taxonomy_predictions_120.csv`: human and deterministic-rule closure labels.
- `generation_judgments_246.csv`: numeric and binary automated-judge outputs for three systems.
- `action_routing_46.csv`: binary realization judgments for two action dimensions.
- `splade_checkpoint_audit_5seeds.csv`: checkpoint-selection and dataset-hash audit.
- `reported_study_scale.csv`: manuscript-level study scale and prevalence aggregates.
- `followup_cases_162.csv`: 82 fair inputs and 80 bot-probe inputs, with cohort membership, tracker-supported status, the exclusion code, and the categorical switch provenance.
- `followup_judgments_1780.csv`: both generators' frozen judge and lexical labels. A blank means that the source did not score that endpoint. `RAW` denotes raw metadata on both datasets, and `BINARY` and `CLOSURE-AWARE` denote the original shared-prompt comparators on the fair dataset. The switch selects rows from this table, without adding generator calls.
- `followup_human_check_24.csv`: completed outcome labels for both responses in each of the 12 GPT-4o-mini judge-discordant raw vs taxonomy-only pairs.
- `provenance_prevalence_7.csv`: seven GitHub scan aggregates with V1 and V2 counts and bot-label attribution denominators.
- `retrieval_query_scores_82.csv`: paired BM25, BGE-ZS and RRF best-known-positive ranks, confidence values, and strict success flags for the original external evaluation.
- `retrieval_thresholds_12.csv`: the three frozen confidence signals and four coverage thresholds per signal.
- `synthetic_bge_ranks_794.csv`: paired synthetic-development ranks for BGE-ZS and the selected epoch-2 BGE-FT checkpoint.

Case IDs are newly assigned opaque identifiers. They are stable within this snapshot but do not expose platform review identifiers, issue numbers, or text.

The follow-up `F`, external-retrieval `Q`, and synthetic-development `S` IDs each belong to a separate namespace. The retrieval and generation exports do not provide a crosswalk. Source checksums identify the internal ledgers used in the export. [Source checksums](../protocols/followup_source_checksums.json)
