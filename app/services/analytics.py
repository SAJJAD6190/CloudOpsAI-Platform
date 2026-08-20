"""Transparent analytical functions used by the CloudOpsAI MVP."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Sequence


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def weighted_utilization(
    cpu: float,
    memory: float,
    storage: float,
    network: float,
    weights: tuple[float, float, float, float] = (0.40, 0.30, 0.20, 0.10),
) -> float:
    """Calculate the report's weighted utilization score on a 0-1 scale."""
    wc, wm, ws, wn = weights
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-8):
        raise ValueError("Utilization weights must sum to 1.0")
    return clamp(wc * cpu + wm * memory + ws * storage + wn * network)


def data_quality_score(sample_count: int, freshness_hours: float, missing_ratio: float = 0.0) -> float:
    completeness = clamp(sample_count / 14.0)
    freshness = clamp(1.0 - freshness_hours / 72.0)
    validity = clamp(1.0 - missing_ratio)
    return round(0.45 * completeness + 0.35 * freshness + 0.20 * validity, 4)


def anomaly_z_score(values: Sequence[float], current: float | None = None) -> float:
    if not values:
        return 0.0
    target = values[-1] if current is None else current
    baseline = list(values[:-1] if current is None and len(values) > 1 else values)
    if len(baseline) < 2:
        return 0.0
    mean = statistics.fmean(baseline)
    stdev = statistics.pstdev(baseline)
    if stdev < 1e-8:
        return 0.0
    return round((target - mean) / stdev, 4)


def linear_forecast(values: Sequence[float], horizon: int = 1) -> float:
    """Small dependency-free linear trend forecast."""
    if not values:
        return 0.0
    if len(values) == 1:
        return round(float(values[0]), 2)
    n = len(values)
    xs = list(range(n))
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = 0.0 if denominator == 0 else sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denominator
    intercept = y_mean - slope * x_mean
    prediction = intercept + slope * (n - 1 + horizon)
    return round(max(0.0, prediction), 2)


@dataclass(frozen=True)
class DeploymentRiskResult:
    probability: float
    level: str
    reasons: list[str]
    recommended_action: str


def deployment_risk(
    *,
    test_failures: int,
    change_size: int,
    vulnerabilities: int,
    rollback_rate: float,
    target_utilization: float,
    active_incidents: int,
    environment: str = "production",
) -> DeploymentRiskResult:
    """Interpretable logistic risk baseline based on the project report."""
    normalized_change = clamp(change_size / 500.0)
    score = (
        -2.25
        + 0.70 * min(test_failures, 5)
        + 0.55 * min(vulnerabilities, 5)
        + 1.30 * clamp(rollback_rate)
        + 1.55 * clamp(target_utilization)
        + 0.65 * min(active_incidents, 4)
        + 0.85 * normalized_change
        + (0.35 if environment.lower() == "production" else 0.0)
    )
    probability = 1.0 / (1.0 + math.exp(-score))

    reasons: list[str] = []
    if test_failures:
        reasons.append(f"{test_failures} failed test(s)")
    if vulnerabilities:
        reasons.append(f"{vulnerabilities} unresolved security finding(s)")
    if target_utilization >= 0.75:
        reasons.append("target environment is heavily utilized")
    if active_incidents:
        reasons.append(f"{active_incidents} active incident(s)")
    if rollback_rate >= 0.20:
        reasons.append("historical rollback rate is elevated")
    if change_size >= 250:
        reasons.append("large deployment change size")
    if not reasons:
        reasons.append("no major risk indicators detected")

    if probability < 0.35:
        level = "low"
        action = "Proceed through the normal deployment process."
    elif probability < 0.65:
        level = "medium"
        action = "Require additional tests or an authorized approval before release."
    else:
        level = "high"
        action = "Postpone or block the release until the strongest risk factors are resolved."

    return DeploymentRiskResult(round(probability, 4), level, reasons, action)
