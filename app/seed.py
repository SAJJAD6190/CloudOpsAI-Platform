"""Create deterministic demo data for first launch."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    CloudAccount,
    CloudResource,
    CostRecord,
    Deployment,
    Organization,
    TelemetryMetric,
    User,
)
from app.security import hash_password
from app.services.analytics import deployment_risk
from app.services.recommendations import generate_recommendations


DEMO_USERS = [
    ("System Administrator", "admin@cloudopsai.local", "cloud_admin", "admin123"),
    ("Cloud Engineer", "engineer@cloudopsai.local", "cloud_engineer", "engineer123"),
    ("Finance Manager", "finance@cloudopsai.local", "finance_manager", "finance123"),
    ("Security Analyst", "security@cloudopsai.local", "security_analyst", "security123"),
]


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(func.count(Organization.id))) > 0:
        return

    rng = random.Random(42)
    org = Organization(name="CloudOpsAI Demonstration Organization")
    db.add(org)
    db.flush()

    users: list[User] = []
    for full_name, email, role, password in DEMO_USERS:
        user = User(
            organization_id=org.id,
            full_name=full_name,
            email=email,
            role=role,
            password_hash=hash_password(password),
        )
        db.add(user)
        users.append(user)

    account_specs = [
        ("AWS", "Production AWS", "ap-southeast-1"),
        ("Azure", "Analytics Azure", "southeastasia"),
        ("GCP", "Data GCP", "asia-east1"),
    ]
    accounts: list[CloudAccount] = []
    for provider, name, region in account_specs:
        account = CloudAccount(
            organization_id=org.id,
            provider=provider,
            account_name=name,
            region=region,
            status="connected",
            last_sync_at=datetime.utcnow() - timedelta(minutes=rng.randint(2, 18)),
        )
        db.add(account)
        accounts.append(account)
    db.flush()

    resource_specs = [
        (0, "checkout-api", "compute", "running", "Payments", "production", 420, 0.18),
        (0, "customer-web", "compute", "running", "Experience", "production", 260, 0.67),
        (0, "legacy-volume", "storage", "running", "Core Platform", "production", 95, 0.04),
        (1, "analytics-worker", "compute", "running", "Analytics", "production", 510, 0.38),
        (1, "dev-test-vm", "compute", "running", "Development", "development", 120, 0.13),
        (1, "orders-db", "database", "running", "Orders", "production", 380, 0.86),
        (2, "event-stream", "compute", "running", "Data Platform", "production", 330, 0.74),
        (2, "backup-bucket", "storage", "running", "Core Platform", "production", 70, 0.42),
    ]

    resources: list[CloudResource] = []
    for idx, (account_idx, name, rtype, status, project, env, monthly_cost, base_util) in enumerate(resource_specs, start=1):
        account = accounts[account_idx]
        resource = CloudResource(
            organization_id=org.id,
            cloud_account_id=account.id,
            native_id=f"{account.provider.lower()}-resource-{idx:03d}",
            name=name,
            resource_type=rtype,
            region=account.region,
            status=status,
            owner="Platform Team" if project == "Core Platform" else f"{project} Team",
            project=project,
            environment=env,
            cpu_capacity=4 if rtype == "compute" else 2,
            memory_gb=16 if env == "production" else 8,
            monthly_cost=monthly_cost,
            created_at=datetime.utcnow() - timedelta(days=180 + idx * 10),
            last_seen_at=datetime.utcnow() - timedelta(minutes=rng.randint(1, 20)),
        )
        db.add(resource)
        db.flush()
        resources.append(resource)

        for day in range(14, 0, -1):
            noise = rng.uniform(-0.06, 0.06)
            util = min(0.98, max(0.02, base_util + noise))
            storage_util = 0.04 + rng.uniform(0, 0.025) if name == "legacy-volume" else min(0.96, max(0.05, util * rng.uniform(0.65, 1.05)))
            metric = TelemetryMetric(
                resource_id=resource.id,
                observed_at=datetime.utcnow() - timedelta(days=day, hours=rng.randint(0, 8)),
                cpu_util=util,
                memory_util=min(0.98, max(0.02, util * rng.uniform(0.85, 1.15))),
                storage_util=storage_util,
                network_util=min(0.95, max(0.01, util * rng.uniform(0.45, 0.85))),
                response_time_ms=70 + util * 420 + rng.uniform(-15, 20),
                error_rate=max(0.0, (util - 0.76) * 0.09 + rng.uniform(0, 0.008)),
            )
            db.add(metric)

        for month_back in range(5, -1, -1):
            month_date = datetime.utcnow().replace(day=1) - timedelta(days=month_back * 30)
            growth = 1 + (5 - month_back) * rng.uniform(0.005, 0.025)
            db.add(
                CostRecord(
                    resource_id=resource.id,
                    period=month_date.strftime("%Y-%m"),
                    amount=round(monthly_cost * growth * rng.uniform(0.94, 1.04), 2),
                    currency="USD",
                )
            )

    deployment_inputs = [
        ("v2.8.0", "AWS", 0, 85, 0, 0.05, 0.58, 0),
        ("v2.9.0-rc1", "Azure", 2, 310, 1, 0.22, 0.81, 1),
        ("v4.1.2", "GCP", 0, 140, 0, 0.08, 0.69, 0),
    ]
    for index, values in enumerate(deployment_inputs):
        version, provider, failures, change, vulns, rollback, util, incidents = values
        result = deployment_risk(
            test_failures=failures,
            change_size=change,
            vulnerabilities=vulns,
            rollback_rate=rollback,
            target_utilization=util,
            active_incidents=incidents,
            environment="production",
        )
        db.add(
            Deployment(
                organization_id=org.id,
                resource_id=resources[index].id,
                version=version,
                environment="production",
                provider=provider,
                status="assessed",
                test_failures=failures,
                change_size=change,
                vulnerabilities=vulns,
                rollback_rate=rollback,
                target_utilization=util,
                active_incidents=incidents,
                risk_probability=result.probability,
                risk_level=result.level,
                reasons="; ".join(result.reasons),
                created_at=datetime.utcnow() - timedelta(days=index * 2, hours=index * 3),
            )
        )

    db.add(
        AuditEvent(
            organization_id=org.id,
            user_id=None,
            event_type="system.seeded",
            target_type="system",
            target_id="demo",
            details="Created demonstration users, resources, telemetry, costs, and deployments.",
        )
    )
    db.commit()
    generate_recommendations(db, org.id, actor_user_id=None)
