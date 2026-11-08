from __future__ import annotations

import ast
import re
from dataclasses import dataclass


REJECTED_PATTERNS = (
    "wontfix",
    "won't-fix",
    "won't fix",
    "wont fix",
    "wont-fix",
    "by-design",
    "by design",
    "invalid",
    "not-a-bug",
    "not a bug",
    "not planned",
    "not-planned",
)
STALE_PATTERNS = ("stale", "auto-closed", "auto closed", "inactive")
NEEDS_INFO_PATTERNS = (
    "needs author reply",
    "needs-info",
    "needs info",
    "more info",
    "needs reproduction",
    "needs repro",
    "can't reproduce",
    "cannot reproduce",
    "cant reproduce",
    "unable to reproduce",
    "unconfirmed",
    "insufficient information",
    "insufficient-information",
    "no response",
    "no-response",
)
UPSTREAM_PATTERNS = ("upstream", "third-party", "third party")
LEVEL1 = ("RESOLVED", "REJECTED", "ABANDONED", "REDIRECTED")
PRIMARY_PRIORITY = ("D", "E", "A", "F", "R")
SENSITIVITY_PRIORITIES = (
    ("D", "E", "A", "F", "R"),
    ("D", "A", "E", "F", "R"),
    ("E", "A", "D", "F", "R"),
    ("D", "E", "F", "A", "R"),
)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_labels(value: object) -> list[str]:
    text = clean(value)
    if not text or text.lower() == "nan" or text == "[]":
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            values = [item.get("name", "") if isinstance(item, dict) else item for item in parsed]
            return [re.sub(r"\s+", " ", clean(item).lower()) for item in values if clean(item)]
    except (SyntaxError, ValueError):
        pass
    return [
        re.sub(r"\s+", " ", part.strip().lower())
        for part in re.split(r"[,;]", text)
        if part.strip()
    ]


@dataclass(frozen=True)
class Classification:
    level1: str
    subtype: str
    evidence: str


def _first_matching_label(labels: list[str], patterns: tuple[str, ...]) -> str:
    for label in labels:
        if any(pattern in label for pattern in patterns):
            return label
    return ""


def classify(
    state_reason: object,
    labels_value: object,
    priority: tuple[str, ...] = PRIMARY_PRIORITY,
) -> Classification:
    reason = clean(state_reason).lower().replace("-", "_")
    labels = normalize_labels(labels_value)

    duplicate_label = next((label for label in labels if "duplicate" in label), "")
    rejected_label = _first_matching_label(labels, REJECTED_PATTERNS)
    stale_label = _first_matching_label(labels, STALE_PATTERNS)
    needs_label = _first_matching_label(labels, NEEDS_INFO_PATTERNS)
    upstream_label = _first_matching_label(labels, UPSTREAM_PATTERNS)

    candidates = {
        "D": Classification(
            "REDIRECTED",
            "DUPLICATE",
            "state_reason=duplicate" if reason == "duplicate" else f"duplicate label={duplicate_label}",
        ) if reason == "duplicate" or duplicate_label else None,
        "E": Classification(
            "REJECTED", "EXPLICIT_REJECTION", f"rejection label={rejected_label}"
        ) if rejected_label else None,
        "A": (
            Classification("ABANDONED", "STALE", f"stale/inactive label={stale_label}")
            if stale_label
            else Classification("ABANDONED", "NEEDS_INFO", f"needs-info label={needs_label}")
            if needs_label
            else Classification("ABANDONED", "UPSTREAM", f"upstream label={upstream_label}")
            if upstream_label
            else None
        ),
        "F": Classification("REJECTED", "NOT_PLANNED", "state_reason=not_planned")
        if reason == "not_planned"
        else None,
        "R": Classification("RESOLVED", "COMPLETED", "state_reason=completed")
        if reason == "completed"
        else None,
    }
    for signal in priority:
        candidate = candidates[signal]
        if candidate is not None:
            return candidate
    return Classification(
        "UNCLASSIFIED_CLOSED",
        "",
        f"no classifiable signal; state_reason={reason or '<missing>'}",
    )


def priority_label(priority: tuple[str, ...]) -> str:
    return ">".join(priority)

