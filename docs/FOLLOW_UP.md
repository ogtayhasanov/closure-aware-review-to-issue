# Follow-up generation evidence

The shared-prompt replication ran 82 fair inputs across three arms with both generators. The bot probe used 80 `wontfix` issues with no linked fix from Signal and Jitsi. A bot applied the label and closed the issue in 50 cases, 25 from each project. A person performed both actions in the remaining 30 eligible issues. Taxonomy only and raw + meaning each added 324 responses across the two datasets and generators. The public ledger has 1,780 generated response records in total. [Derived data inventory](../data/README.md)

| Arm | Closure evidence supplied |
| --- | --- |
| Binary | Open or closed state |
| Raw | Raw tracker closure fields |
| Raw + closer | Raw fields plus closure actor, linked-fix evidence and label actor |
| Closure-aware / V1 codes | Raw fields plus normalized class, subtype and action |
| V2 codes | Raw fields plus codes using the provenance-aware GitHub rule |
| Taxonomy only | Normalized class and exact meaning line |
| Raw + meaning | Raw fields plus the class and meaning line |
| Switch | Selects the saved taxonomy-only response for a confirmed bot closure without a linked fix and the raw response otherwise |

The V2 mapping gives duplicate evidence precedence, then maps bot closure without a linked fix to ABANDONED before evaluating rejection labels. The switch has its own selection rule based on closer and linked-fix provenance. A currently open issue stays on raw. Generation used `gpt-4o-mini-2024-07-18` and `gemma-4-26b-a4b-it` at temperature 0 with a 220-token maximum. The outcome judge saw the response and tracker evidence without an arm label. The response-only judge scored DECLINED, FIX_CLAIM, INACTIVITY, ASKS_DETAILS and SAYS_DUPLICATE using separate frozen instructions. NO_FALSE_FIX is the inverse of the existing core FIX_CLAIM score. [Exact prompts, meanings and settings](../protocols/followup_prompts.json)

The internal protocol history includes the bot-closure plan (`e0bf6d9`), routing plan (`0b83e2c`), taxonomy-only plan (`fce3086`), the amendment making automated scores primary and limiting the human check (`dbfeb18`), and the combined-arm plan (`48d8b42`). The published analysis specification records the exact McNemar contrasts, Holm families, and descriptive outcomes. The archived lexical checkers document the scoring rules used for the frozen decisions. [Analysis specification](../protocols/followup_analysis.json) · [Lexical checkers](../protocols/lexical/)

The frozen historical human audit keeps 36 pairs. The follow-up audit has 35 cases after a tracker refresh verified that one issue with missing closure fields had actually been fixed. The response stays in the saved 82-case original evidence and carries an exclusion code for the follow-up comparison. Another refresh found manual configuration advice without verified code-fix evidence. The fixed/not-fixed split uses tracker evidence and retains uncertain cases separately. [Fix-claim results](../results/generated/followup_fix_by_status.csv)

## Bot-closure probe

Judge-coded DECLINED positives out of the same 50 bot-closed cases per model:

| Model | Raw | Raw + closer | V1 | V2 | Taxonomy only | Raw + meaning | Switch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-4o-mini | 50 | 50 | 50 | 49 | 12 | 50 | 12 |
| Gemma | 23 | 24 | 50 | 21 | 0 | 0 | 0 |

The original four arms had 638/640 judge–lexical agreement on DECLINED across both generators and both closure groups. For GPT taxonomy only on the 50 BOT cases, agreement was 38/50 and all 12 disagreements were judge-positive and lexical-negative. Gemma agreed on 50/50, with both scorers always negative and kappa undefined. The binary judge records do not contain rationales. Bot-probe labels have no human verification. [Agreement counts](../results/generated/followup_agreement.csv)

## Fair outcome audit

| Model | Binary | Raw | Closure-aware | Taxonomy only | Raw + meaning | Switch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-4o-mini | 20/35 | 33/35 | 30/35 | 23/35 | 31/35 | 29/35 |
| Gemma | unavailable | 31/35 | unavailable | 21/35 | 31/35 | 29/35 |

GPT's taxonomy-only comparison with raw gives Holm-adjusted p = 0.00635 for STATES_OUTCOME and p = 1.46e-11 for bot-probe DECLINED. Both GPT raw + meaning primary comparisons have Holm-adjusted p = 1. The outcome difference is −5.71 percentage points with a paired 95% percentile interval of [−17.14, +5.71] points. The public reproducer enumerates the paired bootstrap distribution and recovers the archived Monte Carlo interval endpoints. The switch selects taxonomy only for 50/80 probe inputs and 5/82 fair inputs, including 4/35 fair audit cases. [Per-arm rates](../results/generated/followup_rates.csv) · [Paired tests](../results/generated/followup_paired_tests.csv)

The completed human check covers the 12 pairs selected for GPT judge disagreement between raw and taxonomy only. The human labels favored raw in 8 pairs and tied in 4. The judge agreed with the human labels on 18/24 responses, with κ = 0.50. The paired subset is selected for disagreement and cannot estimate agreement over the entire audit. The separate combined-arm check covers four pairs and eight responses. Its human labels are pending in this snapshot. [Human labels](../data/derived/followup_human_check_24.csv)

Under the shared prompt, GPT judge-scored requests for details were 15/16 raw and 16/16 closure-aware, while duplicate statements were 7/7 for both. The historical action audit used distinct system messages and a narrower duplicate-routing endpoint. Canonical duplicate targets were unavailable for the registered shared-prompt routing cases. The lexical results and the available judge results are reported separately. [Routing rates and tests](../results/generated/followup_rates.csv)

## Provenance sensitivity

The seven GitHub scan aggregates preserve the V1 and V2 counts and the historical comparison denominators. Four V1 scan rates fall outside the pre-specified ±0.5 percentage point comparison with the historical table. In the narrower V1 rejection-by-label subset, bots applied 1,477/1,670 Jitsi labels (88.4%) and 1,976/1,982 Signal labels (99.7%). The broader issue-label-instance denominators give 1,478/1,674 and 1,979/1,985, respectively. The refreshed scan uses bounded timeline evidence. Firefox and VLC are outside this GitHub sensitivity analysis. [Reproduced aggregate rates](../results/generated/followup_prevalence.csv)
