# Prevalence sensitivity: unchanged V1 versus V2

All seven GitHub projects in the paper’s Table 1 have completed scans (DONE cursors). No missing project and no new network scan. The original closure_provenance.py was copied byte for byte and run with `summarize --extra-bots automated-signal`; no rule was tuned. The inference that automated-signal is automation is the same declared addition used in bot_test.

| Project | Closed | Paper V1 % | Recomputed V1 % | V2 % | V1−paper pp | Within 0.5 pp | Rejection-labeled issues | Labels added by bot % | Such issues bot-closed/no fix % |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| Jitsi | 6959 | 42.5 | 42.52 | 42.58 | +0.02 | yes | 1674 | 88.3 | 80.3 |
| Nextcloud | 7224 | 34.9 | 42.52 | 42.58 | +7.62 | NO | 32 | 0.0 | 0.0 |
| AnkiDroid | 9318 | 27.5 | 27.66 | 27.95 | +0.16 | yes | 104 | 0.0 | 3.8 |
| Brave | 45558 | 20.3 | 23.66 | 23.68 | +3.36 | NO | 3898 | 0.0 | 0.0 |
| Signal | 11331 | 18.2 | 18.66 | 28.44 | +0.46 | yes | 1985 | 99.7 | 87.6 |
| K-9 Mail | 5161 | 13.3 | 20.38 | 21.60 | +7.08 | NO | 0 | n/a | n/a |
| PPSSPP | 9077 | 5.7 | 11.24 | 11.24 | +5.54 | NO | 41 | 0.0 | 0.0 |

**Differences are reported without changing the mapping.** Scan totals are reported alongside the paper’s historical totals in the CSV. A difference can reflect time/snapshot changes, a different original mapping, or extraction differences; the current artifacts alone do not identify which caused it. A failure of the 0.5-point reproduction check is not described as successful replication.

The rejection-label population includes every issue with any raw label matching the unchanged RX_REJECT, even when duplicate precedence makes its V1 class REDIRECTED. “Labels added by bot” uses matching issue-label instances as the denominator, with the last retained add event per label. Unknown adders remain in that denominator and are separately counted in the CSV; the known-adder-only percentage is also provided. This is an observed bot-attribution share, not an assumption that unknown actors are human. “Such issues bot-closed/no fix” is conditional on rejection-labeled issues. The all-closed-issue share is also in the CSV. The unchanged script’s narrower V1 REJECTED-by-label counts are retained in separate columns.

The source GraphQL scan retains only its configured label/timeline windows, so an unknown adder or absent linked closer may reflect incomplete historical provenance. V2 is a rule sensitivity analysis, not independently adjudicated truth. Firefox/Bugzilla and VLC/Trac are not GitHub projects and are not recomputed by this GitHub-only script. The manuscript and its tables are unchanged. Full source hashes and scan completeness are in prevalence_manifest.json.
