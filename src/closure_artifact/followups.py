from __future__ import annotations

import math
from collections import Counter

from .metrics import cohen_kappa, exact_mcnemar_p, holm_adjust, parse_bool, wilson_interval

CORE_SCORES = tuple(
    f"{source}_{endpoint}"
    for source in ("judge", "lexical")
    for endpoint in ("declined", "fix_claim", "inactivity")
)
AUDIT_SCORES = CORE_SCORES + (
    "judge_states_outcome", "lexical_states_outcome",
    "judge_no_false_fix", "lexical_no_false_fix",
)
ORIGINAL_BOT_ARMS = {"RAW", "RAW+CLOSER", "TAXONOMY-V1", "TAXONOMY-V2"}
ORIGINAL_FAIR_ARMS = {"RAW", "BINARY", "CLOSURE-AWARE"}


def switch_arm(case: dict[str, str]) -> str:
    """Select a saved response using the frozen tracker-provenance decision."""
    eligible = (
        case["tracker"] == "GitHub"
        and case["switch_state"] == "closed"
        and case["closer_type"] == "bot"
        and case["linked_fix"] == "0"
    )
    return "TAXONOMY-ONLY" if eligible else "RAW"


def _group_cases(cases):
    fair = [row for row in cases if row["dataset"] == "fair"]
    included = [row for row in fair if not row["analysis_exclusion"]]
    return {
        "BOT": [row["case_id"] for row in cases if row["probe_group"] == "BOT"],
        "HUMAN": [row["case_id"] for row in cases if row["probe_group"] == "HUMAN"],
        "fair82": [row["case_id"] for row in fair],
        "fair81": [row["case_id"] for row in included],
        "audit35": [row["case_id"] for row in included if parse_bool(row["audit35"])],
        "NEEDS_INFO": [row["case_id"] for row in included if row["routing_cohort"] == "NEEDS_INFO"],
        "REDIRECTED": [row["case_id"] for row in included if row["routing_cohort"] == "REDIRECTED"],
    }


def _optional_score(row, score):
    if score.endswith("_no_false_fix"):
        return not parse_bool(row[score.replace("_no_false_fix", "_fix_claim")])
    return parse_bool(row[score]) if row[score] else None


def _rate(values):
    available = [value for value in values if value is not None]
    successes = sum(available)
    n = len(available)
    lo, hi = wilson_interval(successes, n) if n else (None, None)
    return {
        "positive": successes, "n_scored": n, "n_missing": len(values) - n,
        "proportion": successes / n if n else None,
        "wilson95_lower": max(0.0, lo) if lo is not None else None,
        "wilson95_upper": min(1.0, hi) if hi is not None else None,
    }


def _rates(index, groups, protocol):
    scope_scores = {
        "BOT": CORE_SCORES, "HUMAN": CORE_SCORES,
        "fair81": CORE_SCORES + ("judge_no_false_fix", "lexical_no_false_fix"),
        "fair82": CORE_SCORES, "audit35": AUDIT_SCORES,
        "NEEDS_INFO": ("judge_asks_details", "lexical_asks_details"),
        "REDIRECTED": ("judge_says_duplicate", "lexical_says_duplicate"),
    }
    records = []
    for model in protocol["models"].values():
        for cohort, fields in scope_scores.items():
            dataset = "bot_test" if cohort in {"BOT", "HUMAN"} else "fair"
            arms = protocol["generated_arms"][dataset] + ["SWITCH"]
            if cohort == "fair82":
                arms = sorted(ORIGINAL_FAIR_ARMS)
            for arm in arms:
                rows = [index[model, case, arm] for case in groups[cohort]]
                for field in fields:
                    records.append({
                        "model": model, "cohort": cohort, "arm": arm, "score": field,
                        **_rate([_optional_score(row, field) for row in rows]),
                    })
    return records


def _pairs(index, cases, model, field, arm_a, arm_b):
    scores_a = [_optional_score(index[model, case, arm_a], field) for case in cases]
    scores_b = [_optional_score(index[model, case, arm_b], field) for case in cases]
    if any(value is None for value in scores_a + scores_b):
        raise ValueError(f"Missing paired score: {model}, {field}, {arm_a} vs {arm_b}")
    return list(zip(scores_a, scores_b))


def _paired_tests(index, groups, protocol):
    tests = []
    for family in protocol["paired_families"]:
        for name in family["models"]:
            model = protocol["models"][name]
            local = []
            for cohort, score, arm_a, arm_b in family["comparisons"]:
                pairs = _pairs(index, groups[cohort], model, score, arm_a, arm_b)
                a_only = sum(a and not b for a, b in pairs)
                b_only = sum(b and not a for a, b in pairs)
                local.append({
                    "family": family["name"], "model": model,
                    "role": family["gpt_role"] if name == "GPT" else "secondary",
                    "cohort": cohort, "score": score, "arm_a": arm_a, "arm_b": arm_b,
                    "pairs": len(pairs), "a_positive": sum(a for a, _ in pairs),
                    "b_positive": sum(b for _, b in pairs), "a_only": a_only, "b_only": b_only,
                    "p_exact_two_sided": exact_mcnemar_p(a_only, b_only), "p_holm": None,
                })
            if family["correction"] == "holm":
                adjusted = holm_adjust([row["p_exact_two_sided"] for row in local])
                for row, p in zip(local, adjusted):
                    row["p_holm"] = p
            tests.extend(local)
    return tests


def _paired_percentile_interval(pairs):
    """Enumerate the empirical bootstrap over differences -1, 0 and +1."""
    n = len(pairs)
    counts = Counter(int(a) - int(b) for a, b in pairs)
    negative, tied, positive = [counts[value] / n for value in (-1, 0, 1)]
    probability = Counter()
    for minus in range(n + 1):
        for plus in range(n - minus + 1):
            zero = n - minus - plus
            multiplicity = math.comb(n, minus) * math.comb(n - minus, plus)
            probability[plus - minus] += multiplicity * negative**minus * tied**zero * positive**plus
    cumulative = 0.0
    bounds = []
    for difference in sorted(probability):
        cumulative += probability[difference]
        if not bounds and cumulative >= 0.025:
            bounds.append(difference / n)
        if cumulative >= 0.975:
            bounds.append(difference / n)
            break
    return {
        "pairs": n,
        "difference": (counts[1] - counts[-1]) / n,
        "paired_percentile_95": bounds,
    }


def _agreement(left, right):
    pairs = list(zip(left, right))
    if len(left) != len(right) or not pairs or any(None in pair for pair in pairs):
        raise ValueError("Agreement requires complete paired labels")
    counts = Counter(pairs)
    agreement = counts[True, True] + counts[False, False]
    kappa = cohen_kappa(left, right)
    return {
        "n": len(pairs), "agree": agreement, "agreement": agreement / len(pairs),
        "cohen_kappa": None if math.isnan(kappa) else kappa,
        "both_positive": counts[True, True], "left_only": counts[True, False],
        "right_only": counts[False, True], "both_negative": counts[False, False],
    }


def _agreements(judgments, cases, human, index, protocol):
    original_probe = [
        row for row in judgments if cases[row["case_id"]]["dataset"] == "bot_test"
        and row["arm"] in ORIGINAL_BOT_ARMS
    ]
    original_shared = [
        row for row in judgments if cases[row["case_id"]]["dataset"] == "fair"
        and row["arm"] in ORIGINAL_FAIR_ARMS
    ]
    result = []
    for scope, rows in [
        ("original_bot_probe", original_probe),
        ("original_bot_and_shared_prompt", original_probe + original_shared),
    ]:
        for endpoint in ("declined", "fix_claim", "inactivity"):
            result.append({
                "scope": scope, "model": "both", "arm": "all_original", "endpoint": endpoint,
                "left": "judge", "right": "lexical",
                **_agreement(
                    [parse_bool(row[f"judge_{endpoint}"]) for row in rows],
                    [parse_bool(row[f"lexical_{endpoint}"]) for row in rows],
                ),
            })
    for model in protocol["models"].values():
        for arm in ("TAXONOMY-ONLY", "RAW+MEANING"):
            for group in ("BOT", "HUMAN", "all"):
                rows = [
                    row for row in judgments
                    if row["model"] == model and row["arm"] == arm
                    and cases[row["case_id"]]["dataset"] == "bot_test"
                    and (group == "all" or cases[row["case_id"]]["probe_group"] == group)
                ]
                result.append({
                    "scope": f"probe_{group}", "model": model, "arm": arm, "endpoint": "declined",
                    "left": "judge", "right": "lexical",
                    **_agreement(
                        [parse_bool(row["judge_declined"]) for row in rows],
                        [parse_bool(row["lexical_declined"]) for row in rows],
                    ),
                })
    labels = [parse_bool(row["human_states_outcome"]) for row in human]
    for source in ("judge", "lexical"):
        comparators = [
            _optional_score(index[row["model"], row["case_id"], row["arm"]], f"{source}_states_outcome")
            for row in human
        ]
        result.append({
            "scope": "selected_human_check", "model": protocol["models"]["GPT"],
            "arm": "RAW+TAXONOMY-ONLY pair", "endpoint": "states_outcome",
            "left": "human", "right": source, **_agreement(labels, comparators),
        })
    return result


def _fix_status(index, cases, protocol):
    rows = []
    for model in protocol["models"].values():
        for cohort in ("fair82", "fair81"):
            arms = sorted(ORIGINAL_FAIR_ARMS) if cohort == "fair82" else protocol["generated_arms"]["fair"] + ["SWITCH"]
            members = [
                case for case in cases if case["dataset"] == "fair"
                and (cohort == "fair82" or not case["analysis_exclusion"])
            ]
            for arm in arms:
                for source in ("judge", "lexical"):
                    for status, meaning in (
                        ("FIXED", "missed_fix"), ("NOT FIXED", "false_fix_claim"),
                        ("UNCERTAIN", "fix_claim_unadjudicated"),
                    ):
                        values = [
                            parse_bool(index[model, case["case_id"], arm][f"{source}_fix_claim"])
                            for case in members if case["tracker_supported_status"] == status
                        ]
                        rows.append({
                            "model": model, "arm": arm, "cohort": cohort, "source": source,
                            "tracker_supported_status": status, "interpretation": meaning,
                            **_rate([not value for value in values] if status == "FIXED" else values),
                        })
    return rows


def _prevalence(rows):
    result = []
    for row in rows:
        n = int(row["closed_issues"])
        v1 = 100 * int(row["nonresolved_v1_count"]) / n
        v2 = 100 * int(row["nonresolved_v2_count"]) / n
        delta = v1 - float(row["paper_table1_nonresolved_pct"])
        instances = int(row["rejection_label_instances"])
        known_adders = instances - int(row["rejection_label_adder_unknown"])
        bots = int(row["rejection_labels_added_by_bot"])
        narrow_n = int(row["script_v1_rejected_by_label"])
        labeled = int(row["issues_with_any_rejection_label"])
        result.append({
            **row,
            "nonresolved_v1_pct": v1, "nonresolved_v2_pct": v2,
            "v2_minus_v1_pp": v2 - v1, "v1_minus_historical_pp": delta,
            "within_0_5_pp": abs(delta) <= 0.5,
            "bot_rejection_label_pct_all": 100 * bots / instances if instances else None,
            "bot_rejection_label_pct_known_adders": 100 * bots / known_adders if known_adders else None,
            "bot_rejection_label_pct_narrow_v1": (
                100 * int(row["script_v1_reject_label_added_by_bot"]) / narrow_n if narrow_n else None
            ),
            "rejection_labeled_bot_closed_no_fix_pct": (
                100 * int(row["rejection_labeled_issues_closed_by_bot_no_fix"]) / labeled if labeled else None
            ),
        })
    return result


def analyze_followups(cases, judgments, human, prevalence, protocol):
    by_case = {row["case_id"]: row for row in cases}
    groups = _group_cases(cases)
    if len(by_case) != len(cases) or {key: len(value) for key, value in groups.items()} != protocol["cohorts"]:
        raise ValueError("Case IDs or frozen follow-up cohort counts differ")
    index = {(row["model"], row["case_id"], row["arm"]): row for row in judgments}
    expected = {
        (model, case["case_id"], arm) for model in protocol["models"].values()
        for case in cases for arm in protocol["generated_arms"][case["dataset"]]
    }
    if len(index) != len(judgments) or set(index) != expected:
        raise ValueError("Follow-up judgment grid has missing or duplicate responses")
    for case in cases:
        selected = switch_arm(case)
        if (selected == "TAXONOMY-ONLY") != parse_bool(case["switch"]):
            raise ValueError(f"Switch provenance mismatch for {case['case_id']}")
        for model in protocol["models"].values():
            index[model, case["case_id"], "SWITCH"] = index[model, case["case_id"], selected]
    gpt = protocol["models"]["GPT"]
    audit_scores = _pairs(index, groups["audit35"], gpt, "judge_states_outcome", "RAW", "TAXONOMY-ONLY")
    discordant_ids = {case for case, (raw, tax) in zip(groups["audit35"], audit_scores) if raw != tax}
    expected_human = {(gpt, case, arm) for case in discordant_ids for arm in ("RAW", "TAXONOMY-ONLY")}
    actual_human = {(row["model"], row["case_id"], row["arm"]) for row in human}
    if len(human) != len(expected_human) or actual_human != expected_human:
        raise ValueError("Human check must contain both responses for each selected judge-discordant pair")
    human_by_case = {(row["case_id"], row["arm"]): parse_bool(row["human_states_outcome"]) for row in human}
    human_pairs = [(human_by_case[case, "RAW"], human_by_case[case, "TAXONOMY-ONLY"]) for case in sorted(discordant_ids)]
    intervals = {}
    for model in protocol["models"].values():
        intervals[model] = _paired_percentile_interval(
            _pairs(index, groups["audit35"], model, "judge_states_outcome", "RAW+MEANING", "RAW")
        )
    combined_pairs = _pairs(index, groups["audit35"], gpt, "judge_states_outcome", "RAW+MEANING", "RAW")
    summary = {
        "generation_rows": len(judgments),
        "case_counts": {name: len(members) for name, members in groups.items()},
        "original_bot_responses": sum(row["arm"] in ORIGINAL_BOT_ARMS and by_case[row["case_id"]]["dataset"] == "bot_test" for row in judgments),
        "original_shared_prompt_responses": sum(row["arm"] in ORIGINAL_FAIR_ARMS and by_case[row["case_id"]]["dataset"] == "fair" for row in judgments),
        "taxonomy_only_responses": sum(row["arm"] == "TAXONOMY-ONLY" for row in judgments),
        "raw_plus_meaning_responses": sum(row["arm"] == "RAW+MEANING" for row in judgments),
        "switch_cases": dict(Counter(row["dataset"] for row in cases if parse_bool(row["switch"]))),
        "switch_audit_cases": sum(parse_bool(by_case[case]["switch"]) for case in groups["audit35"]),
        "analysis_exclusions": dict(Counter(row["analysis_exclusion"] for row in cases if row["analysis_exclusion"])),
        "combined_outcome_differences": intervals,
        "human_check": {
            "selected_pairs": len(human_pairs), "human_labels": len(human),
            "raw_only_correct": sum(raw and not tax for raw, tax in human_pairs),
            "taxonomy_only_correct": sum(tax and not raw for raw, tax in human_pairs),
            "tied": sum(raw == tax for raw, tax in human_pairs),
        },
        "combined_check_requested_labels": 2 * sum(a != b for a, b in combined_pairs),
        "combined_check_completed_labels": 0,
    }
    return {
        "summary": summary, "rates": _rates(index, groups, protocol),
        "paired_tests": _paired_tests(index, groups, protocol),
        "agreement": _agreements(judgments, by_case, human, index, protocol),
        "fix_by_status": _fix_status(index, cases, protocol), "prevalence": _prevalence(prevalence),
    }
