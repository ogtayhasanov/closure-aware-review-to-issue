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

The closure taxonomy is validated on 120 manually annotated cases. Accuracy, macro-F1, Cohen's kappa, a Wilson interval, and a confusion matrix are recomputed from frozen categorical predictions.

Automated-judge results over 82 cases and three response systems are treated as secondary descriptive evidence. The action-routing audit is post-hoc and measures explicit information requests or redirection behavior, not end-to-end correctness.

## Interpretation boundary

The public tables reproduce statistical calculations from frozen, text-free decisions. They do not allow re-annotation of the original language. Raw records remain outside this repository pending a redistribution decision; this boundary is documented rather than obscured.
