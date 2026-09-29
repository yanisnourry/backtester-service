from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import DISCLAIMER, app
from app.store import ResultStore

RESULT = {
    "strategy": {"name": "sma_crossover", "fast": 3, "slow": 8},
    "data": {"symbol": "BTCUSDT", "timeframe": "1h", "bars": 2},
    "metrics": {"total_return": 0.01},
    "equity": [],
}


@pytest.fixture
def client(settings):
    # no `with`: the lifespan (and its refresh task hitting the network) never runs
    app.state.settings = settings
    app.state.store = ResultStore()
    return TestClient(app)


def test_results_before_first_refresh_is_503_with_disclaimer(client):
    resp = client.get("/results")
    assert resp.status_code == 503
    assert resp.json()["disclaimer"] == DISCLAIMER


def test_results_returns_latest_with_disclaimer(client):
    app.state.store.set_result(RESULT, datetime.now(timezone.utc))
    body = client.get("/results").json()

    assert body["disclaimer"] == DISCLAIMER
    assert body["stale"] is False
    assert body["metrics"] == RESULT["metrics"]
    assert body["strategy"] == RESULT["strategy"]


def test_results_flagged_stale_but_still_served(client, settings):
    old = datetime.now(timezone.utc) - timedelta(seconds=settings.stale_after_seconds + 60)
    app.state.store.set_result(RESULT, old)
    app.state.store.record_failure(datetime.now(timezone.utc))

    resp = client.get("/results")
    assert resp.status_code == 200
    assert resp.json()["stale"] is True
    assert resp.json()["metrics"] == RESULT["metrics"]


def test_health_ok_even_without_result(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["has_result"] is False
    assert resp.json()["stale"] is True


def test_health_reports_failed_attempt(client):
    now = datetime.now(timezone.utc)
    app.state.store.set_result(RESULT, now)
    app.state.store.record_failure(now)

    body = client.get("/health").json()
    assert body["has_result"] is True
    assert body["last_attempt_ok"] is False


def test_only_health_and_results_are_exposed():
    assert {r.path for r in app.routes} == {"/health", "/results"}
