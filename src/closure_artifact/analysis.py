from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .followups import analyze_followups
from .metrics import cohen_kappa, exact_mcnemar_p, macro_f1, mde_80, parse_bool, wilson_interval
from .retrieval import analyze_retrieval, analyze_synthetic_bge
from .taxonomy import LEVEL1


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    fields = list(materialized[0]) if materialized else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def analyze_human_status(root: Path) -> dict[str, Any]:
    rows = read_csv(root / "data" / "derived" / "human_status_72.csv")
    if len(rows) != 72:
        raise AssertionError(f"Expected 72 human-status rows, found {len(rows)}")

    normalized = [
        {
            **row,
            "human_status_correct": parse_bool(row["human_status_correct"]),
            "llm_judge_status_correct": parse_bool(row["llm_judge_status_correct"]),
        }
        for row in rows
    ]
    systems = ("closure_aware", "binary_state")
    by_system: dict[str, dict[str, Any]] = {}
    for system in systems:
        subset = [row for row in normalized if row["system"] == system]
        correct = sum(row["human_status_correct"] for row in subset)
        by_system[system] = {"correct": correct, "n": len(subset), "rate": correct / len(subset)}

    pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in normalized:
        pairs[row["case_id"]][row["system"]] = row
    if len(pairs) != 36 or any(set(pair) != set(systems) for pair in pairs.values()):
        raise AssertionError("Expected 36 complete closure-aware/binary-state pairs")

    outcomes = Counter(both_correct=0, structured_only=0, binary_only=0, both_incorrect=0)
    for pair in pairs.values():
        structured = pair["closure_aware"]["human_status_correct"]
        binary = pair["binary_state"]["human_status_correct"]
        key = (
            "both_correct" if structured and binary
            else "structured_only" if structured
            else "binary_only" if binary
            else "both_incorrect"
        )
        outcomes[key] += 1

    class_rows: list[dict[str, Any]] = []
    for level1 in ("ABANDONED", "REDIRECTED", "REJECTED"):
        result: dict[str, Any] = {"l1_class": level1}
        for system in systems:
            subset = [
                row for row in normalized
                if row["l1_class"] == level1 and row["system"] == system
            ]
            result[f"{system}_correct"] = sum(row["human_status_correct"] for row in subset)
            result[f"{system}_n"] = len(subset)
        class_rows.append(result)

    human = [row["human_status_correct"] for row in normalized]
    automated = [row["llm_judge_status_correct"] for row in normalized]
    agreement = sum(a == b for a, b in zip(human, automated))
    return {
        "evidence_status": "REPRODUCED_FROM_TEXT_FREE_FROZEN_DECISIONS",
        "n_pairs": len(pairs),
        "n_responses": len(normalized),
        "by_system": by_system,
        "paired_outcomes": dict(outcomes),
        "exact_two_sided_mcnemar_p": exact_mcnemar_p(
            outcomes["structured_only"], outcomes["binary_only"]
        ),
        "observed_paired_difference": (
            outcomes["structured_only"] - outcomes["binary_only"]
        ) / len(pairs),
        "by_closure_class": class_rows,
        "human_llm_agreement": {
            "agreement_count": agreement,
            "n": len(normalized),
            "rate": agreement / len(normalized),
            "cohen_kappa": cohen_kappa(human, automated),
        },
    }


def analyze_taxonomy(root: Path) -> dict[str, Any]:
    rows = read_csv(root / "data" / "derived" / "taxonomy_predictions_120.csv")
    if len(rows) != 120:
        raise AssertionError(f"Expected 120 taxonomy rows, found {len(rows)}")
    actual = [row["human_l1"].strip().upper() for row in rows]
    predicted = [row["rule_l1"].strip().upper() for row in rows]
    correct = sum(a == p for a, p in zip(actual, predicted))
    low, high = wilson_interval(correct, len(rows))
    confusion = {truth: {prediction: 0 for prediction in LEVEL1} for truth in LEVEL1}
    for truth, prediction in zip(actual, predicted):
        confusion[truth][prediction] += 1
    return {
        "evidence_status": "REPRODUCED_FROM_TEXT_FREE_FROZEN_LABELS",
        "correct": correct,
        "n": len(rows),
        "accuracy": correct / len(rows),
        "wilson_95": [low, high],
        "macro_f1": macro_f1(actual, predicted, LEVEL1),
        "cohen_kappa": cohen_kappa(actual, predicted),
        "human_class_counts": dict(Counter(actual)),
        "confusion_matrix": confusion,
        "mismatch_case_ids": [
            row["case_id"] for row, truth, prediction in zip(rows, actual, predicted)
            if truth != prediction
        ],
    }


def _optional_bool(value: object) -> bool | None:
    return None if value is None or str(value).strip() == "" else parse_bool(value)


def analyze_generation(root: Path) -> dict[str, Any]:
    rows = read_csv(root / "data" / "derived" / "generation_judgments_246.csv")
    if len(rows) != 246:
        raise AssertionError(f"Expected 246 generation rows, found {len(rows)}")
    systems = ("closure_aware", "raw_metadata", "binary_state")
    nonresolved = {"REJECTED", "ABANDONED", "REDIRECTED"}
    system_rows: list[dict[str, Any]] = []
    for system in systems:
        subset = [row for row in rows if row["system"] == system]
        faithfulness = [float(row["judge_faithfulness"]) for row in subset]
        nonresolved_rows = [row for row in subset if row["l1_class"] in nonresolved]
        system_rows.append(
            {
                "system": system,
                "n": len(subset),
                "judge_status_correct": sum(parse_bool(row["judge_status_correct"]) for row in subset),
                "judge_hallucination": sum(parse_bool(row["judge_hallucination"]) for row in subset),
                "mean_judge_faithfulness": sum(faithfulness) / len(faithfulness),
                "known_positive_hit_at_1": sum(parse_bool(row["known_positive_hit_at_1"]) for row in subset),
                "known_positive_gated_strict_success": sum(
                    value is True
                    for value in (_optional_bool(row["known_positive_gated_strict_success"]) for row in subset)
                ),
                "nonresolved_n": len(nonresolved_rows),
                "nonresolved_judge_status_correct": sum(
                    parse_bool(row["judge_status_correct"]) for row in nonresolved_rows
                ),
                "nonresolved_judge_hallucination": sum(
                    parse_bool(row["judge_hallucination"]) for row in nonresolved_rows
                ),
            }
        )

    case_classes: dict[str, str] = {}
    for row in rows:
        case_classes[row["case_id"]] = row["l1_class"]
    if len(case_classes) != 82:
        raise AssertionError(f"Expected 82 unique generation cases, found {len(case_classes)}")

    action_rows = read_csv(root / "data" / "derived" / "action_routing_46.csv")
    groups: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in action_rows:
        groups[(row["action_dimension"], row["system"])].append(
            parse_bool(row["action_realized"])
        )
    action_summary = [
        {
            "action_dimension": dimension,
            "system": system,
            "realized": sum(values),
            "n": len(values),
            "rate": sum(values) / len(values),
        }
        for (dimension, system), values in sorted(groups.items())
    ]
    return {
        "evidence_status": "REPRODUCED_FROM_TEXT_FREE_FROZEN_DECISIONS",
        "n_cases": len(case_classes),
        "n_system_rows": len(rows),
        "case_class_counts": dict(Counter(case_classes.values())),
        "system_metrics": system_rows,
        "action_routing": action_summary,
        "interpretation": "Automated-judge metrics are secondary; the blinded human endpoint is primary.",
    }


def analyze_training(root: Path) -> dict[str, Any]:
    rows = read_csv(root / "data" / "derived" / "splade_checkpoint_audit_5seeds.csv")
    seeds = sorted(int(row["seed"]) for row in rows)
    return {
        "evidence_status": "REPRODUCED_CHECKPOINT_MANIFEST_AUDIT",
        "seeds": seeds,
        "n_checkpoints": len(rows),
        "checkpoint_audit_passed": sum(parse_bool(row["pass"]) for row in rows),
        "all_dataset_hashes_equal": (
            len({row["dataset_triplet_sha256"] for row in rows}) == 1
            and len({row["dataset_pairs_sha256"] for row in rows}) == 1
        ),
        "note": "Model weights and full-corpus per-query outputs are outside this public snapshot.",
    }


def build_mde_rows() -> list[dict[str, Any]]:
    specifications = [
        ("Human closure-aware vs binary status", 36, 33, 0, "PRIMARY_HUMAN_ENDPOINT"),
        ("RRF vs BGE-ZS known-positive Hit@1", 82, 10, 2, "PRIMARY_RQ2_BINARY_ENDPOINT"),
    ]
    rows: list[dict[str, Any]] = []
    for comparison, n, a_only, b_only, status in specifications:
        discordant = a_only + b_only
        rows.append(
            {
                "comparison": comparison,
                "n": n,
                "a_only": a_only,
                "b_only": b_only,
                "status": status,
                "discordant_pairs": discordant,
                "discordance_rate": discordant / n,
                "observed_abs_paired_difference": abs(a_only - b_only) / n,
                "mde_80pct_power_abs_paired_difference": mde_80(n, discordant),
                "alpha_two_sided": 0.05,
                "target_power": 0.80,
            }
        )
    return rows


def reproduce_all(root: Path, output: Path | None = None) -> dict[str, Any]:
    output = output or root / "results" / "generated"
    human = analyze_human_status(root)
    taxonomy = analyze_taxonomy(root)
    generation = analyze_generation(root)
    training = analyze_training(root)
    mde_rows = build_mde_rows()
    derived = root / "data" / "derived"
    followup = analyze_followups(
        read_csv(derived / "followup_cases_162.csv"),
        read_csv(derived / "followup_judgments_1780.csv"),
        read_csv(derived / "followup_human_check_24.csv"),
        read_csv(derived / "provenance_prevalence_7.csv"),
        json.loads((root / "protocols" / "followup_analysis.json").read_text(encoding="utf-8")),
    )
    retrieval = analyze_retrieval(
        read_csv(derived / "retrieval_query_scores_82.csv"),
        read_csv(derived / "retrieval_thresholds_12.csv"),
    )
    synthetic = analyze_synthetic_bge(read_csv(derived / "synthetic_bge_ranks_794.csv"))
    summary = {
        "snapshot_version": "0.1.0",
        "public_data_boundary": "text-free derived evidence",
        "human_primary": human,
        "taxonomy_validation": taxonomy,
        "generation_descriptive": generation,
        "training_manifest": training,
        "paired_binary_sensitivity": mde_rows,
        "generation_followup": followup["summary"],
        "external_retrieval": retrieval["summary"],
        "synthetic_bge_development": [row for row in synthetic if row["project"] == "all"],
    }
    write_json(output / "human_status_summary.json", human)
    write_json(output / "taxonomy_validation_summary.json", taxonomy)
    write_csv(output / "generation_system_metrics.csv", generation["system_metrics"])
    write_csv(output / "action_routing_summary.csv", generation["action_routing"])
    write_json(output / "generation_summary.json", generation)
    write_json(output / "training_manifest_summary.json", training)
    write_csv(output / "paired_binary_mde_sensitivity.csv", mde_rows)
    for name in ("rates", "paired_tests", "agreement", "fix_by_status", "prevalence"):
        write_csv(output / f"followup_{name}.csv", followup[name])
    for name in ("rates", "paired_tests", "selective"):
        write_csv(output / f"retrieval_{name}.csv", retrieval[name])
    write_csv(output / "synthetic_bge_rates.csv", synthetic)
    write_json(output / "reproduction_summary.json", summary)
    return summary
