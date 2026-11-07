from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence


def parse_bool(value: object, field: str = "value") -> bool:
    if isinstance(value, bool):
        return value
    text = "" if value is None else str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Cannot parse {field}={value!r} as boolean")


def exact_mcnemar_p(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar p-value using the conditional binomial test."""
    discordant = int(a_only) + int(b_only)
    if discordant == 0:
        return 1.0
    tail = min(int(a_only), int(b_only))
    lower = sum(math.comb(discordant, i) for i in range(tail + 1)) / (2**discordant)
    return min(1.0, 2.0 * lower)


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Adjust a fixed family of p-values and return them in the input order."""
    adjusted = [0.0] * len(p_values)
    previous = 0.0
    for rank, index in enumerate(sorted(range(len(p_values)), key=p_values.__getitem__)):
        previous = max(previous, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = previous
    return adjusted


def cohen_kappa(actual: Sequence[object], predicted: Sequence[object]) -> float:
    if len(actual) != len(predicted):
        raise ValueError("Kappa inputs must have equal length")
    if not actual:
        return float("nan")
    n = len(actual)
    observed = sum(a == b for a, b in zip(actual, predicted)) / n
    ac = Counter(actual)
    pc = Counter(predicted)
    expected = sum((ac[label] / n) * (pc[label] / n) for label in set(ac) | set(pc))
    if abs(1.0 - expected) < 1e-15:
        return float("nan")
    return (observed - expected) / (1.0 - expected)


def macro_f1(
    actual: Sequence[str], predicted: Sequence[str], labels: Iterable[str] | None = None
) -> float:
    if len(actual) != len(predicted):
        raise ValueError("F1 inputs must have equal length")
    selected = list(labels) if labels is not None else sorted(set(actual) | set(predicted))
    scores: list[float] = []
    for label in selected:
        tp = sum(a == label and p == label for a, p in zip(actual, predicted))
        fp = sum(a != label and p == label for a, p in zip(actual, predicted))
        fn = sum(a == label and p != label for a, p in zip(actual, predicted))
        denominator = 2 * tp + fp + fn
        scores.append((2 * tp / denominator) if denominator else 0.0)
    return sum(scores) / len(scores) if scores else float("nan")


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = successes / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return center - margin, center + margin


def _binom_pmf(n: int, k: int, p: float) -> float:
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    return math.comb(n, k) * (p**k) * ((1 - p) ** (n - k))


def mcnemar_power(n: int, discordance_rate: float, delta: float, alpha: float = 0.05) -> float:
    """Unconditional exact power under the paired-binary sensitivity model."""
    q = discordance_rate
    if q <= 0 or delta < 0 or delta > q:
        return 0.0
    direction_probability = (q + delta) / (2 * q)
    total = 0.0
    for discordant in range(n + 1):
        p_discordant = _binom_pmf(n, discordant, q)
        reject_given_discordant = 0.0
        for a_only in range(discordant + 1):
            b_only = discordant - a_only
            if exact_mcnemar_p(a_only, b_only) <= alpha:
                reject_given_discordant += _binom_pmf(
                    discordant, a_only, direction_probability
                )
        total += p_discordant * reject_given_discordant
    return total


def mde_80(
    n: int,
    discordant_pairs: int,
    alpha: float = 0.05,
    target_power: float = 0.80,
) -> float | None:
    q = discordant_pairs / n
    if q <= 0 or mcnemar_power(n, q, q, alpha) < target_power:
        return None
    low, high = 0.0, q
    for _ in range(60):
        middle = (low + high) / 2
        if mcnemar_power(n, q, middle, alpha) >= target_power:
            high = middle
        else:
            low = middle
    return high

