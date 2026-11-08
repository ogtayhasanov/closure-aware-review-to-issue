# Bot-closure experiment — Checkpoint 1

Status: preparation complete. No new model calls or scoring. Awaiting user OK.

Preregistration commit: `e0bf6d9` in `C:\Users\Ogtay\Desktop\test`.

## Reused files

- `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\rq3_protocol.py`: identical SYSTEM_PROMPT and render().
- `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\run_rq3.py`: call_openai(), model, seed and generation settings.
- `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\private_working\new_responses_246.jsonl`: completed historical run (read only).
- `C:\Users\Ogtay\Downloads\TOSEM_RQ3_Run\tosem_rq3_fair\private_working\real_82_native_staged.jsonl`: main rerun inputs (read only).
- `C:\Users\Ogtay\Desktop\test\closure_provenance.py`: imported classification and actor functions.
- `C:\Users\Ogtay\Downloads\run_haring_rrf_frozen_e2e.py`: AST-read existing taxonomy tuples; pipeline never executed.

All 246 historical message hashes reproduce exactly from the saved 82 cases and current renderer.
System SHA-256: `614bb4a0cc94c13957acfb3e0879e8f8a08ffa54d8d50cd4c66c5b6dfbae4d7e`.
Generation settings read from code: `{"max_tokens": 220, "model_requested": "gpt-4o-mini-2024-07-18", "seed": 20261020, "temperature": 0}`.
Historical returned model IDs: gpt-4o-mini-2024-07-18.

## Sample

| Group | Signal | Jitsi | Total |
|---|---:|---:|---:|
| BOT | 25 | 25 | 50 |
| HUMAN | 3 | 27 | 30 |

Eligible pools: BOT 1,687 Signal + 1,290 Jitsi; HUMAN 3 Signal + 27 Jitsi.
The HUMAN group is smaller than 50 because only 30 qualify. All 30 are retained.
Seed: 20261024. No classification exceptions. No duplicate scan rows.
18,290 unique scanned issues = 80 sampled + 18,210 excluded. Every exclusion is in exclusions.csv.

| Exclusion reason (overlapping) | Count |
|---|---:|
| no_wontfix_label | 14800 |
| close_count_not_one | 674 |
| reopened | 632 |
| linked_fix | 1544 |
| v1_redirected | 288 |
| mixed_bot_human | 348 |
| actor_not_known_bot_or_user | 1 |
| eligible_not_sampled_BOT | 2927 |

Unknown label-adder exclusions: 0. Mixed bot/human cases after eligibility filters: 348.
Sampling exclusions: 2,927 eligible BOT issues. No eligible HUMAN issue was dropped.

## Preparation decisions for review

- Extra bot: automated-signal (API type User). Inferred automation from account name and bulk scan closures on 2018-04-02; the public profile has no explanatory bio. No wontfix-labelled issue uses this closer, so the choice has no effect on either sample group.
- Both scan cursors are DONE. Original summarize() was rerun; its output files were redirected here to preserve existing provenance outputs.
- All 80 issue bodies were fetched through the GitHub connector GET-issue operation. No comments were fetched for sampled issues or supplied to prompts. Body excerpt remains exactly the original renderer limit of 1,200 characters.
- Review and issue title use the scan title verbatim. Current REST native closure metadata is shared across arms. Every scan/REST difference is in metadata_drift.json; there are no exclusions caused by differences.
- The original shared prompt has no prose class descriptions. Existing REJECTED/wontfix/REJECTED and ABANDONED/OTHER/ABANDONED tuples are reused. OTHER avoids adding a new subtype or inferring an inactivity reason solely from the bot closer. No legacy unequal system prompt or action description is imported.
- RAW is the unmodified renderer output. RAW+CLOSER appends exactly the three prescribed provenance lines. Both taxonomy arms use unmodified closure_aware rendering with the corresponding existing tuple.
- Every issue has four prompts with identical common prefix and final instruction; only closure data differ. All 30 HUMAN taxonomy prompt pairs are byte-identical.

## Later-stage dependency

The reused 246-run kit provides lexical action diagnostics and a human status rubric, but no implemented metric explicitly named specific closure reason conveyed. No replacement metric has been written. Its original implementation or an agreed definition must be established before the Model B main-run analysis.

## Representative full prompts and differences

The system message is identical for all 320 prompts and saved in system_prompt.txt. Full user messages follow. Diffs compare each alternative with RAW.

### BOT: signalapp/Signal-Android#8103

https://github.com/signalapp/Signal-Android/issues/8103

#### RAW

```text
REAL USER REVIEW:
Forwarded videos lose their thumbnail.

RETRIEVED ISSUE:
- Tracker: signalapp/Signal-Android (GitHub)
- Issue #8103: Forwarded videos lose their thumbnail.
- Binary state: closed
- URL: https://github.com/signalapp/Signal-Android/issues/8103
- Issue body excerpt: This is follow up on #7783. The extension problem was addressed, but forwarded videos are missing their thumbnail.

Steps to reproduce:
1. Send a video that has a thumbnail (requires Android >= M)
1. Long-press > Forward
1. Select any contact
1. Note that the video will send, but will have no thumbnail

Signal version: 4.24.x

RAW TRACKER CLOSURE FIELDS:
- closed_at: 2022-02-04T14:14:41Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

Write a response to the review.
```

#### RAW+CLOSER

```text
REAL USER REVIEW:
Forwarded videos lose their thumbnail.

RETRIEVED ISSUE:
- Tracker: signalapp/Signal-Android (GitHub)
- Issue #8103: Forwarded videos lose their thumbnail.
- Binary state: closed
- URL: https://github.com/signalapp/Signal-Android/issues/8103
- Issue body excerpt: This is follow up on #7783. The extension problem was addressed, but forwarded videos are missing their thumbnail.

Steps to reproduce:
1. Send a video that has a thumbnail (requires Android >= M)
1. Long-press > Forward
1. Select any contact
1. Note that the video will send, but will have no thumbnail

Signal version: 4.24.x

RAW TRACKER CLOSURE FIELDS:
- closed_at: 2022-02-04T14:14:41Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed
closed_by: stale (Bot)
closed_via: none
wontfix label added by: stale (Bot)

Write a response to the review.
```

#### TAXONOMY-V1

```text
REAL USER REVIEW:
Forwarded videos lose their thumbnail.

RETRIEVED ISSUE:
- Tracker: signalapp/Signal-Android (GitHub)
- Issue #8103: Forwarded videos lose their thumbnail.
- Binary state: closed
- URL: https://github.com/signalapp/Signal-Android/issues/8103
- Issue body excerpt: This is follow up on #7783. The extension problem was addressed, but forwarded videos are missing their thumbnail.

Steps to reproduce:
1. Send a video that has a thumbnail (requires Android >= M)
1. Long-press > Forward
1. Select any contact
1. Note that the video will send, but will have no thumbnail

Signal version: 4.24.x

RAW TRACKER CLOSURE FIELDS:
- closed_at: 2022-02-04T14:14:41Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: REJECTED
- subtype: wontfix
- action_l1: REJECTED

Write a response to the review.
```

#### TAXONOMY-V2

```text
REAL USER REVIEW:
Forwarded videos lose their thumbnail.

RETRIEVED ISSUE:
- Tracker: signalapp/Signal-Android (GitHub)
- Issue #8103: Forwarded videos lose their thumbnail.
- Binary state: closed
- URL: https://github.com/signalapp/Signal-Android/issues/8103
- Issue body excerpt: This is follow up on #7783. The extension problem was addressed, but forwarded videos are missing their thumbnail.

Steps to reproduce:
1. Send a video that has a thumbnail (requires Android >= M)
1. Long-press > Forward
1. Select any contact
1. Note that the video will send, but will have no thumbnail

Signal version: 4.24.x

RAW TRACKER CLOSURE FIELDS:
- closed_at: 2022-02-04T14:14:41Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: ABANDONED
- subtype: OTHER
- action_l1: ABANDONED

Write a response to the review.
```

```diff
--- RAW
+++ RAW+CLOSER
@@ -21,5 +21,8 @@
 - labels: ["wontfix"]
 - state: closed
 - state_reason: completed
+closed_by: stale (Bot)
+closed_via: none
+wontfix label added by: stale (Bot)
 
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V1
@@ -22,4 +22,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: REJECTED
+- subtype: wontfix
+- action_l1: REJECTED
+
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V2
@@ -22,4 +22,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: ABANDONED
+- subtype: OTHER
+- action_l1: ABANDONED
+
 Write a response to the review.
```

### BOT: jitsi/jitsi-meet#1209

https://github.com/jitsi/jitsi-meet/issues/1209

#### RAW

```text
REAL USER REVIEW:
Jitsi Behind OpenVPN

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #1209: Jitsi Behind OpenVPN
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/1209
- Issue body excerpt: I have the Jitsi-Meet package installed from the official repo. The default install works great with no tweaking.

However, when I modify the nginx file for my Jitsi-Meet page to listen on the VPN interface, I am able to connect to the VPN, browse to my Jitsi-Meet page, enter a chat name, proceed to the chat (where I'm asked to share my mic/cam) then nothing happens. I'm stuck on the blue page shown in the attached screenshot.

Switching the nginx file back to listening on all interfaces fixes the issue to where the service works as expected but is accessible from the internet which is not the desired configuration.

My camera light is on and Firefox thinks it is sharing the mic and cam with something.
![jitsi error](https://cloud.githubusercontent.com/assets/9064374/21335536/9b3e973a-c62d-11e6-8c58-05cfb0d1e003.PNG)


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2018-12-11T00:35:52Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

Write a response to the review.
```

#### RAW+CLOSER

```text
REAL USER REVIEW:
Jitsi Behind OpenVPN

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #1209: Jitsi Behind OpenVPN
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/1209
- Issue body excerpt: I have the Jitsi-Meet package installed from the official repo. The default install works great with no tweaking.

However, when I modify the nginx file for my Jitsi-Meet page to listen on the VPN interface, I am able to connect to the VPN, browse to my Jitsi-Meet page, enter a chat name, proceed to the chat (where I'm asked to share my mic/cam) then nothing happens. I'm stuck on the blue page shown in the attached screenshot.

Switching the nginx file back to listening on all interfaces fixes the issue to where the service works as expected but is accessible from the internet which is not the desired configuration.

My camera light is on and Firefox thinks it is sharing the mic and cam with something.
![jitsi error](https://cloud.githubusercontent.com/assets/9064374/21335536/9b3e973a-c62d-11e6-8c58-05cfb0d1e003.PNG)


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2018-12-11T00:35:52Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed
closed_by: stale (Bot)
closed_via: none
wontfix label added by: stale (Bot)

Write a response to the review.
```

#### TAXONOMY-V1

```text
REAL USER REVIEW:
Jitsi Behind OpenVPN

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #1209: Jitsi Behind OpenVPN
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/1209
- Issue body excerpt: I have the Jitsi-Meet package installed from the official repo. The default install works great with no tweaking.

However, when I modify the nginx file for my Jitsi-Meet page to listen on the VPN interface, I am able to connect to the VPN, browse to my Jitsi-Meet page, enter a chat name, proceed to the chat (where I'm asked to share my mic/cam) then nothing happens. I'm stuck on the blue page shown in the attached screenshot.

Switching the nginx file back to listening on all interfaces fixes the issue to where the service works as expected but is accessible from the internet which is not the desired configuration.

My camera light is on and Firefox thinks it is sharing the mic and cam with something.
![jitsi error](https://cloud.githubusercontent.com/assets/9064374/21335536/9b3e973a-c62d-11e6-8c58-05cfb0d1e003.PNG)


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2018-12-11T00:35:52Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: REJECTED
- subtype: wontfix
- action_l1: REJECTED

Write a response to the review.
```

#### TAXONOMY-V2

```text
REAL USER REVIEW:
Jitsi Behind OpenVPN

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #1209: Jitsi Behind OpenVPN
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/1209
- Issue body excerpt: I have the Jitsi-Meet package installed from the official repo. The default install works great with no tweaking.

However, when I modify the nginx file for my Jitsi-Meet page to listen on the VPN interface, I am able to connect to the VPN, browse to my Jitsi-Meet page, enter a chat name, proceed to the chat (where I'm asked to share my mic/cam) then nothing happens. I'm stuck on the blue page shown in the attached screenshot.

Switching the nginx file back to listening on all interfaces fixes the issue to where the service works as expected but is accessible from the internet which is not the desired configuration.

My camera light is on and Firefox thinks it is sharing the mic and cam with something.
![jitsi error](https://cloud.githubusercontent.com/assets/9064374/21335536/9b3e973a-c62d-11e6-8c58-05cfb0d1e003.PNG)


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2018-12-11T00:35:52Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: ABANDONED
- subtype: OTHER
- action_l1: ABANDONED

Write a response to the review.
```

```diff
--- RAW
+++ RAW+CLOSER
@@ -21,5 +21,8 @@
 - labels: ["wontfix"]
 - state: closed
 - state_reason: completed
+closed_by: stale (Bot)
+closed_via: none
+wontfix label added by: stale (Bot)
 
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V1
@@ -22,4 +22,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: REJECTED
+- subtype: wontfix
+- action_l1: REJECTED
+
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V2
@@ -22,4 +22,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: ABANDONED
+- subtype: OTHER
+- action_l1: ABANDONED
+
 Write a response to the review.
```

### HUMAN: jitsi/jitsi-meet#568

https://github.com/jitsi/jitsi-meet/issues/568

#### RAW

```text
REAL USER REVIEW:
Adding API Key To Jitsi Room Creation

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #568: Adding API Key To Jitsi Room Creation
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/568
- Issue body excerpt: I would like to add an application API key to the room creation on Jitsi-Meet, so as to restrict access to different clients that I provide my services to. Since I would be hosting Jitsi on a dedicated server, I would like only the authenticated clients to create rooms on my installation. Skylink.io provides a similar mechanism.

Can anyone tell me if I can add in some API the API key parameter? Or if it can be added as a new feature in Jitsi??


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2016-03-30T12:46:40Z
- labels: ["wontfix", "api", "question"]
- state: closed
- state_reason: completed

Write a response to the review.
```

#### RAW+CLOSER

```text
REAL USER REVIEW:
Adding API Key To Jitsi Room Creation

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #568: Adding API Key To Jitsi Room Creation
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/568
- Issue body excerpt: I would like to add an application API key to the room creation on Jitsi-Meet, so as to restrict access to different clients that I provide my services to. Since I would be hosting Jitsi on a dedicated server, I would like only the authenticated clients to create rooms on my installation. Skylink.io provides a similar mechanism.

Can anyone tell me if I can add in some API the API key parameter? Or if it can be added as a new feature in Jitsi??


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2016-03-30T12:46:40Z
- labels: ["wontfix", "api", "question"]
- state: closed
- state_reason: completed
closed_by: damencho (User)
closed_via: none
wontfix label added by: luixxiul (User)

Write a response to the review.
```

#### TAXONOMY-V1

```text
REAL USER REVIEW:
Adding API Key To Jitsi Room Creation

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #568: Adding API Key To Jitsi Room Creation
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/568
- Issue body excerpt: I would like to add an application API key to the room creation on Jitsi-Meet, so as to restrict access to different clients that I provide my services to. Since I would be hosting Jitsi on a dedicated server, I would like only the authenticated clients to create rooms on my installation. Skylink.io provides a similar mechanism.

Can anyone tell me if I can add in some API the API key parameter? Or if it can be added as a new feature in Jitsi??


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2016-03-30T12:46:40Z
- labels: ["wontfix", "api", "question"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: REJECTED
- subtype: wontfix
- action_l1: REJECTED

Write a response to the review.
```

#### TAXONOMY-V2

```text
REAL USER REVIEW:
Adding API Key To Jitsi Room Creation

RETRIEVED ISSUE:
- Tracker: jitsi/jitsi-meet (GitHub)
- Issue #568: Adding API Key To Jitsi Room Creation
- Binary state: closed
- URL: https://github.com/jitsi/jitsi-meet/issues/568
- Issue body excerpt: I would like to add an application API key to the room creation on Jitsi-Meet, so as to restrict access to different clients that I provide my services to. Since I would be hosting Jitsi on a dedicated server, I would like only the authenticated clients to create rooms on my installation. Skylink.io provides a similar mechanism.

Can anyone tell me if I can add in some API the API key parameter? Or if it can be added as a new feature in Jitsi??


RAW TRACKER CLOSURE FIELDS:
- closed_at: 2016-03-30T12:46:40Z
- labels: ["wontfix", "api", "question"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: REJECTED
- subtype: wontfix
- action_l1: REJECTED

Write a response to the review.
```

```diff
--- RAW
+++ RAW+CLOSER
@@ -16,5 +16,8 @@
 - labels: ["wontfix", "api", "question"]
 - state: closed
 - state_reason: completed
+closed_by: damencho (User)
+closed_via: none
+wontfix label added by: luixxiul (User)
 
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V1
@@ -17,4 +17,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: REJECTED
+- subtype: wontfix
+- action_l1: REJECTED
+
 Write a response to the review.
```

```diff
--- RAW
+++ TAXONOMY-V2
@@ -17,4 +17,9 @@
 - state: closed
 - state_reason: completed
 
+NORMALIZED TAXONOMY FIELDS:
+- l1_class: REJECTED
+- subtype: wontfix
+- action_l1: REJECTED
+
 Write a response to the review.
```
