"""JSON API endpoints for programmatic use and Swagger documentation."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Approval, AuditEvent, CloudResource, Deployment, Recommendation, TelemetryMetric
from app.schemas import DeploymentRiskRequest, RecommendationDecision, TelemetryCreate
from app.security import require_api_user
from app.services.analytics import deployment_risk
from app.services.recommendations import generate_recommendations


router = APIRouter(prefix="/api", tags=["CloudOpsAI API"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "CloudOpsAI", "mode": "demonstration"}


@router.get("/dashboard")
def dashboard_api(request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db)
    resources = db.scalar(
        select(func.count(CloudResource.id)).where(CloudResource.organization_id == user.organization_id)
    ) or 0
    monthly_cost = db.scalar(
        select(func.sum(CloudResource.monthly_cost)).where(CloudResource.organization_id == user.organization_id)
    ) or 0.0
    pending = db.scalar(
        select(func.count(Recommendation.id)).where(
            Recommendation.organization_id == user.organization_id,
            Recommendation.status == "pending",
        )
    ) or 0
    return {
        "resources": resources,
        "monthly_cost_usd": round(float(monthly_cost), 2),
        "pending_recommendations": pending,
    }


@router.get("/resources")
def resources_api(request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db)
    rows = db.scalars(
        select(CloudResource)
        .where(CloudResource.organization_id == user.organization_id)
        .options(selectinload(CloudResource.account))
        .order_by(CloudResource.name)
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "provider": row.account.provider,
            "resource_type": row.resource_type,
            "region": row.region,
            "status": row.status,
            "project": row.project,
            "environment": row.environment,
            "monthly_cost_usd": row.monthly_cost,
        }
        for row in rows
    ]


@router.post("/telemetry", status_code=201)
def create_telemetry(payload: TelemetryCreate, request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db, {"cloud_admin", "cloud_engineer"})
    resource = db.get(CloudResource, payload.resource_id)
    if not resource or resource.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    metric = TelemetryMetric(
        resource_id=resource.id,
        observed_at=payload.observed_at or datetime.utcnow(),
        cpu_util=payload.cpu_util,
        memory_util=payload.memory_util,
        storage_util=payload.storage_util,
        network_util=payload.network_util,
        response_time_ms=payload.response_time_ms,
        error_rate=payload.error_rate,
    )
    db.add(metric)
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type="telemetry.created",
            target_type="resource",
            target_id=str(resource.id),
            details="Telemetry record added through the API.",
        )
    )
    db.commit()
    db.refresh(metric)
    return {"id": metric.id, "resource_id": metric.resource_id, "observed_at": metric.observed_at}


@router.get("/recommendations")
def recommendations_api(request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db)
    rows = db.scalars(
        select(Recommendation)
        .where(Recommendation.organization_id == user.organization_id)
        .options(selectinload(Recommendation.resource))
        .order_by(desc(Recommendation.created_at))
    ).all()
    return [
        {
            "id": row.id,
            "resource": row.resource.name if row.resource else None,
            "action": row.action,
            "reason": row.reason,
            "evidence": row.evidence,
            "confidence": row.confidence,
            "expected_saving_usd": row.expected_saving,
            "risk_score": row.risk_score,
            "status": row.status,
            "expires_at": row.expires_at,
        }
        for row in rows
    ]


@router.post("/recommendations/generate")
def generate_api_recommendations(request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db, {"cloud_admin", "cloud_engineer"})
    rows = generate_recommendations(db, user.organization_id, user.id)
    return {"generated": len(rows), "ids": [row.id for row in rows]}


@router.post("/recommendations/{recommendation_id}/decision")
def recommendation_decision_api(
    recommendation_id: int,
    payload: RecommendationDecision,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_api_user(request, db, {"cloud_admin", "cloud_engineer", "finance_manager", "security_analyst"})
    row = db.get(Recommendation, recommendation_id)
    if not row or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    row.status = {"approve": "approved", "reject": "rejected", "defer": "deferred"}[payload.decision]
    db.add(Approval(recommendation_id=row.id, user_id=user.id, decision=payload.decision, comment=payload.comment))
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type=f"recommendation.{payload.decision}",
            target_type="recommendation",
            target_id=str(row.id),
            details=payload.comment,
        )
    )
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/deployments/risk", status_code=201)
def deployment_risk_api(payload: DeploymentRiskRequest, request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db, {"cloud_admin", "cloud_engineer", "security_analyst"})
    result = deployment_risk(
        test_failures=payload.test_failures,
        change_size=payload.change_size,
        vulnerabilities=payload.vulnerabilities,
        rollback_rate=payload.rollback_rate,
        target_utilization=payload.target_utilization,
        active_incidents=payload.active_incidents,
        environment=payload.environment,
    )
    deployment = Deployment(
        organization_id=user.organization_id,
        resource_id=payload.resource_id,
        version=payload.version,
        environment=payload.environment,
        provider=payload.provider,
        status="assessed",
        test_failures=payload.test_failures,
        change_size=payload.change_size,
        vulnerabilities=payload.vulnerabilities,
        rollback_rate=payload.rollback_rate,
        target_utilization=payload.target_utilization,
        active_incidents=payload.active_incidents,
        risk_probability=result.probability,
        risk_level=result.level,
        reasons="; ".join(result.reasons),
    )
    db.add(deployment)
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type="deployment.assessed",
            target_type="deployment",
            target_id=payload.version,
            details=f"Risk {result.level} ({result.probability:.1%}).",
        )
    )
    db.commit()
    db.refresh(deployment)
    return {
        "deployment_id": deployment.id,
        "probability": result.probability,
        "level": result.level,
        "reasons": result.reasons,
        "recommended_action": result.recommended_action,
    }


@router.get("/audits")
def audits_api(request: Request, db: Session = Depends(get_db)):
    user = require_api_user(request, db, {"cloud_admin", "security_analyst"})
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == user.organization_id)
        .order_by(desc(AuditEvent.created_at))
        .limit(100)
    ).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows
    ]
