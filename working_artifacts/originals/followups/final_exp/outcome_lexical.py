"""Frozen supplemental STATES_OUTCOME screen from tracker facts, not taxonomy."""
import re
VERSION='tracker-outcome-lexical-v1-20261101'
PATTERNS={
 'duplicate':r'\b(?:duplicate|tracked\s+(?:elsewhere|in\s+another\s+issue)|another\s+(?:issue|ticket))\b',
 'needs_info':r'\b(?:closed|closure|closing)\b.{0,160}\b(?:more\s+information|lack\s+of\s+information|insufficient\s+(?:information|details)|incomplete|needs?\s+(?:more\s+)?info|could\s+not\s+(?:be\s+)?reproduce|cannot\s+(?:be\s+)?reproduce|unable\s+to\s+reproduce|couldn[’\x27]?t\s+(?:be\s+)?reproduce)\b',
 'invalid':r'\b(?:invalid|not\s+(?:considered\s+)?a\s+bug|not\s+a\s+valid\s+(?:bug|issue))\b',
 'notvlc':r'\b(?:not\s+(?:a\s+)?vlc\s+(?:issue|bug)|outside\s+(?:of\s+)?vlc|notvlc)\b',
 'rejected':r'\b(?:won[’\x27]?t\s+fix|wontfix|not\s+planned|declined|rejected|out\s+of\s+scope|will\s+not\s+be\s+(?:fixed|addressed|implemented))\b',
 'inactivity':r'\b(?:closed|closure|closing)\b.{0,150}\b(?:inactivity|inactive|stale|no\s+(?:recent\s+)?activity|automatically|bot)\b|\b(?:bot|automatically|inactivity|stale)\b.{0,150}\bclos(?:ed|ure|ing)\b',
 'configuration_advice':r'\b(?:battery\s+(?:optimization|optimisation|restrictions?|settings?|handling)|samsung.{0,60}battery)\b',
}
def outcome_kind(facts):
    # facts are extracted only from raw tracker fields and event/comment evidence.
    resolution=str(facts.get('native_resolution','')).upper()
    if resolution=='DUPLICATE' or facts.get('marked_duplicate'):return 'duplicate'
    if resolution in {'WORKSFORME','INCOMPLETE'}:return 'needs_info'
    if resolution=='INVALID':return 'invalid'
    if resolution=='NOTVLC':return 'notvlc'
    if facts.get('configuration_advice'):return 'configuration_advice'
    if facts.get('closed_by_bot_no_fix'):return 'inactivity'
    labels=' '.join(facts.get('labels',[]))
    if re.search(r'duplicate',labels,re.I):return 'duplicate'
    if re.search(r"won'?t[ _-]?fix|invalid|not[ _-]?planned|out.of.scope",labels,re.I):return 'rejected'
    if re.search(r'needs?.{0,10}info|cannot.reproduce|incomplete',labels,re.I):return 'needs_info'
    if re.search(r'stale|inactiv',labels,re.I):return 'inactivity'
    if str(facts.get('state_reason','')).upper()=='NOT_PLANNED':return 'rejected'
    return None
def score(response,facts):
    kind=outcome_kind(facts)
    if kind is None:return {'STATES_OUTCOME':None,'evidence_kind':None,'match':None}
    match=re.search(PATTERNS[kind],' '.join(response.split()),re.I)
    return {'STATES_OUTCOME':bool(match),'evidence_kind':kind,'match':match.group() if match else None}
