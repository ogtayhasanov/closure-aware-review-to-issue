# TAXONOMY-ONLY input review — Checkpoint 1

Instructions committed first as `fce3086081968dc950d972e24a57bcd5def70699`. User-supplied meaning lines committed as `f8f329f76c0c5cd772d9f704763ba99b55d22c0c` before constructing inputs.

**Prepared 162 inputs: 50 BOT + 30 HUMAN + 82 fair cases. No generation or judging has started.**

Every new user message starts from the exact saved RAW/raw_metadata message. Only the heading and lines of the raw closure block are replaced. For all 162 inputs, the UTF-8 bytes of the prefix and suffix match exactly, including every Binary state line and the final instruction. The shared system message is unchanged. The new closure block contains only class and the exact user-supplied meaning line; raw labels are not copied into it. Existing review/title/body text remains unchanged and could itself contain label-like words.

## Settings read from saved manifests

- Model A: gpt-4o-mini-2024-07-18, OpenAI, temperature 0, max_tokens 220, seed 20261020.
- Model B: gemma-4-26b-a4b-it, Google native API, temperature 0, maxOutputTokens 220, thinkingLevel minimal, API seed omitted, as in bot_test.
- Judge configuration retained: requested gpt-5.4-nano (reference returned snapshot gpt-5.4-nano-2026-03-17), temperature 0, reasoning none, max_completion_tokens 80.
- Shared system SHA-256: `614bb4a0cc94c13957acfb3e0879e8f8a08ffa54d8d50cd4c66c5b6dfbae4d7e`.

## Exclusions and frozen evidence

Nextcloud #2131 remains ABANDONED/OTHER exactly as received, with meaning “Closed without a fix. The reason is not recorded.” It is retained for generation but explicitly excluded from all analyses. The tracker refresh establishes that it was fixed by merged PR #4470; no taxonomy class is used as correctness truth. This leaves 35 of the original 36 fair audit cases, hence 140 GPT-4o-mini responses for the later four-arm audit. No other case is excluded.

Nextcloud #3425 remains included. The later audit will include its closing-comment evidence about Samsung battery restrictions and logs, separate from the supplied taxonomy block. No original tracker snapshot, message, response, earlier checkpoint, or manuscript has been edited.

## Full example messages and diffs

### BOT: jitsi/jitsi-meet #1209

Selection is deterministic as described in prepare_inputs.py, without examining generated outcomes.

TAXONOMY-ONLY user message:

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


CLOSURE:
- class: ABANDONED
- meaning: Closed automatically by a bot. Not fixed, and no maintainer decided against it.

Write a response to the review.
```

RAW user message:

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

Exact change (RAW → TAXONOMY-ONLY):

```diff
--- RAW
+++ TAXONOMY-ONLY
@@ -16,10 +16,8 @@
 ![jitsi error](https://cloud.githubusercontent.com/assets/9064374/21335536/9b3e973a-c62d-11e6-8c58-05cfb0d1e003.PNG)
 
 
-RAW TRACKER CLOSURE FIELDS:
-- closed_at: 2018-12-11T00:35:52Z
-- labels: ["wontfix"]
-- state: closed
-- state_reason: completed
+CLOSURE:
+- class: ABANDONED
+- meaning: Closed automatically by a bot. Not fixed, and no maintainer decided against it.
 
 Write a response to the review.
```

### HUMAN: jitsi/jitsi-meet #568

Selection is deterministic as described in prepare_inputs.py, without examining generated outcomes.

TAXONOMY-ONLY user message:

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


CLOSURE:
- class: REJECTED
- meaning: Closed by a maintainer without a fix: declined, invalid or out of scope.

Write a response to the review.
```

RAW user message:

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

Exact change (RAW → TAXONOMY-ONLY):

```diff
--- RAW
+++ TAXONOMY-ONLY
@@ -11,10 +11,8 @@
 Can anyone tell me if I can add in some API the API key parameter? Or if it can be added as a new feature in Jitsi??
 
 
-RAW TRACKER CLOSURE FIELDS:
-- closed_at: 2016-03-30T12:46:40Z
-- labels: ["wontfix", "api", "question"]
-- state: closed
-- state_reason: completed
+CLOSURE:
+- class: REJECTED
+- meaning: Closed by a maintainer without a fix: declined, invalid or out of scope.
 
 Write a response to the review.
```

### fair NEEDS_INFO: nextcloud/android (GitHub) #1514

Selection is deterministic as described in prepare_inputs.py, without examining generated outcomes.

TAXONOMY-ONLY user message:

```text
REAL USER REVIEW:
Absolutely destroys battery life. Phone always lasts all day well past midnight. Had it installed for 3 days and will now go from fully charged at 7am to dead at 5pm with hardly any phone use and no phone calls. Android reporting app responsible for 19% of battery drain. Can't keep it installed like that.

RETRIEVED ISSUE:
- Tracker: nextcloud/android (GitHub)
- Issue #1514: Battery drain
- Binary state: closed
- URL: https://github.com/nextcloud/android/issues/1514
- Issue body excerpt: ### Actual behaviour
-Tell us what happens
It never stop uploading the same photo
### Expected behaviour
-Tell us what should happen
upload the  the photo once
### Steps to reproduce
1. Use autophoto upload
2. Never stops upload the same photo


### Environment data
Android version:

Device model: 

Stock or customized system:

Nextcloud app version:

Nextcloud server version:12.02

### Logs
#### Web server error log
```
Insert your webserver log here
```

#### Nextcloud log (data/nextcloud.log)
```
Insert your Nextcloud log here
```
**NOTE:** Be super sure to remove sensitive data like passwords, note that everybody can look here! You can use the Issue Template application to prefill some of the required information: https://apps.nextcloud.com/apps/issuetemplate

CLOSURE:
- class: ABANDONED
- meaning: Closed because more information was needed or it could not be reproduced. Not fixed.

Write a response to the review.
```

RAW user message:

```text
REAL USER REVIEW:
Absolutely destroys battery life. Phone always lasts all day well past midnight. Had it installed for 3 days and will now go from fully charged at 7am to dead at 5pm with hardly any phone use and no phone calls. Android reporting app responsible for 19% of battery drain. Can't keep it installed like that.

RETRIEVED ISSUE:
- Tracker: nextcloud/android (GitHub)
- Issue #1514: Battery drain
- Binary state: closed
- URL: https://github.com/nextcloud/android/issues/1514
- Issue body excerpt: ### Actual behaviour
-Tell us what happens
It never stop uploading the same photo
### Expected behaviour
-Tell us what should happen
upload the  the photo once
### Steps to reproduce
1. Use autophoto upload
2. Never stops upload the same photo


### Environment data
Android version:

Device model: 

Stock or customized system:

Nextcloud app version:

Nextcloud server version:12.02

### Logs
#### Web server error log
```
Insert your webserver log here
```

#### Nextcloud log (data/nextcloud.log)
```
Insert your Nextcloud log here
```
**NOTE:** Be super sure to remove sensitive data like passwords, note that everybody can look here! You can use the Issue Template application to prefill some of the required information: https://apps.nextcloud.com/apps/issuetemplate

RAW TRACKER CLOSURE FIELDS:
- closed_at: 2018-01-15T06:24:45Z
- labels: ["bug", "feature:AutoUpload", "needs info/discussion"]
- state: closed

Write a response to the review.
```

Exact change (RAW → TAXONOMY-ONLY):

```diff
--- RAW
+++ TAXONOMY-ONLY
@@ -40,9 +40,8 @@
 ```
 **NOTE:** Be super sure to remove sensitive data like passwords, note that everybody can look here! You can use the Issue Template application to prefill some of the required information: https://apps.nextcloud.com/apps/issuetemplate
 
-RAW TRACKER CLOSURE FIELDS:
-- closed_at: 2018-01-15T06:24:45Z
-- labels: ["bug", "feature:AutoUpload", "needs info/discussion"]
-- state: closed
+CLOSURE:
+- class: ABANDONED
+- meaning: Closed because more information was needed or it could not be reproduced. Not fixed.
 
 Write a response to the review.
```

## Shared system message

```text
You are a developer-support assistant. Write a concise, empathetic response to a real app review using only the supplied issue evidence.

Tell the user accurately what happened to the issue, using only the supplied information.
Do not claim the issue was fixed unless the supplied information says so.
If it was closed because more information was needed, ask for reproduction steps, app version, device, and logs.
If it was closed as a duplicate or is tracked elsewhere, say that it is tracked elsewhere.

If the issue is open, say that it is open and tracked; do not claim anyone is working on it without explicit evidence.
Cite the retrieved issue number, and include its URL when one is supplied.
Do not invent versions, releases, dates, commits, causes, fixes, issue numbers, or developer promises.
Keep the response under 100 words.
```

**Stopped at CHECKPOINT 1.** Awaiting the user’s OK before any new responses, scores, human audit sheet, prevalence scan, or release package is produced.
