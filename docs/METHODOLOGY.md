# Methodology overview

## Research question

Can an issue-grounded response system avoid treating every closed issue as successfully resolved, and does explicit closure-reason conditioning improve the status communicated to an app user?

## Pipeline

1. Retrieve issue candidates for a user review with reciprocal-rank fusion over a dense retriever and BM25.
2. Interpret tracker metadata with a deterministic, priority-ordered closure taxonomy.
3. Assign one of `RESOLVED`, `REJECTED`, `ABANDONED`, or `REDIRECTED` and a more specific subtype.
4. Generate a response grounded in the retrieved issue and closure outcome.
5. Evaluate retrieval, closure classification, response status correctness, hallucination, and action realization.

## Evaluation design

The primary human endpoint is a blinded paired comparison of closure-aware and binary-state responses over 36 non-resolved cases, producing 72 judgments. The inferential test is a two-sided exact McNemar test with one primary comparison.

The supplement includes the deterministic closure taxonomy and its precedence rules. [Mapping protocol](../protocols/taxonomy_mapping_protocol.json)

Automated-judge results over 82 cases and three response systems are treated as secondary descriptive evidence. The action-routing audit is post-hoc and measures explicit information requests or redirection behavior, not end-to-end correctness.

The follow-up experiments use one shared system message, two generators, and a separately defined outcome judge. The tracker-provenance probe and subsequent comparisons have their own endpoints and testing families. [Follow-up protocol and evidence](FOLLOW_UP.md)

The external retrieval export preserves the frozen positive-subset ranks for BM25, BGE-ZS, and RRF. The paired Wilcoxon calculation uses zero removal and a tie-corrected normal approximation as in the archived test. It adjusts the three retrieval endpoints together and adjusts the two exact McNemar checks in a separate family. Abstention uses the archived inclusive thresholds and corrects the three one-sided Fisher enrichment tests together. The strict end-to-end curve reuses frozen success flags at those thresholds.

## Interpretation boundary

The public tables reproduce statistical calculations from frozen, text-free decisions. The original texts are in working_artifacts/.
