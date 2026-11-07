from __future__ import annotations

import math
from collections import Counter
from statistics import median

from .metrics import exact_mcnemar_p, holm_adjust, parse_bool

METHODS = ("bm25", "bge_zs", "rrf")
PRIMARY_SIGNAL = "corroboration_rr"


def _signed_rank(differences):
    """Wilcox zero removal, tie-corrected normal approximation, no continuity correction."""
    nonzero = [difference for difference in differences if difference]
    if not nonzero:
        return 0.0, 1.0
    ties = Counter(abs(difference) for difference in nonzero)
    ranks = {}
    previous = 0
    for magnitude, count in sorted(ties.items()):
        ranks[magnitude] = previous + (count + 1) / 2
        previous += count
    n = len(nonzero)
    plus = sum(ranks[abs(difference)] for difference in nonzero if difference > 0)
    statistic = min(plus, n * (n + 1) / 2 - plus)
    tie_correction = sum(count**3 - count for count in ties.values())
    variance = (n * (n + 1) * (2 * n + 1) - tie_correction / 2) / 24
    z = (plus - n * (n + 1) / 4) / math.sqrt(variance)
    return statistic, math.erfc(abs(z) / math.sqrt(2))


def _fisher_enrichment(n, positives, accepted, accepted_positives):
    denominator = math.comb(n, accepted)
    high = min(accepted, positives)
    return sum(
        math.comb(positives, hits) * math.comb(n - positives, accepted - hits)
        for hits in range(accepted_positives, high + 1)
    ) / denominator


def _method_rates(queries, methods=METHODS):
    result = []
    projects = sorted({row["project"] for row in queries})
    for project in ("all", *projects):
        members = [row for row in queries if project == "all" or row["project"] == project]
        for method in methods:
            ranks = [int(row[f"{method}_rank"]) for row in members]
            result.append({
                "project": project, "method": method, "n": len(ranks),
                "mrr": math.fsum(1 / rank for rank in ranks) / len(ranks),
                "hit_at_1_count": sum(rank == 1 for rank in ranks),
                "hit_at_10_count": sum(rank <= 10 for rank in ranks),
                "median_rank": median(ranks),
            })
    return result


def _paired_retrieval(queries):
    rrf_ranks = [int(row["rrf_rank"]) for row in queries]
    bge_ranks = [int(row["bge_zs_rank"]) for row in queries]
    contributions = {
        "reciprocal_rank": ([1 / rank for rank in rrf_ranks], [1 / rank for rank in bge_ranks]),
        "hit_at_1": ([rank == 1 for rank in rrf_ranks], [rank == 1 for rank in bge_ranks]),
        "hit_at_10": ([rank <= 10 for rank in rrf_ranks], [rank <= 10 for rank in bge_ranks]),
    }
    tests = []
    for metric, (rrf, bge) in contributions.items():
        differences = [a - b for a, b in zip(rrf, bge)]
        statistic, p = _signed_rank(differences)
        rrf_only = sum(difference > 0 for difference in differences)
        bge_only = sum(difference < 0 for difference in differences)
        binary = metric.startswith("hit_")
        tests.append({
            "comparison": "rrf_vs_bge_zs", "metric": metric, "n": len(queries),
            "rrf_mean": math.fsum(rrf) / len(queries),
            "bge_mean": math.fsum(bge) / len(queries),
            "mean_difference": math.fsum(differences) / len(queries),
            "rrf_higher": rrf_only, "bge_higher": bge_only,
            "ties": len(queries) - rrf_only - bge_only,
            "wilcoxon_statistic": statistic, "wilcoxon_p": p,
            "wilcoxon_p_holm": None,
            "mcnemar_p": exact_mcnemar_p(rrf_only, bge_only) if binary else None,
            "mcnemar_p_holm": None,
        })
    for test, p in zip(tests, holm_adjust([row["wilcoxon_p"] for row in tests])):
        test["wilcoxon_p_holm"] = p
    binary = [row for row in tests if row["mcnemar_p"] is not None]
    for test, p in zip(binary, holm_adjust([row["mcnemar_p"] for row in binary])):
        test["mcnemar_p_holm"] = p
    return tests


def _selective(queries, thresholds):
    total_positives = sum(int(row["rrf_rank"]) == 1 for row in queries)
    total_strict = sum(parse_bool(row["strict_success"]) for row in queries)
    result = []
    for row in thresholds:
        signal = row["signal"]
        threshold = float(row["threshold_inclusive"])
        accepted = [query for query in queries if float(query[signal]) >= threshold]
        n_accepted = len(accepted)
        positives = sum(int(query["rrf_rank"]) == 1 for query in accepted)
        primary = signal == PRIMARY_SIGNAL
        strict = sum(parse_bool(query["strict_success"]) for query in accepted) if primary else None
        result.append({
            "signal": signal, "target_coverage": float(row["target_coverage"]),
            "threshold_inclusive": threshold, "accepted": n_accepted,
            "abstained": len(queries) - n_accepted, "realized_coverage": n_accepted / len(queries),
            "confirmed_hits_accepted": positives,
            "confirmed_hits_abstained": total_positives - positives,
            "confirmed_hit_rate_accepted": positives / n_accepted,
            "confirmed_hits_retained": positives / total_positives,
            "strict_success_accepted": strict,
            "strict_success_abstained": total_strict - strict if primary else None,
            "strict_success_rate_accepted": strict / n_accepted if primary else None,
            "strict_success_retained": strict / total_strict if primary else None,
            "enrichment_fisher_p": (
                _fisher_enrichment(len(queries), total_positives, n_accepted, positives)
                if primary and n_accepted < len(queries) else None
            ),
            "enrichment_fisher_p_holm": None,
        })
    tests = [row for row in result if row["enrichment_fisher_p"] is not None]
    for test, p in zip(tests, holm_adjust([row["enrichment_fisher_p"] for row in tests])):
        test["enrichment_fisher_p_holm"] = p
    return result


def analyze_retrieval(queries, thresholds):
    if len(queries) != 82 or len({row["query_id"] for row in queries}) != 82:
        raise ValueError("Expected the complete set of 82 opaque retrieval queries")
    if Counter(row["project"] for row in queries) != {"Firefox": 28, "VLC": 21, "Nextcloud": 33}:
        raise ValueError("Unexpected project composition in the retrieval evidence")
    if any(int(row[f"{method}_rank"]) < 1 for method in METHODS for row in queries):
        raise ValueError("Known-positive ranks must be positive")
    if any(parse_bool(row["strict_success"]) and int(row["rrf_rank"]) != 1 for row in queries):
        raise ValueError("Strict successes must pass the known-positive Hit@1 gate")
    expected_thresholds = {
        (signal, coverage) for signal in (PRIMARY_SIGNAL, "rrf_relative_margin", "mean_top10_jaccard")
        for coverage in (1.0, 0.75, 0.5, 0.25)
    }
    if len(thresholds) != 12 or {(row["signal"], float(row["target_coverage"])) for row in thresholds} != expected_thresholds:
        raise ValueError("Incomplete or unexpected frozen selective thresholds")
    rates = _method_rates(queries)
    tests = _paired_retrieval(queries)
    selective = _selective(queries, thresholds)
    return {
        "summary": {
            "evidence_status": "REPRODUCED_FROM_OPAQUE_KNOWN_POSITIVE_RANKS",
            "queries": len(queries),
            "methods": [row for row in rates if row["project"] == "all"],
            "rank_movement_rrf_vs_bge_zs": {
                "improved": tests[0]["rrf_higher"], "worsened": tests[0]["bge_higher"],
                "unchanged": tests[0]["ties"],
                "exact_sign_test_p": exact_mcnemar_p(tests[0]["rrf_higher"], tests[0]["bge_higher"]),
            },
            "primary_selective_curve": [row for row in selective if row["signal"] == PRIMARY_SIGNAL],
        },
        "rates": rates, "paired_tests": tests, "selective": selective,
    }


def analyze_synthetic_bge(queries):
    methods = ("bge_zs", "bge_ft")
    if len(queries) != 794 or len({row["query_id"] for row in queries}) != 794:
        raise ValueError("Expected 794 paired synthetic-development queries")
    if any(int(row[f"{method}_rank"]) < 1 for method in methods for row in queries):
        raise ValueError("Synthetic-development ranks must be positive")
    return _method_rates(queries, methods)
