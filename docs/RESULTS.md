# Results and evidence status

| Claim | Public evidence | Status |
| --- | --- | --- |
| Closure-aware status: 34/36 vs binary state: 1/36 | 72 categorical human decisions with opaque pair IDs | Reproduced |
| Exact McNemar p = 2.33e-10 | Paired human decisions | Reproduced |
| Human/automated-judge agreement: 48/72, kappa 0.339 | Paired binary judgments | Reproduced |
| Taxonomy: 117/120, macro-F1 0.9747, kappa 0.9667 | Human and rule labels without source text | Reproduced |
| Three-system automated-judge summaries over 246 rows | Text-free scores and decisions | Reproduced, descriptive |
| NEEDS_INFO: 16/16 vs 4/16; REDIRECTED: 7/7 vs 0/7 | 46 binary action decisions | Reproduced, post-hoc |
| Five-seed SPLADE checkpoint consistency | Seed, validation, and dataset-hash manifest | Reproduced as manifest audit |
| Shared-prompt fair run, bot probe, taxonomy only, and raw + meaning | 1,780 frozen response decision records, 162 opaque inputs, exact testing families | Reproduced |
| Switch rule | Categorical closer/fix provenance and saved arm decisions | Reproduced |
| Selected human check | 24 completed blinded outcome decisions from 12 judge-discordant pairs | Reproduced |
| Fix claims and routing | Tracker-supported status categories, frozen lexical and judge decisions, explicit missing scores | Reproduced where scored |
| V1/V2 provenance sensitivity on seven GitHub projects | Frozen closed-issue and attribution counts | Rates reproduced from aggregates |
| 117,695-issue closure prevalence study | [Nine project counts transcribed from manuscript Figure 1](../working_artifacts/curated/manuscript_figure1_prevalence_9.csv); no complete historical issue-level source corpus | Aggregate arithmetic reproducible; counts not independently verified |
| External BM25, BGE-ZS and RRF results | 82 paired best-known-positive ranks | Reproduced, including both RRF test families |
| Selective retrieval and strict end-to-end retention | Frozen confidence thresholds, query scores and strict success flags | Reproduced |
| BGE synthetic-development comparison | 794 paired ranks for zero-shot and the selected epoch-2 checkpoint | Reproduced |
| DeepMatcher cached-vector and expanded relevance audit | [82 reproduction ranks](../working_artifacts/curated/deepmatcher_comparison_82.csv) and [796 frozen AI labels](../working_artifacts/curated/ai_relevance_labels_796.csv) | Text-free labels only; reasoning and source text are not included. One ChatGPT evaluator; not independent human validation |
| External BGE-FT | [82 paired query scores with BGE-FT ranks](../working_artifacts/curated/retrieval_query_scores_82_with_bge_ft.csv) | MRR 0.202, Hit@1 9/82, Hit@10 35/82, median rank 20.5 |
| RAW METADATA human audit | [36 verdicts, re-labeled 8 Nov 2026](../working_artifacts/curated/raw_metadata_human_36.csv) | 34 correct and two incorrect; original labels were not retained |
| Clean cross-tracker audit and controlled synthetic generation | Original source-text ledgers are not part of this snapshot | Not independently reproduced here |
| Expansion and cross-encoder diagnostics | [Working artifact inventory](../working_artifacts/README.md) | Historical scripts retained; source inputs and model dependencies are not included |

The original paired human status result and the follow-up judge analyses use different protocols and cohorts. See [follow-up results](FOLLOW_UP.md), [machine-readable reproduction summary](../results/generated/reproduction_summary.json), and [manuscript-reported reference values](../results/reference/manuscript_reported.json).

## Known limitations of the frozen evidence

In the original three-arm real-review generation run, the issue-body field for all 28 Firefox cases was a malformed pandas Series display, rather than the issue description. Those cases produce 84 of the 246 system rows, and 18 of the 36 human-audited cases are from Firefox. The preserved judgments describe the actual outputs generated under that limitation; they are not evidence from a corrected rerun. This issue is distinct from later restoration of Firefox descriptions for the exploratory DeepMatcher relevance audit.

The historical headline of 33,662/117,695 explicitly non-resolved issues (28.6%) can be arithmetically recomputed from the nine project counts printed in Figure 1 of the 8 November manuscript. The transcribed counts are manuscript reports, not an independent reconstruction from the original closed-issue records. Run `python scripts/check_reported_prevalence.py` to recompute the pooled percentage and compare the later scan. For Nextcloud, K-9 Mail, PPSSPP and Brave, the newer seven-project scan gives approximately 42.5%, 20.4%, 11.2% and 23.7%, compared with manuscript rates of 34.9%, 13.3%, 5.7% and 20.3%, respectively. The later denominators and scan conditions differ, and Firefox and VLC are not in that scan. These differences warrant reconstruction or qualification of the original claim, not replacement with an unverified pooled percentage. [Scan aggregates](../data/derived/provenance_prevalence_7.csv)
