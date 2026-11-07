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
| 117,695-issue closure prevalence study | Historical aggregate values | Reported |
| External BM25, BGE-ZS and RRF results | 82 paired best-known-positive ranks | Reproduced, including both RRF test families |
| Selective retrieval and strict end-to-end retention | Frozen confidence thresholds, query scores and strict success flags | Reproduced |
| BGE synthetic-development comparison | 794 paired ranks for zero-shot and the selected epoch-2 checkpoint | Reproduced |
| DeepMatcher cached-vector and expanded relevance audit | Manuscript aggregates, including 796 pooled AI decisions and five top-1 rows | Reported; pair-level supplement unavailable in this snapshot |
| External BGE-FT, expansion and cross-encoder diagnostics, legacy raw-human 34/36, clean cross-tracker audit, and synthetic generation diagnostics | Manuscript-reported values and coverage notes | Reported; matching frozen decision or rank ledgers unavailable here |

The original paired human status result and the follow-up judge analyses use different protocols and cohorts. See [follow-up results](FOLLOW_UP.md), [machine-readable reproduction summary](../results/generated/reproduction_summary.json), and [manuscript-reported reference values](../results/reference/manuscript_reported.json).
