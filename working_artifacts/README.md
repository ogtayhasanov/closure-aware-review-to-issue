# TOSEM working artifacts

The `originals/` directory holds byte-for-byte copies of local run files and archived members. `reference/` holds the corresponding public score tables. `index/` contains new case crosswalks built from those files. `SOURCE_MANIFEST.json` records each source, member name and SHA-256. This bundle contains full research texts.

| Requested item | Availability | Where to look |
| --- | --- | --- |
| Full execution codebase | Partial. Recovered retrieval, query expansion, cross-encoder reranking, fine-tuning, response generation and judge runners from several run snapshots. The exact end-to-end environment and complete source set remain unverified. | `originals/historical_snapshot/scripts/full_pipeline/`, `originals/retrieval/scripts/`, `originals/training/`, and `originals/followups/` |
| Main 246 responses and rationales | Complete. All three original arms contain 82 responses and all 246 rows have a saved `judge_reasoning` value. Both the generator and judge returned `gpt-4o-mini-2024-07-18`. | `originals/main_246/rrf_threeway_responses_and_judgments.csv` and `api_progress.jsonl` in the same directory |
| Follow-up 1,780 responses and judge logs | All response texts and boolean judge outputs recovered. Written judge rationales were never requested or returned by the saved calls. | `index/followup_judgments_1780_with_text.csv` and `originals/followups/` |
| Table 5 and Figure 5 synthetic responses | Complete. All 175 rows contain the four original response fields `resp_ca`, `resp_sa`, `resp_rag` and `resp_zs`. | `originals/synthetic_benchmark/closure_reason_results.csv` |
| Table 8 RAW METADATA human labels | Complete. The supplied workbook matches all 36 archived cases and records 34 correct and two incorrect human verdicts. | `originals/human_status/completed/raw_metadata_status_annotation_36_FORMATTED.xlsx`, `index/raw_metadata_labels_completed_36.csv`, and `index/raw_metadata_audit_36_crosswalk.csv` |
| BGE-FT full ranks for 82 real queries | Complete. Both supplied exports agree on all 82 BGE-FT and BGE-ZS ranks. The joined table includes `bge_ft_rank` for each public query ID. | `originals/retrieval/bge_fullrank/` and `index/retrieval_query_scores_82_with_bge_ft.csv` |
| Taxonomy 120 and Table 3 cross-tracker 90 | Complete. The 120 native state reasons and the labels field are restored beside the frozen predictions. The 90-row file contains native evidence, model rationales and rule predictions. | `index/taxonomy_predictions_120_with_tracker_fields.csv` and `originals/cross_tracker_90/CLEAN_scored_90.csv` |
| Appendix C DeepMatcher and 796-pair AI audit | Complete. The supplied archive contains the original cached-document reproduction and all 796 frozen judgments and reasons. | `originals/deepmatcher_appendix_c/DeepMatcher_Supplementary_2026-11-03.zip` |

## Follow-up scoring

The 1,780 rows consist of 492 shared-prompt fair responses, 640 original bot-test responses, 324 TAXONOMY-ONLY responses and 324 RAW+MEANING responses. Each text matches the SHA-256 saved with its original score. The switch policy reuses existing texts.

The follow-up judge was `gpt-5.4-nano-2026-03-17`. Its saved payloads returned boolean fields only. The archived October and November prompts define DECLINED to include implied decisions by developers. The frozen lexical rule checks text patterns. On 50 GPT-4o-mini TAXONOMY-ONLY bot closures, the judge marked 12 DECLINED and the lexical rule marked zero. The 12 texts and both scores are in `index/taxonomy_only_gpt_bot_declined_12.csv`. Jitsi #4913 includes “Unfortunately, it was not accepted for implementation.” The frozen patterns do not match that phrase. The saved judge outputs establish the disagreement and leave the trigger sentences unspecified.

`lexical_states_outcome` is populated for the 140 GPT-4o-mini audit responses originally scored with that rule in `originals/followups/final_exp/audit_primary_scores.csv`. It is blank on the other 1,640 rows because the rule was only applied to that subset. The later combined-arm analysis specified judge-only scoring for STATES_OUTCOME. `judge_states_outcome` is populated for 280 responses. Blank cells indicate missing scores.

## Historical human status and routing

The supplied completed RAW METADATA workbook matches all 36 annotation IDs, evidence fields and responses in the archived blank worksheet. It records 34 correct and two incorrect human verdicts for Table 8. The separate historical LLM status verdicts are 27 true and nine false. The completed 72 human judgments cover the structured and binary arms.

The action-routing audit overlaps 23 of the 36 RAW METADATA cases. That includes all eight WORKSFORME cases, seven on Bugzilla and one on Trac. Those action codes record whether the response asks for more information or redirects. The crosswalk keeps action codes, original LLM status verdicts and completed human verdicts in separate columns.

## Training and retrieval provenance

The four original synthetic review exports contain 4,700 Brave, 2,977 Signal, 2,967 AnkiDroid and 2,935 K-9 rows. The saved balance and filtering artifacts cover 9,349 pairs and preserve the final 7,944 retained pairs and 62,515 triplets. The original alignment ledger contains 9,348 GPT-4o-mini scores and one placeholder for a failed Signal judgment. Its row was removed before triplet mining. The bundle preserves the original ledgers, retained pairs and training inputs.

The recovered training snapshots include the BGE-FT run config, split and internal evaluation and the SPLADE seed 13, 21, 42, 67 and 100 source and run metadata. The `old35/` directory contains a separately named training variant. Model checkpoint binaries remain in the original training archives. The earlier artifact scripts and notebook variants are historical source snapshots with varying coverage.

The original external full-rank export contains 82 cases for each of three BGE variants. The `bge_ft_rank` column uses `best_gold_rank` for `BGE-FT-E2-NOPREFIX-TITLE`. The join uses the archived query ID mapping and was checked against all existing BM25, BGE-ZS, and RRF ranks. The BGE-FT ranks reproduce the paper's MRR of 0.202, Hit@1 of 9/82, Hit@10 of 35/82, and median rank of 20.5.

The original controlled synthetic output reproduces Figure 5's reported hallucination counts. The closure-aware and binary-state counts are 0/35 and 8/35 for REJECTED, and 2/35 and 17/35 for ABANDONED. The separate L1 rerun CSV is included under its own original filename.

## Appendix C DeepMatcher evidence

The original supplementary ZIP contains two archives. `DeepMatcher_Comparison_2026-11-03.zip` contains reproduction scripts, protocols, and `comparison_results/per_query_results.csv`. Its 82 query IDs match the historical real-query benchmark. Recomputed cached-document results on the original labels are MRR 0.633, Hit@1 41/82, and Hit@10 70/82.

`AI_Relevance_Audit_796_2026-11-03.zip` contains the completed `AI_Relevance_Audit_796/AI_Relevance_Audit_796.csv` and first- and second-pass records. The 796 rows each include a reason. The counts are 174 Yes, 489 No, and 133 Unsure. The first-result AI judgments are Yes on 23/82 cached DeepMatcher results and 30/82 RRF results. The supplied checksums and label-freeze hashes match. The earlier local scripts and SPLADE comparisons remain grouped in `originals/deepmatcher_related/`.

## Taxonomy and cross-tracker evidence

The 120-row source has a populated `state_reason` in every row and nonblank `labels` in 91 rows. The remaining 29 cells were blank in the original export. The joined file was checked row by row against the archived human fields and both frozen rule predictions. The 90-row transfer audit contains 30 rows per tracker and 77 rule–judge agreements.

## Original files with possible credentials

The following source files contain possible credentials and are omitted from the release.

- `Downloads/spladetraining (2).ipynb`
- `Downloads/spladetraining (3).ipynb`
- `Downloads/spladetraining (4).ipynb`
- `Downloads/spladetest.ipynb`
- `Downloads/spladetest (1).ipynb`
- `Downloads/spladetest (2).ipynb`
- `Downloads/spladetest (3).ipynb`
