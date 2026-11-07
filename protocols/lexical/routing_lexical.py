"""Frozen secondary routing checks. Apply to response text, never taxonomy truth.

Version frozen before scoring: routing-lexical-v1-20261031.
Canonical targets are absent from the registered input population. Therefore
GIVES_CANONICAL is unavailable, not false. Different-issue references are kept
as descriptive candidates only and are never assumed to be canonical targets.
"""
import re

VERSION='routing-lexical-v1-20261031'
DEFINITIONS={
 'ASKS_DETAILS': 'Asks for specific missing information (reproduction steps, logs, app version, device) or to add details to the issue. Generic invitations for questions do not count.',
 'SAYS_DUPLICATE': 'Says the problem is tracked in another issue or is a duplicate.',
 'GIVES_CANONICAL': 'SAYS_DUPLICATE plus the canonical issue number or link; unavailable when the actual target is not supplied or independently established.',
}
REQUEST=r'\b(?:(?:please\s+)?(?:provide|share|send|submit|supply|include|attach|add|post|give|tell\s+us|let\s+us\s+know)|(?:please|could\s+you|can\s+you|you\s+can|you\s+could)\s+report)\b'
ARTIFACT=r'\b(?:steps?\s+to\s+(?:reproduce|replicate)|reproduction\s+(?:steps?|details)|reproduc(?:tion|ing)\s+(?:steps?|instructions)|logs?|logcat|stack\s+traces?|(?:app(?:lication)?|android|os|operating\s+system|software)\s+version|version\s+(?:of\s+)?(?:the\s+)?app|device(?:\s+(?:model|details|information))?|screenshots?)\b'
DETAIL=r'\b(?:more|additional|further|specific|relevant)?\s*(?:details?|information)\b'
ISSUE=r'\b(?:issue|ticket|report|thread|bug\s+report)\b'
PATTERNS={
 'ASKS_DETAILS':[
    REQUEST+r'[^.!?;\n]{0,180}?'+ARTIFACT,
    r'\b(?:could|can|would)\s+you\b[^.!?;\n]{0,45}?'+REQUEST+r'[^.!?;\n]{0,180}?'+ARTIFACT,
    REQUEST+r'[^.!?;\n]{0,80}?'+DETAIL+r'[^.!?;\n]{0,80}?\b(?:to|in|on|for)\b[^.!?;\n]{0,35}?'+ISSUE,
    r'\b(?:update|comment\s+on)\b[^.!?;\n]{0,50}?'+ISSUE+r'[^.!?;\n]{0,80}?'+DETAIL,
 ],
 'SAYS_DUPLICATE':[
    r'\bduplicate(?:d)?\b',
    r'\b(?:tracked|tracking|addressed|handled|discussed|reported)\b[^.!?;\n]{0,70}?\b(?:elsewhere|(?:another|other|original|canonical|upstream)\s+(?:issue|ticket|report|thread))\b',
    r'\b(?:see|follow|refer\s+to|check|continue\s+(?:in|on))\b[^.!?;\n]{0,50}?\b(?:original|other|canonical|linked|related)\s+(?:issue|ticket|thread|discussion)\b',
    r'\bredirected\s+(?:to|elsewhere)\b',
 ],
}
COMPILED={q:[re.compile(p,re.I) for p in patterns] for q,patterns in PATTERNS.items()}
NEGATED=re.compile(r"\b(?:not|never|isn['’]?t|wasn['’]?t|no\s+evidence\s+(?:of|that)|cannot\s+confirm|can['’]?t\s+confirm)\b(?:\W+\w+){0,4}\W*$",re.I)
NEGATED_REQUEST=re.compile(r"\b(?:do\s+not|don['’]?t|no\s+need\s+to|need\s+not)\s*$",re.I)
REFERENCE_PATTERNS=[
 re.compile(r'https?://[^\s<>\[\]()]+/(?:issues|pull|ticket)/(?P<number>\d+)',re.I),
 re.compile(r'https?://[^\s<>\[\]()]+show_bug\.cgi\?id=(?P<number>\d+)',re.I),
 re.compile(r'\b(?:issue|bug|ticket)\s*#?\s*(?P<number>\d+)\b',re.I),
 re.compile(r'(?<!\w)#(?P<number>\d+)\b'),
]
ROUTED_NUMBER=re.compile(r'\b(?:tracked|tracking|duplicate\s+of|redirected\s+to)\b[^.!?;\n]{0,90}?(?:issue|bug|ticket)?\s*#?\s*(\d+)\b',re.I)

def score(response,retrieved_number,canonical_target=None):
    text=' '.join(response.split())
    matches={q:[] for q in COMPILED}
    for q,patterns in COMPILED.items():
        for p in patterns:
            for m in p.finditer(text):
                before=re.split(r'[.!?;]|\bbut\b|\bhowever\b',text[:m.start()],flags=re.I)[-1][-100:]
                if q=='SAYS_DUPLICATE' and NEGATED.search(before):continue
                if q=='ASKS_DETAILS' and NEGATED_REQUEST.search(before):continue
                matches[q].append(m.group())
    refs=sorted({m.group('number') for p in REFERENCE_PATTERNS for m in p.finditer(text)}-{str(retrieved_number)})
    for m in ROUTED_NUMBER.finditer(text):
        if m.group(1)!=str(retrieved_number):matches['SAYS_DUPLICATE'].append(m.group())
    duplicate=bool(matches['SAYS_DUPLICATE'])
    canonical=None if canonical_target is None else duplicate and str(canonical_target) in refs
    return {'ASKS_DETAILS':bool(matches['ASKS_DETAILS']),'SAYS_DUPLICATE':duplicate,
            'GIVES_CANONICAL':canonical,'different_issue_reference_candidates':refs,
            'matches':{q:sorted(set(values)) for q,values in matches.items()}}
