# Analysis implementation choices

The user’s primary tests and two-test Holm family are unchanged. Exact two-sided McNemar conditions on the discordant counts. Rates include Wilson 95% intervals.

The STATES_OUTCOME difference is RAW+MEANING minus raw_metadata, using the same 35 paired cases. Its 95% interval is a paired nonparametric percentile bootstrap: resample whole cases, 200,000 replicates, NumPy default_rng seed 20261024. This retains the within-case dependence. It is descriptive uncertainty and does not replace the exact McNemar test.

Existing GPT audit judgments are reused for RAW and TAXONOMY-ONLY. The same frozen evidence-only judge is applied to the 70 combined audit responses and to the 70 existing Gemma RAW/TAXONOMY-ONLY audit responses, since those Gemma STATES_OUTCOME judgments were not previously available. Routing judgments missing for selected existing switch responses or audit comparators use the unchanged response-only routing judge. No new generator calls are made for the switch.

NO_FALSE_FIX is the opposite of the frozen-core FIX_CLAIM score, as in the previous amendment. STATES_OUTCOME has no lexical score in this experiment. Received taxonomy classes are never used as correctness truth. Prior audit membership/applicability is retained for comparability; correctness is evaluated against tracker evidence.

Nextcloud #2131 is generated and scored but excluded from every analysis, as before. All counts, failed/retried requests, and exclusions are retained. The switch is computed from refreshed GitHub issue/complete-timeline evidence, requires a currently closed issue, uses the frozen bot detector and extra bot list, and defaults to raw for other trackers. Every candidate bot-closed fair case has no commit or PR reference anywhere in its complete returned timeline. The API currently reports #5910 open, so its past bot closure does not trigger switching.

The conditional human sheet includes both responses for every GPT test-2 judge-discordant case, shuffled with seed 20261024, with neutral IDs assigned after shuffling. Only STATES_OUTCOME is requested. The private arm/pair key is separate. This selected check cannot estimate full-population judge accuracy.
