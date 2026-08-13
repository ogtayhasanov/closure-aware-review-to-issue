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
| 117,695-issue closure prevalence study | Aggregate values only | Reported; row-level source not public here |
| Full retrieval effectiveness and significance tables | Not included in this snapshot | Awaiting a separate release package |

The primary claim in this snapshot is the paired human status result. Automated-judge measures are secondary, and action realization is a mechanism-oriented descriptive audit.
