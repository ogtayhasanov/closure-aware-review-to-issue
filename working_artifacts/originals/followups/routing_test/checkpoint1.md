# V2 check — Checkpoint 1

Pre-registration commit: `0b83e2c` (Pre-register routing test and V2 check).

Existing Model A outputs only. No generation, rescoring by a model, prompt edits, or paper edits. The frozen lexical function is used only to verify the saved scores and locate supporting text.

## Finding

All 50 BOT V2 prompts retain the raw `wontfix` label and append only three normalized fields. There is no prose definition of ABANDONED and no explanation in these fields that a bot closed the issue. Thus V2 tested raw tracker fields plus a terse taxonomy code. The examples below show responses interpreting the retained label as a decision not to address the issue. This is evidence of a plausible prompt conflict; it does not establish a causal explanation or measure a corrected prompt.

## a. Full user messages and diff

Example: [jitsi/jitsi-meet#1209](https://github.com/jitsi/jitsi-meet/issues/1209). Selected as the first BOT case sorted by repository and numeric issue number.

### TAXONOMY-V2

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

### RAW

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

### Unified diff (RAW → TAXONOMY-V2)

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

Both arms use the same saved system prompt. Its full text is included below for context.

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

## b. Exact V2 closure block

```text
- closed_at: 2018-12-11T00:35:52Z
- labels: ["wontfix"]
- state: closed
- state_reason: completed

NORMALIZED TAXONOMY FIELDS:
- l1_class: ABANDONED
- subtype: OTHER
- action_l1: ABANDONED
```

Yes: in this example the raw label line is exactly `- labels: ["wontfix"]`. All 50 BOT V2 prompts contain `wontfix` in their raw labels; 14 also include other labels.

## c. Exact ABANDONED class text

```text
- l1_class: ABANDONED
- subtype: OTHER
- action_l1: ABANDONED
```

These are the complete normalized taxonomy fields received by the model. No descriptive ABANDONED class text was supplied in the user or shared system message. This same three-field block occurs in all 50 BOT V2 inputs.

## d. Five seeded BOT responses

Sampling: Python `random.Random(20261024).sample(sorted_BOT_cases, 5)`, with the 50 cases sorted by `(repo, numeric issue number)`. No filtering on the response or scores; all five sampled cases are shown and none excluded.

The judge saved boolean labels only, with no sentence-level rationale. Consequently the quotations below are supporting sentences identified from the saved responses and frozen lexical matches, not a recorded explanation from the judge. Judge and lexical DECLINED values are reported separately.

### 1. signalapp/Signal-Android#11910

Source: https://github.com/signalapp/Signal-Android/issues/11910

Saved DECLINED: judge **True**, lexical **True**.

Full saved response:

> Thank you for your feedback. The issue you mentioned, "Auto-play audio stopped by text message," has been closed as it was marked with a "wontfix" label. You can view the details [here](https://github.com/signalapp/Signal-Android/issues/11910). If you have further concerns or need assistance, please feel free to reach out.

Sentence(s) supporting DECLINED:

> The issue you mentioned, "Auto-play audio stopped by text message," has been closed as it was marked with a "wontfix" label.

Exact lexical matches: `wontfix`.

### 2. jitsi/jitsi-meet#4913

Source: https://github.com/jitsi/jitsi-meet/issues/4913

Saved DECLINED: judge **True**, lexical **True**.

Full saved response:

> Thank you for your suggestion regarding the "start audio/video muted" setting. This feature request has been closed as it was marked "wontfix" by the team, meaning it will not be implemented. You can view the details of the issue here: [Issue #4913](https://github.com/jitsi/jitsi-meet/issues/4913). We appreciate your input and encourage you to share any other ideas you may have!

Sentence(s) supporting DECLINED:

> This feature request has been closed as it was marked "wontfix" by the team, meaning it will not be implemented.

Exact lexical matches: `will not be implemented`, `wontfix`.

### 3. signalapp/Signal-Android#13795

Source: https://github.com/signalapp/Signal-Android/issues/13795

Saved DECLINED: judge **True**, lexical **True**.

Full saved response:

> Thank you for your feedback. The issue you reported about not being able to play audio messages on Android is tracked as issue #13795 on GitHub, which has been closed with a "wontfix" status. You can view it here: [Issue #13795](https://github.com/signalapp/Signal-Android/issues/13795). Unfortunately, it seems this issue will not be addressed further. If you have any additional details or specific reproduction steps, please share them, and we can look into it further.

Sentence(s) supporting DECLINED:

> The issue you reported about not being able to play audio messages on Android is tracked as issue #13795 on GitHub, which has been closed with a "wontfix" status.
> Unfortunately, it seems this issue will not be addressed further.

Exact lexical matches: `will not be addressed`, `wontfix`.

### 4. jitsi/jitsi-meet#2134

Source: https://github.com/jitsi/jitsi-meet/issues/2134

Saved DECLINED: judge **True**, lexical **True**.

Full saved response:

> Thank you for your feedback! The issue regarding the invite button over the filmstrip has been closed as "wontfix" and is tracked under issue #2134. You can view it here: [Issue #2134](https://github.com/jitsi/jitsi-meet/issues/2134). Unfortunately, it seems that this option will not be addressed. If you have any further questions or need assistance, feel free to reach out!

Sentence(s) supporting DECLINED:

> The issue regarding the invite button over the filmstrip has been closed as "wontfix" and is tracked under issue #2134.
> Unfortunately, it seems that this option will not be addressed.

Exact lexical matches: `will not be addressed`, `wontfix`.

### 5. jitsi/jitsi-meet#7299

Source: https://github.com/jitsi/jitsi-meet/issues/7299

Saved DECLINED: judge **True**, lexical **True**.

Full saved response:

> Thank you for your feedback regarding the startAudioOnly feature in the mobile app. This issue has been closed as it was marked with a "wontfix" label, indicating that it will not be addressed further. You can view the details of the issue here: [Issue #7299](https://github.com/jitsi/jitsi-meet/issues/7299). If you have any other concerns or need assistance, please feel free to reach out.

Sentence(s) supporting DECLINED:

> This issue has been closed as it was marked with a "wontfix" label, indicating that it will not be addressed further.

Exact lexical matches: `will not be addressed`, `wontfix`.

## Source integrity and checkpoint

Canonical source directory: `C:\Users\Ogtay\Desktop\test\bot_test`. Its six inspected files match the existing workspace mirror byte for byte. SHA-256 hashes were checked before and after inspection; no source changed. See `v2_check_evidence.json` for hashes and sample identities.

**Stopped at CHECKPOINT 1.** No routing setup, routing scoring, fixes, or reruns performed.
