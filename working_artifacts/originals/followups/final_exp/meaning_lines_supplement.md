# User-supplied meaning lines

The original final_experiments.md attachment omitted the text after “Meaning lines, fixed now:”. The user supplied the exact lines in chat on 1 November 2026. They are preserved verbatim as values in meaning_lines.json and are committed before constructing TAXONOMY-ONLY inputs.

RESOLVED -> class: RESOLVED; meaning: Closed as fixed or completed.

REJECTED (any subtype) -> class: REJECTED; meaning: Closed by a maintainer without a fix: declined, invalid or out of scope.

ABANDONED / NEEDS_INFO -> class: ABANDONED; meaning: Closed because more information was needed or it could not be reproduced. Not fixed.

ABANDONED / STALE -> class: ABANDONED; meaning: Closed after a period of inactivity. Not fixed, and no maintainer decided against it.

ABANDONED / bot-closed (V2) -> class: ABANDONED; meaning: Closed automatically by a bot. Not fixed, and no maintainer decided against it.

ABANDONED / OTHER -> class: ABANDONED; meaning: Closed without a fix. The reason is not recorded.

REDIRECTED -> class: REDIRECTED; meaning: Closed as a duplicate. It is tracked in another issue.

OPEN -> class: OPEN; meaning: Still open.

The 50 BOT sample issues receive the bot-closed V2 meaning. Fair cases use the class/subtype supplied to the original closure_aware arm, including ABANDONED/OTHER for Nextcloud #2131. That case remains a generated input but is excluded from all analyses under the user's explicit rule. These supplied meanings are generation evidence; they never serve as correctness ground truth.
