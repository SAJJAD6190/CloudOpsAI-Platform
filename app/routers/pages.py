"""HTML dashboard routes."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Approval,
    AuditEvent,
    CloudAccount,
    CloudResource,
    CostRecord,
    Deployment,
    Recommendation,
)
from app.security import current_user_from_request
from app.services.analytics import linear_forecast
from app.services.recommendations import generate_recommendations


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _page_user(request: Request, db: Session):
    user = current_user_from_request(request, db)
    if not user:
        return None
    return user


def _sparkline_points(values: list[float], width: int = 720, height: int = 180, pad: int = 14) -> str:
    if not values:
        return ""
    low, high = min(values), max(values)
    span = max(high - low, 1.0)
    points = []
    for index, value in enumerate(values):
        x = pad + index * (width - 2 * pad) / max(len(values) - 1, 1)
        y = height - pad - (value - low) * (height - 2 * pad) / span
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _base_context(request: Request, user, **kwargs):
    return {"request": request, "user": user, **kwargs}


@router.get("/")
def home(request: Request):
    return RedirectResponse("/dashboard" if request.session.get("user_id") else "/login", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    resources = db.scalars(
        select(CloudResource)
        .where(CloudResource.organization_id == user.organization_id)
        .options(selectinload(CloudResource.account))
    ).all()
    pending = db.scalar(
        select(func.count(Recommendation.id)).where(
            Recommendation.organization_id == user.organization_id,
            Recommendation.status == "pending",
        )
    ) or 0
    high_risk = db.scalar(
        select(func.count(Deployment.id)).where(
            Deployment.organization_id == user.organization_id,
            Deployment.risk_level == "high",
        )
    ) or 0

    provider_counts = Counter(resource.account.provider for resource in resources)
    current_cost = sum(resource.monthly_cost for resource in resources)
    cost_rows = db.execute(
        select(CostRecord.period, func.sum(CostRecord.amount))
        .join(CloudResource, CostRecord.resource_id == CloudResource.id)
        .where(CloudResource.organization_id == user.organization_id)
        .group_by(CostRecord.period)
        .order_by(CostRecord.period)
    ).all()
    periods = [row[0] for row in cost_rows]
    values = [round(float(row[1]), 2) for row in cost_rows]
    forecast = linear_forecast(values)
    recommendations = db.scalars(
        select(Recommendation)
        .where(Recommendation.organization_id == user.organization_id)
        .options(selectinload(Recommendation.resource))
        .order_by(desc(Recommendation.confidence), desc(Recommendation.expected_saving))
        .limit(5)
    ).all()
    deployments = db.scalars(
        select(Deployment)
        .where(Deployment.organization_id == user.organization_id)
        .order_by(desc(Deployment.created_at))
        .limit(4)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=_base_context(
            request,
            user,
            resource_count=len(resources),
            current_cost=current_cost,
            pending=pending,
            high_risk=high_risk,
            provider_counts=provider_counts,
            max_provider=max(provider_counts.values(), default=1),
            cost_periods=periods,
            cost_values=values,
            cost_forecast=forecast,
            sparkline=_sparkline_points(values),
            recommendations=recommendations,
            deployments=deployments,
        ),
    )


@router.get("/resources")
def resources_page(
    request: Request,
    provider: str = Query(default=""),
    status: str = Query(default=""),
    db: Session = Depends(get_db),
):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    query = (
        select(CloudResource)
        .where(CloudResource.organization_id == user.organization_id)
        .options(selectinload(CloudResource.account))
        .order_by(CloudResource.project, CloudResource.name)
    )
    if provider:
        query = query.join(CloudAccount).where(CloudAccount.provider == provider)
    if status:
        query = query.where(CloudResource.status == status)
    rows = db.scalars(query).all()
    providers = db.scalars(
        select(CloudAccount.provider).where(CloudAccount.organization_id == user.organization_id).distinct()
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="resources.html",
        context=_base_context(
            request,
            user,
            resources=rows,
            providers=providers,
            selected_provider=provider,
            selected_status=status,
        ),
    )


@router.get("/recommendations")
def recommendations_page(
    request: Request,
    status: str = Query(default=""),
    db: Session = Depends(get_db),
):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    query = (
        select(Recommendation)
        .where(Recommendation.organization_id == user.organization_id)
        .options(selectinload(Recommendation.resource), selectinload(Recommendation.approvals))
        .order_by(desc(Recommendation.created_at))
    )
    if status:
        query = query.where(Recommendation.status == status)
    rows = db.scalars(query).all()
    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context=_base_context(request, user, recommendations=rows, selected_status=status),
    )


@router.post("/recommendations/generate")
def generate_page_recommendations(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    generated = generate_recommendations(db, user.organization_id, user.id)
    return RedirectResponse(f"/recommendations?notice=Generated+{len(generated)}+new+recommendation(s)", status_code=303)


@router.post("/recommendations/{recommendation_id}/decision")
def recommendation_decision(
    recommendation_id: int,
    request: Request,
    decision: str = Form(...),
    comment: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    recommendation = db.get(Recommendation, recommendation_id)
    if not recommendation or recommendation.organization_id != user.organization_id:
        return RedirectResponse("/recommendations?notice=Recommendation+not+found", status_code=303)
    if decision not in {"approve", "reject", "defer"}:
        return RedirectResponse("/recommendations?notice=Invalid+decision", status_code=303)
    if user.role not in {"cloud_admin", "cloud_engineer", "finance_manager", "security_analyst"}:
        return RedirectResponse("/recommendations?notice=Insufficient+permission", status_code=303)

    status_map = {"approve": "approved", "reject": "rejected", "defer": "deferred"}
    recommendation.status = status_map[decision]
    recommendation.updated_at = datetime.utcnow()
    db.add(Approval(recommendation_id=recommendation.id, user_id=user.id, decision=decision, comment=comment))
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type=f"recommendation.{decision}",
            target_type="recommendation",
            target_id=str(recommendation.id),
            details=comment or f"Recommendation {decision}d by {user.full_name}.",
        )
    )
    db.commit()
    return RedirectResponse("/recommendations?notice=Decision+recorded", status_code=303)


@router.post("/recommendations/{recommendation_id}/execute")
def execute_recommendation(recommendation_id: int, request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    recommendation = db.get(Recommendation, recommendation_id)
    if not recommendation or recommendation.organization_id != user.organization_id:
        return RedirectResponse("/recommendations?notice=Recommendation+not+found", status_code=303)
    if recommendation.status != "approved":
        return RedirectResponse("/recommendations?notice=Only+approved+recommendations+can+be+executed", status_code=303)
    recommendation.status = "executed"
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type="recommendation.executed",
            target_type="recommendation",
            target_id=str(recommendation.id),
            details="Simulated execution completed. No real cloud resource was modified.",
        )
    )
    db.commit()
    return RedirectResponse("/recommendations?notice=Simulated+execution+completed", status_code=303)


@router.post("/recommendations/{recommendation_id}/verify")
def verify_recommendation(recommendation_id: int, request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    recommendation = db.get(Recommendation, recommendation_id)
    if not recommendation or recommendation.organization_id != user.organization_id:
        return RedirectResponse("/recommendations?notice=Recommendation+not+found", status_code=303)
    if recommendation.status != "executed":
        return RedirectResponse("/recommendations?notice=Execute+the+recommendation+before+verification", status_code=303)
    recommendation.status = "verified"
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            user_id=user.id,
            event_type="recommendation.verified",
            target_type="recommendation",
            target_id=str(recommendation.id),
            details="Outcome verified in the demonstration workflow.",
        )
    )
    db.commit()
    return RedirectResponse("/recommendations?notice=Outcome+verified", status_code=303)


@router.get("/deployments")
def deployments_page(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    rows = db.scalars(
        select(Deployment)
        .where(Deployment.organization_id == user.organization_id)
        .order_by(desc(Deployment.created_at))
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="deployments.html",
        context=_base_context(request, user, deployments=rows),
    )


@router.get("/audits")
def audits_page(request: Request, db: Session = Depends(get_db)):
    user = _page_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role not in {"cloud_admin", "security_analyst"}:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context=_base_context(request, user, message="Audit access is limited to administrators and security analysts."),
            status_code=403,
        )
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == user.organization_id)
        .order_by(desc(AuditEvent.created_at))
        .limit(100)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="audits.html",
        context=_base_context(request, user, audits=rows),
    )
