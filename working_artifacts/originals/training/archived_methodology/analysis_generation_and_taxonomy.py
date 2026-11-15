"""Reproduce generation and closure-taxonomy statistics used in the manuscript."""

from __future__ import annotations

from itertools import permutations
from math import comb
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, cohen_kappa_score, f1_score


ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "library_inputs"
OUTPUTS = ROOT / "analysis_outputs"
OUTPUTS.mkdir(exist_ok=True)

NON_RESOLVED = {
    "WONTFIX",
    "STALE",
    "NEEDS_INFO",
    "UPSTREAM",
    "OTHER_CLOSED",
    "DUPLICATE",
}


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054):
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    half_width = (
        z
        * np.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return center - half_width, center + half_width


def exact_mcnemar(first: pd.Series, second: pd.Series):
    first = first.astype(bool)
    second = second.astype(bool)
    first_only = int((first & ~second).sum())
    second_only = int((~first & second).sum())
    discordant = first_only + second_only
    if discordant == 0:
        p_value = 1.0
    else:
        smaller = min(first_only, second_only)
        one_tail = sum(comb(discordant, index) for index in range(smaller + 1))
        p_value = min(1.0, 2.0 * one_tail / (2**discordant))
    return first_only, second_only, discordant, p_value


def holm_adjust(p_values):
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running_max = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * p_values[index])
        running_max = max(running_max, candidate)
        adjusted[index] = running_max
    return adjusted


def normalized_labels(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def closure_signals(row: pd.Series):
    labels = normalized_labels(row.get("labels"))
    state_reason = (
        "" if pd.isna(row.get("state_reason")) else str(row["state_reason"]).lower()
    )
    tokens = set(labels.split())
    duplicate = state_reason == "duplicate" or "duplicate" in tokens
    explicit_rejection = any(
        phrase in f" {labels} "
        for phrase in (
            " wontfix ",
            " wont fix ",
            " by design ",
            " not a bug ",
            " invalid ",
        )
    )
    abandonment = any(
        phrase in f" {labels} "
        for phrase in (
            " stale ",
            " needs author reply ",
            " needs info ",
            " insufficient information ",
            " can t reproduce ",
            " cannot reproduce ",
            " no response ",
            " upstream issue ",
        )
    )
    fallback_rejection = state_reason in {"not_planned", "not planned"}
    return {
        "D": duplicate,
        "E": explicit_rejection,
        "A": abandonment,
        "F": fallback_rejection,
        "R": True,
    }


def classify_closure(row: pd.Series, order: str) -> str:
    output = {
        "D": "REDIRECTED",
        "E": "REJECTED",
        "A": "ABANDONED",
        "F": "REJECTED",
        "R": "RESOLVED",
    }
    signals = closure_signals(row)
    for key in order:
        if signals[key]:
            return output[key]
    raise AssertionError("Every policy must end with the RESOLVED fallback.")


def generation_statistics():
    frame = pd.read_csv(INPUTS / "closure_reason_results (1).csv")
    headline = frame[
        frame["correct_retrieval"].astype(bool)
        & frame["true_closure_reason"].isin(NON_RESOLVED)
    ].copy()
    if len(headline) != 42:
        raise AssertionError(f"Expected 42 headline cases, found {len(headline)}")

    status_columns = {
        "Closure-aware (common paired run)": "status_ca",
        "Binary-state baseline": "status_sa",
        "Vanilla RAG": "status_rag",
        "Zero-shot LLM": "status_zs",
    }
    status_rows = []
    for method, column in status_columns.items():
        successes = int(headline[column].astype(bool).sum())
        low, high = wilson_interval(successes, len(headline))
        status_rows.append(
            {
                "method": method,
                "successes": successes,
                "n": len(headline),
                "percent": 100.0 * successes / len(headline),
                "wilson_low_percent": 100.0 * low,
                "wilson_high_percent": 100.0 * high,
            }
        )

    human = pd.read_excel(
        INPUTS / "response_annotation_HEADLINE_FORMATTED (1).xlsx",
        sheet_name="Response Annotation",
    )
    human_successes = int(
        human["human_status_correct"].astype(str).str.upper().eq("YES").sum()
    )
    low, high = wilson_interval(human_successes, len(human))
    status_rows.insert(
        0,
        {
            "method": "Closure-aware (refined, manual audit)",
            "successes": human_successes,
            "n": len(human),
            "percent": 100.0 * human_successes / len(human),
            "wilson_low_percent": 100.0 * low,
            "wilson_high_percent": 100.0 * high,
        },
    )
    status = pd.DataFrame(status_rows)

    tests = []
    for method, column in list(status_columns.items())[1:]:
        first_only, second_only, discordant, p_value = exact_mcnemar(
            headline["status_ca"], headline[column]
        )
        tests.append(
            {
                "comparison": f"Closure-aware vs {method}",
                "closure_aware_only_correct": first_only,
                "baseline_only_correct": second_only,
                "discordant_pairs": discordant,
                "exact_p": p_value,
            }
        )
    mcnemar = pd.DataFrame(tests)
    mcnemar["holm_adjusted_p"] = holm_adjust(mcnemar["exact_p"].to_numpy())

    level1 = {
        "OPEN": "OPEN",
        "FIXED": "RESOLVED",
        "WONTFIX": "REJECTED",
        "STALE": "ABANDONED",
        "NEEDS_INFO": "ABANDONED",
        "UPSTREAM": "ABANDONED",
        "OTHER_CLOSED": "ABANDONED",
        "DUPLICATE": "REDIRECTED",
    }
    frame["level1"] = frame["true_closure_reason"].map(level1)
    hallucination_columns = {
        "Closure-aware": "hall_ca",
        "Binary-state": "hall_sa",
        "Vanilla RAG": "hall_rag",
        "Zero-shot LLM": "hall_zs",
    }
    hallucination_rows = []
    for closure_class in [
        "OPEN",
        "RESOLVED",
        "REJECTED",
        "ABANDONED",
        "REDIRECTED",
    ]:
        subset = frame[frame["level1"] == closure_class]
        for method, column in hallucination_columns.items():
            count = int(subset[column].astype(bool).sum())
            low, high = wilson_interval(count, len(subset))
            hallucination_rows.append(
                {
                    "closure_class": closure_class,
                    "n": len(subset),
                    "method": method,
                    "hallucinations": count,
                    "percent": 100.0 * count / len(subset),
                    "wilson_low_percent": 100.0 * low,
                    "wilson_high_percent": 100.0 * high,
                }
            )
    hallucination = pd.DataFrame(hallucination_rows)

    # RQ4 headline inference: paired hallucination outcomes within the two
    # adequately represented non-resolved classes.  REDIRECTED has only ten
    # cases and remains descriptive.
    hallucination_tests = []
    for closure_class in ("REJECTED", "ABANDONED"):
        subset = frame[frame["level1"] == closure_class]
        closure_only, binary_only, discordant, p_value = exact_mcnemar(
            subset["hall_ca"], subset["hall_sa"]
        )
        hallucination_tests.append(
            {
                "closure_class": closure_class,
                "n": len(subset),
                "closure_aware_only_hallucinated": closure_only,
                "binary_state_only_hallucinated": binary_only,
                "discordant_pairs": discordant,
                "exact_p": p_value,
            }
        )
    hallucination_mcnemar = pd.DataFrame(hallucination_tests)
    hallucination_mcnemar["holm_adjusted_p"] = holm_adjust(
        hallucination_mcnemar["exact_p"].to_numpy()
    )

    status.to_csv(OUTPUTS / "headline_status_wilson.csv", index=False)
    mcnemar.to_csv(OUTPUTS / "headline_status_mcnemar.csv", index=False)
    hallucination.to_csv(OUTPUTS / "hallucination_by_class_wilson.csv", index=False)
    hallucination_mcnemar.to_csv(
        OUTPUTS / "hallucination_mcnemar_by_class.csv", index=False
    )
    return status, mcnemar, hallucination, hallucination_mcnemar


def taxonomy_sensitivity():
    frame = pd.read_excel(
        INPUTS / "taxonomy_annotation_pack_FORMATTED (1).xlsx",
        sheet_name="Annotation",
    )
    policies = {
        "Reported evidence-first": "DEAFR",
        "Abandonment before explicit rejection": "DAEFR",
        "Duplicate after abandonment": "EADFR",
        "state_reason before abandonment": "DEFAR",
    }
    reference = frame.apply(
        lambda row: classify_closure(row, policies["Reported evidence-first"]),
        axis=1,
    )
    rows = []
    for name, order in policies.items():
        predictions = frame.apply(
            lambda row: classify_closure(row, order),
            axis=1,
        )
        rows.append(
            {
                "policy": name,
                "order": order,
                "accuracy": accuracy_score(frame["human_l1"], predictions),
                "macro_f1": f1_score(
                    frame["human_l1"], predictions, average="macro"
                ),
                "cohen_kappa": cohen_kappa_score(
                    frame["human_l1"], predictions
                ),
                "changed_vs_reported": int((predictions != reference).sum()),
                "n": len(frame),
            }
        )

    exhaustive_rows = []
    for permutation in permutations("DEAF"):
        order = "".join(permutation) + "R"
        predictions = frame.apply(
            lambda row: classify_closure(row, order),
            axis=1,
        )
        exhaustive_rows.append(
            {
                "order": order,
                "accuracy": accuracy_score(frame["human_l1"], predictions),
                "macro_f1": f1_score(
                    frame["human_l1"], predictions, average="macro"
                ),
                "changed_vs_reported": int((predictions != reference).sum()),
            }
        )

    sensitivity = pd.DataFrame(rows)
    exhaustive = pd.DataFrame(exhaustive_rows).sort_values(
        ["accuracy", "macro_f1", "order"],
        ascending=[False, False, True],
    )
    sensitivity.to_csv(OUTPUTS / "taxonomy_priority_sensitivity.csv", index=False)
    exhaustive.to_csv(
        OUTPUTS / "taxonomy_priority_all_24_orders.csv",
        index=False,
    )
    return sensitivity, exhaustive


if __name__ == "__main__":
    (
        status_table,
        mcnemar_table,
        hallucination_table,
        hallucination_mcnemar_table,
    ) = generation_statistics()
    sensitivity_table, exhaustive_table = taxonomy_sensitivity()
    print("\nHEADLINE STATUS\n", status_table.to_string(index=False))
    print("\nPAIRED MCNEMAR\n", mcnemar_table.to_string(index=False))
    print(
        "\nHALLUCINATION BY CLASS\n",
        hallucination_table.to_string(index=False),
    )
    print(
        "\nPAIRED HALLUCINATION MCNEMAR\n",
        hallucination_mcnemar_table.to_string(index=False),
    )
    print("\nPRIORITY SENSITIVITY\n", sensitivity_table.to_string(index=False))
    print(
        "\nALL-ORDER ACCURACY RANGE:",
        exhaustive_table["accuracy"].min(),
        "to",
        exhaustive_table["accuracy"].max(),
    )
