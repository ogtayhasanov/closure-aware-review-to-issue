# Next step: V2 check and fair routing test (instructions for the coding agent)

## Context

- TOSEM paper on closure-aware response generation.
- Fair RQ3 run: 246 responses (82 inputs x 3 arms: binary_state, raw_metadata, closure_aware/taxonomy) with gpt-4o-mini and one shared system prompt.
- Bot-closure test (`bot_test/`, 24 Oct 2026): on bot-closed issues, gpt-4o-mini said "declined" in 49/50 cases under TAXONOMY-V2. We need to know why before interpreting that result.
- The paper's own taxonomy claim was action routing: NEEDS_INFO cases ask for details (16/16 vs 4/16) and duplicates point to the canonical issue (7/7 vs 0/7). Those numbers came from unequal prompts. This step retests them on the fair responses.
- No new generation in this step. Use existing outputs only.

## Rules

1. Don't edit existing outputs, prompts or the paper. Put everything new in `routing_test/`.
2. Never use the taxonomy class as ground truth for whether a response is correct. Where truth is needed, use tracker facts or my human-audited labels, as stated below.
3. Never drop a case silently. Report every exclusion with its reason.
4. Stop at each CHECKPOINT and wait for my OK.

## Step 0: Commit this file first
```sql
git add routing_and_v2_check.md && git commit -m "Pre-register routing test and V2 check"
```

## Step 1: V2 check (read-only, `bot_test/`, Model A)

Show me:

- a. The full user message for one BOT issue in TAXONOMY-V2 and in RAW, with a diff between them.
- b. Whether the TAXONOMY-V2 closure block contains any raw label text, such as "wontfix". Quote it if it does.
- c. The exact ABANDONED class text the V2 arm received.
- d. For 5 BOT issues (seed 20261024), the gpt-4o-mini TAXONOMY-V2 response. Quote the sentence that made the judge and the lexical check score it as DECLINED.

**CHECKPOINT 1.** Don't fix or rerun anything.

## Step 2: Routing test setup (fair run)

1. Find the 246 fair responses and their inputs. Tell me which files you are using.
2. For each of the 82 inputs, get its closure class. Use my human-audited class where one exists, otherwise the class the taxonomy arm received, and flag which source each case uses.
3. Count the NEEDS_INFO cases (closed for missing information, can't reproduce, or no response from the reporter) and the REDIRECTED cases (duplicates). Compare the counts with the paper's 16 and 7, and explain any difference. Also explain why the earlier check used 34 non-resolved cases when the paper used 36.
4. For each arm, report whether its input contains: (a) a signal that information was missing, (b) a duplicate signal, and (c) the canonical issue's number or link. If (c) appears only in the taxonomy arm's input, say so.

**CHECKPOINT 2.**

## Step 3: Scoring

These definitions are fixed now, before any scoring:

- **ASKS_DETAILS** (NEEDS_INFO cases): the response asks the user for specific missing information (steps to reproduce, logs, app version, device) or to add details to the issue. "Let us know if you have any questions" doesn't count.
- **SAYS_DUPLICATE** (REDIRECTED cases): the response says the problem is tracked in another issue or is a duplicate.
- **GIVES_CANONICAL** (REDIRECTED cases): SAYS_DUPLICATE, plus the canonical issue's number or link. Treat it as a test only if Step 2 found that reference in every arm's input. Otherwise report it as descriptive only.

How to score:

- **Blind sheet for me:** `routing_test/blind_sheet.csv`, with every response for these cases in all 3 arms, shuffled, with the arm removed and empty columns for my labels. Keep the key in `routing_test/blind_key.csv`.
- **Lexical check:** write the patterns in `routing_test/lexical.py` and commit them before scoring.
- **Gemma:** do the same for the Gemma main-rerun responses, in a separate blind sheet.

**CHECKPOINT 3.** I label the sheets.

## Step 4: Analysis, written to `routing_test/results.md`

- Per model and arm: counts and % for each question, with Wilson 95% CIs. My labels are primary. The lexical check is secondary, reported with its agreement with my labels (Cohen's kappa).
- Exact McNemar, taxonomy vs raw, paired by case, for ASKS_DETAILS and SAYS_DUPLICATE, with Holm across these two tests. Report the binary arm for reference only.

## Step 5: FIX_CLAIM by true status

Use the FIX_CLAIM scores already in `bot_test/` for the historical 246 responses and the Gemma main rerun. Split the 82 inputs by true status, using tracker facts, never the taxonomy:

- **FIXED:** Bugzilla resolution FIXED, closed by a commit or merged PR on GitHub, or the equivalent on other trackers.
- **NOT FIXED:** the human-audited non-resolved cases.
- **UNCERTAIN:** everything else.

Report per model and arm: false fix claims (FIX_CLAIM on NOT FIXED), missed fixes (no FIX_CLAIM on FIXED), and the UNCERTAIN count.

## Expected result (written before running)

If raw metadata asks for details and flags duplicates at a similar rate to the taxonomy, the taxonomy's routing claim doesn't hold under fair prompts. Report the result either way.
