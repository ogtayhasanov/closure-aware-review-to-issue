# Missing components and exact repair targets

The current manuscript says per-query/per-case outputs are retained for all retained analyses and specifically says the completed post-hoc raw-metadata human sheet is retained. The available files do not support that statement.

## Highest-priority repair

Supply a completed file at:

`data/human_status/raw_metadata_labels_completed_36.csv`

Required columns are those in `raw_metadata_labels_TEMPLATE_36.csv`; every `Human status correct` value must be TRUE or FALSE. Preserve the original frozen order and annotation IDs. Do not reconstruct labels from the paper’s aggregate.

## Other claim-completeness targets

The exact expected paths are listed in `config/missing_required_files.txt`. They cover:

- final 82-query RRF/BGE/BM25 rank output;
- 82-query confidence/abstention output and selective E2E join;
- query-expansion and CE-top50 per-query results;
- BGE control per-query results;
- nine-project prevalence summary and issue-level classification output;
- final clean 90-case cross-tracker frozen annotations and scored rows;
- final 175-case synthetic response/judgment output;
- auxiliary SPLADE pruning per-query output.

## Two valid resolutions

1. **Restore the files.** Copy the original immutable outputs, document their hashes/provenance, rerun the quick/strict validation, and update the manifest.
2. **Narrow the paper claim.** State exactly which analyses the public artifact reproduces and label the others as scripts or reported summaries. Do not say all per-query/per-case outputs are included.

Until one of these paths is completed, seek only an availability claim for the audited subset, not a claim that the artifact reproduces every empirical result.

