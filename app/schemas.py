"""Pydantic request schemas for API endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TelemetryCreate(BaseModel):
    resource_id: int
    observed_at: datetime | None = None
    cpu_util: float = Field(ge=0, le=1)
    memory_util: float = Field(ge=0, le=1)
    storage_util: float = Field(ge=0, le=1)
    network_util: float = Field(ge=0, le=1)
    response_time_ms: float = Field(default=0, ge=0)
    error_rate: float = Field(default=0, ge=0, le=1)


class DeploymentRiskRequest(BaseModel):
    version: str = "v-next"
    environment: str = "production"
    provider: str = "AWS"
    resource_id: int | None = None
    test_failures: int = Field(default=0, ge=0)
    change_size: int = Field(default=50, ge=0)
    vulnerabilities: int = Field(default=0, ge=0)
    rollback_rate: float = Field(default=0.05, ge=0, le=1)
    target_utilization: float = Field(default=0.55, ge=0, le=1)
    active_incidents: int = Field(default=0, ge=0)


class RecommendationDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject|defer)$")
    comment: str = Field(default="", max_length=500)
