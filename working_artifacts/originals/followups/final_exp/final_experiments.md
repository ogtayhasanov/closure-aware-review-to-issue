- Fair RQ3 run and its files: as listed in the routing test's Checkpoint 2 (new_responses_246.jsonl, real_82_native_staged.jsonl, fair_prompts_246_dryrun.jsonl, rq3_protocol.py, main_responses_gemma.jsonl).
- Bot-closure test: bot_test/ (canonical copy: C:\Users\Ogtay\Desktop\test\bot_test).
- Findings so far: the closure_aware arm and TAXONOMY-V2 kept the raw labels and only appended class codes, and the models followed the raw labels. Nextcloud #2131 was fixed by merged PR #4470. Nextcloud #3425 was closed manually with battery-setting advice, with no code fix.
- This step tests the taxonomy as a replacement for the raw labels, redoes the human audit on the fair responses, and prepares the data for the paper.
1. Commit this file before anything else.
2. Don't edit existing outputs, prompts or the paper. Put everything new in final_exp/.
3. Only the closure block may differ between arms. Use the same system prompt, model versions, temperature and token limit as the earlier runs. Read them from the saved manifests.
4. Never use the taxonomy class as ground truth for correctness.
5. Never drop a case or a response silently. Report every exclusion with its reason.
6. Stop only at the two checkpoints below.
```
git add final_experiments.md && git commit -m "Pre-register final TOSEM experiments"
```
Start from each case's RAW-arm user message. Replace the whole RAW TRACKER CLOSURE FIELDS: block (its heading and every line in it) with:
```
CLOSURE:
- class: <CLASS>
- meaning: <the meaning line below>
```
Everything else stays byte-identical to the RAW message, including the "Binary state" line.

Meaning lines, fixed now:
Cases:
- Bot test: all 80 issues (50 BOT, 30 HUMAN), with the class from the V2 rule.
- Fair cases: all 82, with the class and subtype the closure_aware arm received. Nextcloud #2131 stays as received and is excluded from all analyses, because it was fixed.
Save final_exp/inputs_taxonomy_only.jsonl.

CHECKPOINT 1. Show me the TAXONOMY-ONLY and RAW messages, with a diff, for one BOT issue, one HUMAN issue and one fair NEEDS_INFO case. Wait for my OK.
- Generate TAXONOMY-ONLY responses for all 162 inputs with both models: gpt-4o-mini (same version) and Gemma 4 26B A4B Instruct (same provider and settings as bot_test/).
- Score every new response with the same judge as bot_test/ (GPT-5.4 nano) and the frozen lexical checks: DECLINED, FIX_CLAIM and INACTIVITY from bot_test/lexical.py, and ASKS_DETAILS and SAYS_DUPLICATE from routing_test/lexical.py.
- Save final_exp/responses_taxonomy_only_<model>.jsonl and final_exp/auto_scores.csv.
- Cases: the 36 non-resolved audit cases minus Nextcloud #2131, so 35 cases. For #3425, show the closing-comment evidence the tracker refresh found.
- Responses: gpt-4o-mini, 4 arms (binary_state, raw_metadata, closure_aware, TAXONOMY-ONLY), so 140 responses.
- final_exp/audit_sheet.csv: shuffled (seed 20261024), with the arm removed. Columns: sheet_id, issue_url, tracker_evidence (the raw closure fields, plus the closer and any linked fix where known), response, NO_FALSE_FIX, STATES_OUTCOME, ASKS_DETAILS, SAYS_DUPLICATE, notes. Fill ASKS_DETAILS with NA except for NEEDS_INFO cases, and SAYS_DUPLICATE with NA except for REDIRECTED cases. Keep the key in final_exp/audit_key.csv.
- Definitions, fixed now: 
  - NO_FALSE_FIX: YES if the response doesn't say or imply that the problem is fixed, resolved or coming in an update.
  - STATES_OUTCOME: YES if the response states the specific outcome the tracker evidence shows, for example closed as a duplicate, closed because more information was needed or it couldn't be reproduced, closed as not planned or invalid, or closed for inactivity. "The issue is closed" alone is NO.
  - ASKS_DETAILS and SAYS_DUPLICATE: as defined in routing_and_v2_check.md.
- Tell me the sheet is ready, then continue with Steps 4 and 5 without waiting.
- Run python closure_provenance.py summarize with the same --extra-bots list as bot_test/.
- Check which GitHub projects in the paper's Table 1 have a scan. If one is missing, scan it.
- Check that the script's V1 rule reproduces each project's non-resolved share in Table 1, within 0.5 points. Report any difference. Don't tune the rule.
- Write final_exp/prevalence_sensitivity.csv and a short table in final_exp/prevalence_sensitivity.md. Per project: closed issues, non-resolved share under V1 and under V2, issues with a rejection label, the share of those labels added by a bot, and the share closed by a bot with no linked fix.
Build final_exp/release/ with every system prompt and user message, every response (all runs and models), all automated scores, the scripts, a manifest with SHA-256 hashes, and a README listing each file. Check that no API keys, tokens or local paths are inside.

CHECKPOINT 2. Wait for my labelled audit_sheet.csv.
- Human audit, per arm: NO_FALSE_FIX, STATES_OUTCOME, ASKS_DETAILS and SAYS_DUPLICATE, with counts, % and Wilson 95% CIs.
- Primary tests (exact McNemar, Holm across the two): 
  1. TAXONOMY-ONLY vs raw_metadata on STATES_OUTCOME (human audit).
  2. TAXONOMY-ONLY vs RAW on false DECLINED for BOT issues (bot test, gpt-4o-mini, automated scores).
- Secondary, without correction: closure_aware vs raw_metadata on each audit question; the same bot-test comparison for Gemma; FIX_CLAIM by true status for TAXONOMY-ONLY, as in routing_test/.
- Agreement: the lexical checks and the judge against my labels (Cohen's kappa).
- Bot test: TAXONOMY-ONLY says "won't be addressed" far less often than RAW for both models, and mentions automatic closing more often.
- Fair cases: TAXONOMY-ONLY matches raw_metadata on NO_FALSE_FIX and STATES_OUTCOME.
- Report the results either way.