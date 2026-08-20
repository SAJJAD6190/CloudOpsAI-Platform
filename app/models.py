"""Core relational data model for the CloudOpsAI prototype."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    accounts: Mapped[list[CloudAccount]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(40), default="cloud_engineer", index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="users")


class CloudAccount(Base):
    __tablename__ = "cloud_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    account_name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(80))
    credential_ref: Mapped[str] = mapped_column(String(200), default="vault://demo/read-only")
    status: Mapped[str] = mapped_column(String(30), default="connected")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="accounts")
    resources: Mapped[list[CloudResource]] = relationship(back_populates="account")


class CloudResource(Base):
    __tablename__ = "cloud_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    cloud_account_id: Mapped[int] = mapped_column(ForeignKey("cloud_accounts.id"), index=True)
    native_id: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    resource_type: Mapped[str] = mapped_column(String(50), index=True)
    region: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    owner: Mapped[str] = mapped_column(String(120), default="Platform Team")
    project: Mapped[str] = mapped_column(String(100), default="Core Platform", index=True)
    environment: Mapped[str] = mapped_column(String(30), default="production", index=True)
    cpu_capacity: Mapped[float] = mapped_column(Float, default=2.0)
    memory_gb: Mapped[float] = mapped_column(Float, default=4.0)
    monthly_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[CloudAccount] = relationship(back_populates="resources")
    telemetry: Mapped[list[TelemetryMetric]] = relationship(back_populates="resource", cascade="all, delete-orphan")
    costs: Mapped[list[CostRecord]] = relationship(back_populates="resource", cascade="all, delete-orphan")
    recommendations: Mapped[list[Recommendation]] = relationship(back_populates="resource")


class TelemetryMetric(Base):
    __tablename__ = "telemetry_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("cloud_resources.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    cpu_util: Mapped[float] = mapped_column(Float)
    memory_util: Mapped[float] = mapped_column(Float)
    storage_util: Mapped[float] = mapped_column(Float)
    network_util: Mapped[float] = mapped_column(Float)
    response_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)

    resource: Mapped[CloudResource] = relationship(back_populates="telemetry")


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("cloud_resources.id"), index=True)
    period: Mapped[str] = mapped_column(String(20), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")

    resource: Mapped[CloudResource] = relationship(back_populates="costs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("cloud_resources.id"), nullable=True)
    version: Mapped[str] = mapped_column(String(60))
    environment: Mapped[str] = mapped_column(String(30), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="assessed")
    test_failures: Mapped[int] = mapped_column(Integer, default=0)
    change_size: Mapped[int] = mapped_column(Integer, default=0)
    vulnerabilities: Mapped[int] = mapped_column(Integer, default=0)
    rollback_rate: Mapped[float] = mapped_column(Float, default=0.0)
    target_utilization: Mapped[float] = mapped_column(Float, default=0.0)
    active_incidents: Mapped[int] = mapped_column(Integer, default=0)
    risk_probability: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    reasons: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("cloud_resources.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    expected_benefit: Mapped[str] = mapped_column(Text)
    expected_saving: Mapped[float] = mapped_column(Float, default=0.0)
    possible_impact: Mapped[str] = mapped_column(Text)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    required_role: Mapped[str] = mapped_column(String(40), default="cloud_admin")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    model_version: Mapped[str] = mapped_column(String(40), default="rules-v1.0")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    resource: Mapped[CloudResource | None] = relationship(back_populates="recommendations")
    approvals: Mapped[list[Approval]] = relationship(back_populates="recommendation", cascade="all, delete-orphan")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recommendation: Mapped[Recommendation] = relationship(back_populates="approvals")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
