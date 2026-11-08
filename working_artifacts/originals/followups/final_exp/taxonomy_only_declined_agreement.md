# DECLINED agreement: new TAXONOMY-ONLY bot-test responses

Existing frozen judge and lexical flags only; no new generation, judging, relabeling, or pattern changes. Every response hash was verified. Agreement is between two automated procedures, not accuracy against human truth.

## Main comparison: the 50 BOT cases, separately per generator

| Model | Agreement | Wilson 95% interval | Cohen’s κ | Judge positive | Lexical positive |
|---|---|---|---|---:|---:|
| gpt-4o-mini-2024-07-18 | 38/50 (76.0%) | 62.6–85.7% | 0.0000 | 12 | 0 |
| gemma-4-26b-a4b-it | 50/50 (100.0%) | 92.9–100.0% | undefined (both constant) | 0 | 0 |

### BOT-case contingency counts

| Model | Judge+/lexical+ | Judge+/lexical− | Judge−/lexical+ | Judge−/lexical− |
|---|---:|---:|---:|---:|
| gpt-4o-mini-2024-07-18 | 0 | 12 | 0 | 38 |
| gemma-4-26b-a4b-it | 0 | 0 | 0 | 50 |

## Supplement: HUMAN cases and the full 80-case bot-test population

These strata clarify the denominator; they are not pooled across generators. Marginal label prevalence differs sharply between BOT and HUMAN cases, so the all-80 kappa is not a substitute for BOT-only agreement.

| Model | Group | n | Agreement | Cohen’s κ |
|---|---|---:|---|---|
| gpt-4o-mini-2024-07-18 | HUMAN | 30 | 29/30 (96.7%) | 0.0000 |
| gpt-4o-mini-2024-07-18 | ALL_BOT_TEST | 80 | 67/80 (83.8%) | 0.6770 |
| gemma-4-26b-a4b-it | HUMAN | 30 | 26/30 (86.7%) | 0.2683 |
| gemma-4-26b-a4b-it | ALL_BOT_TEST | 80 | 76/80 (95.0%) | 0.8883 |

A high observed agreement with no positive labels can have undefined kappa. Undefined is reported explicitly rather than replaced with zero or one. Full counts and intervals for every stratum are in the CSV.

The new 24-response human sheet concerns STATES_OUTCOME in fair cases; it does not validate DECLINED on the BOT cases. Primary automated results and all earlier sheets remain unchanged.
