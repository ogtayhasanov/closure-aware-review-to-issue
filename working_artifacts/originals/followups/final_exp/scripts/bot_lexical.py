"""Frozen lexical diagnostics. Human review resolves disagreement; these are not gold labels."""
import re

VERSION = 'bot-closure-lexical-v1-20261024'
DEFINITIONS = {
    'DECLINED': 'says or implies that the developers decided not to fix or build it, rejected it, or marked it "won\'t fix" as their decision.',
    'FIX_CLAIM': 'says the problem is fixed, resolved, or coming in an update.',
    'INACTIVITY': 'says it was closed for inactivity, for no recent activity, or automatically.',
}
PATTERNS = {
    'DECLINED': [
        r"\b(?:won['’]?t|will not|would not|not going to)\s+(?:be\s+)?(?:fix(?:ed)?|implement(?:ed)?|address(?:ed)?|support(?:ed)?|pursue(?:d)?|develop(?:ed)?)\b",
        r"\b(?:wontfix|won['’]?t[ _-]fix|not[ _-]planned|by[ _-]design|out of scope|not a bug|invalid)\b",
        r"\b(?:declined|rejected|decided against|no plans to|not planned for|not planning to|chose not to|chosen not to)\b",
    ],
    'FIX_CLAIM': [
        r'\b(?:fixed|resolved|patched|corrected|implemented|addressed)\b',
        r'\b(?:fix|solution|resolution)\s+(?:is|will be|has been)\s+(?:available|included|released|delivered|coming)\b',
        r'\b(?:will be|being|to be)\s+(?:fixed|resolved|addressed|implemented)\b',
        r'\b(?:coming|included|available|addressed)\b.{0,45}\b(?:upcoming|next|future|new)\s+(?:update|release|version)\b',
    ],
    'INACTIVITY': [
        r'\b(?:inactivity|inactive|stale|automatically|auto[ -]?closed|no (?:recent |further )?activity|lack of (?:recent )?activity)\b',
        r'\b(?:bot|automation)\b.{0,60}\bclos(?:ed|ure|ing)\b',
        r'\bclos(?:ed|ure|ing)\b.{0,60}\b(?:bot|automation)\b',
    ],
}
COMPILED = {k: [re.compile(x, re.I) for x in patterns] for k, patterns in PATTERNS.items()}
# Exclude explicit negative fix statements while retaining claims in other clauses.
NEGATED_FIX = re.compile(
    r"\b(?:not|never|no|isn['’]?t|wasn['’]?t|hasn['’]?t|haven['’]?t|doesn['’]?t|didn['’]?t|won['’]?t|cannot|can['’]?t)\b"
    r"(?:\W+\w+){0,6}\W*$", re.I)
NEGATED_DECLINE = re.compile(r"\b(?:not|never|no evidence (?:of|that)|does not mean)\b(?:\W+\w+){0,3}\W*$", re.I)

def score(text):
    text = ' '.join(text.split())
    result = {}
    for question, patterns in COMPILED.items():
        found = False
        for pattern in patterns:
            for match in pattern.finditer(text):
                before = re.split(r'[.!?;]|\bbut\b|\bhowever\b', text[:match.start()], flags=re.I)[-1][-100:]
                if question == 'FIX_CLAIM' and NEGATED_FIX.search(before):
                    continue
                if question == 'DECLINED' and re.fullmatch(r'rejected|declined', match.group(), re.I) and NEGATED_DECLINE.search(before):
                    continue
                found = True
        result[question] = found
    return result
