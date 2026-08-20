"""Explainable rule-based recommendation engine for the MVP."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, CloudResource, Recommendation, TelemetryMetric
from app.services.analytics import data_quality_score, weighted_utilization


ACTIVE_STATUSES = {"pending", "approved", "executed"}


def _latest_metrics(db: Session, resource_id: int, limit: int = 14) -> list[TelemetryMetric]:
    rows = db.scalars(
        select(TelemetryMetric)
        .where(TelemetryMetric.resource_id == resource_id)
        .order_by(desc(TelemetryMetric.observed_at))
        .limit(limit)
    ).all()
    return list(reversed(rows))


def _has_active_duplicate(db: Session, resource_id: int, action: str) -> bool:
    existing = db.scalar(
        select(Recommendation).where(
            Recommendation.resource_id == resource_id,
            Recommendation.action == action,
            Recommendation.status.in_(ACTIVE_STATUSES),
        )
    )
    return existing is not None


def generate_recommendations(db: Session, organization_id: int, actor_user_id: int | None = None) -> list[Recommendation]:
    resources = db.scalars(
        select(CloudResource).where(CloudResource.organization_id == organization_id)
    ).all()
    generated: list[Recommendation] = []
    now = datetime.utcnow()

    for resource in resources:
        metrics = _latest_metrics(db, resource.id)
        if len(metrics) < 3:
            continue

        scores = [
            weighted_utilization(m.cpu_util, m.memory_util, m.storage_util, m.network_util)
            for m in metrics
        ]
        average_util = statistics.fmean(scores)
        latest = metrics[-1]
        freshness_hours = max(0.0, (now - latest.observed_at).total_seconds() / 3600)
        quality = data_quality_score(len(metrics), freshness_hours)
        stability = max(0.45, 1.0 - min(statistics.pstdev(scores), 0.55))
        confidence = round(min(0.98, quality * stability), 2)

        candidates: list[dict[str, object]] = []

        if average_util < 0.25 and resource.monthly_cost >= 25 and resource.status == "running":
            candidates.append(
                {
                    "action": "Downsize resource",
                    "reason": f"Average weighted utilization is only {average_util:.0%}.",
                    "evidence": (
                        f"{len(metrics)} telemetry samples; latest CPU {latest.cpu_util:.0%}, "
                        f"memory {latest.memory_util:.0%}; monthly cost USD {resource.monthly_cost:.2f}."
                    ),
                    "expected_benefit": "Reduce unnecessary capacity while retaining operational headroom.",
                    "expected_saving": round(resource.monthly_cost * 0.30, 2),
                    "possible_impact": "Performance may decline if future demand increases unexpectedly.",
                    "risk_score": 0.22,
                }
            )

        if average_util > 0.82:
            candidates.append(
                {
                    "action": "Scale up or enable autoscaling",
                    "reason": f"Average weighted utilization is elevated at {average_util:.0%}.",
                    "evidence": (
                        f"Latest CPU {latest.cpu_util:.0%}, memory {latest.memory_util:.0%}, "
                        f"response time {latest.response_time_ms:.0f} ms."
                    ),
                    "expected_benefit": "Improve performance, stability, and capacity during peak demand.",
                    "expected_saving": 0.0,
                    "possible_impact": "Monthly infrastructure cost is likely to increase.",
                    "risk_score": 0.16,
                }
            )

        if resource.resource_type.lower() in {"storage", "disk", "volume"} and latest.storage_util < 0.10:
            candidates.append(
                {
                    "action": "Archive or remove unused storage",
                    "reason": f"Storage utilization is only {latest.storage_util:.0%}.",
                    "evidence": f"Resource has remained visible for {len(metrics)} observation periods.",
                    "expected_benefit": "Eliminate storage waste and simplify the inventory.",
                    "expected_saving": round(resource.monthly_cost * 0.80, 2),
                    "possible_impact": "Data loss is possible unless ownership and retention requirements are verified.",
                    "risk_score": 0.48,
                }
            )

        if resource.monthly_cost >= 350 and average_util < 0.55:
            candidates.append(
                {
                    "action": "Review provider or pricing plan",
                    "reason": "High monthly cost is not matched by consistently high utilization.",
                    "evidence": f"Cost USD {resource.monthly_cost:.2f}; average utilization {average_util:.0%}.",
                    "expected_benefit": "Identify a lower-cost instance family, commitment, region, or provider.",
                    "expected_saving": round(resource.monthly_cost * 0.18, 2),
                    "possible_impact": "Migration effort, compatibility, latency, and contractual constraints require review.",
                    "risk_score": 0.35,
                }
            )

        for candidate in candidates:
            action = str(candidate["action"])
            if _has_active_duplicate(db, resource.id, action):
                continue
            recommendation = Recommendation(
                organization_id=organization_id,
                resource_id=resource.id,
                action=action,
                reason=str(candidate["reason"]),
                evidence=str(candidate["evidence"]),
                confidence=confidence,
                expected_benefit=str(candidate["expected_benefit"]),
                expected_saving=float(candidate["expected_saving"]),
                possible_impact=str(candidate["possible_impact"]),
                risk_score=float(candidate["risk_score"]),
                required_role="cloud_admin" if float(candidate["risk_score"]) >= 0.40 else "cloud_engineer",
                status="pending",
                model_version="rules-v1.0",
                expires_at=now + timedelta(days=7),
            )
            db.add(recommendation)
            generated.append(recommendation)

    db.flush()
    db.add(
        AuditEvent(
            organization_id=organization_id,
            user_id=actor_user_id,
            event_type="recommendations.generated",
            target_type="recommendation_batch",
            target_id=str(now.timestamp()),
            details=f"Generated {len(generated)} new explainable recommendation(s).",
        )
    )
    db.commit()
    for recommendation in generated:
        db.refresh(recommendation)
    return generated
