from app.services.analytics import deployment_risk, linear_forecast, weighted_utilization


def test_weighted_utilization():
    score = weighted_utilization(0.5, 0.4, 0.3, 0.2)
    assert round(score, 2) == 0.40


def test_linear_forecast_increasing_series():
    assert linear_forecast([100, 110, 120, 130]) == 140.0


def test_deployment_risk_changes_with_evidence():
    low = deployment_risk(
        test_failures=0,
        change_size=40,
        vulnerabilities=0,
        rollback_rate=0.02,
        target_utilization=0.40,
        active_incidents=0,
        environment="development",
    )
    high = deployment_risk(
        test_failures=3,
        change_size=400,
        vulnerabilities=2,
        rollback_rate=0.35,
        target_utilization=0.90,
        active_incidents=2,
        environment="production",
    )
    assert low.probability < high.probability
    assert high.level == "high"
