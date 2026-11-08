# Human check of test 1 discordant pairs

The returned blind sheet has 24 completed YES/NO answers from 12 pairs. No blank or unsure answers, exclusions, duplicate IDs, or altered evidence/response text were found. The original exported file is preserved byte for byte.

## Agreement with human labels

| Automated method | Agreement | Cohen’s κ | Human YES / automated YES | Human YES / automated NO | Human NO / automated YES | Human NO / automated NO |
|---|---:|---:|---:|---:|---:|---:|
| Judge | 18/24 (75.0%) | 0.5000 | 11 | 5 | 1 | 7 |
| Lexical | 13/24 (54.2%) | 0.0571 | 9 | 7 | 4 | 4 |

## Human outcomes within the selected pairs

| Arm | STATES_OUTCOME = YES |
|---|---:|
| raw_metadata | 12/12 (100.0%) |
| TAXONOMY-ONLY | 4/12 (33.3%) |

Human pair counts: both YES 4; TAXONOMY-ONLY only YES 0; raw only YES 8; both NO 0.

Exploratory exact two-sided McNemar on these 12 selected pairs: p = 0.0078125, unadjusted. This is not a replacement for the prespecified 35-case primary test or its Holm correction.

Selected on judge discordance in test 1. Agreement and paired results describe these 24 responses/12 cases only, not the full 35-case population. Primary automated scores and tests remain unchanged.

This check labels STATES_OUTCOME in fair-case responses. It does not validate BOT DECLINED labels or the other routing questions. No new model calls or lexical-pattern changes were made.

Imported source SHA-256: `68e461da8284683006807a701332bf5cf52a31b67311bd04481774507d8f0d79`.
