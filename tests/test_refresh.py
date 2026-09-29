from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from data.loader import DataLoader, DataLoaderError

from app.refresh import RefreshError, compute_result, refresh_once
from app.store import ResultStore
from tests.conftest import ohlcv

NOW = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)


class FakeLoader:
    def __init__(self, frame=None, error=None):
        self.frame = frame
        self.error = error
        self.calls: list[dict] = []

    def load(self, symbol, timeframe, start=None, end=None):
        self.calls.append(dict(symbol=symbol, timeframe=timeframe, start=start, end=end))
        if self.error is not None:
            raise self.error
        return self.frame


def test_result_shape_and_json_safe(settings):
    result = compute_result(settings, FakeLoader(ohlcv(200)), NOW)

    assert set(result) == {"strategy", "data", "metrics", "equity"}
    assert result["strategy"] == {"name": "sma_crossover", "fast": 3, "slow": 8}
    assert result["data"]["bars"] == 200
    assert len(result["equity"]) == 200
    assert result["equity"][0]["equity"] == pytest.approx(1.0)
    assert set(result["metrics"]) == {
        "total_return", "sharpe_ratio", "max_drawdown", "profit_factor", "position_changes",
    }
    json.dumps(result, allow_nan=False)  # what the API will serialize


def test_never_exposes_current_position(settings):
    # the latest position is what a reader could mistake for a live signal
    result = compute_result(settings, FakeLoader(ohlcv(200)), NOW)
    assert "position" not in json.dumps(result).replace("position_changes", "")


def test_loads_lookback_window_ending_now(settings):
    loader = FakeLoader(ohlcv(200))
    compute_result(settings, loader, NOW)

    call = loader.calls[0]
    assert call["symbol"] == settings.symbol
    assert call["timeframe"] == settings.timeframe
    assert call["end"] == NOW
    assert (NOW - call["start"]).days == settings.lookback_days


def test_metrics_reuse_the_engine(settings):
    from engine.backtester import backtest
    from engine.metrics import sharpe_ratio
    from strategy.sma_crossover import SMACrossover

    prices = ohlcv(200)
    result = compute_result(settings, FakeLoader(prices), NOW)
    expected = backtest(prices, SMACrossover(fast=3, slow=8).generate(prices))

    assert result["metrics"]["sharpe_ratio"] == pytest.approx(
        sharpe_ratio(expected.net_returns, 24 * 365)
    )
    assert result["equity"][-1]["equity"] == pytest.approx(expected.equity.iloc[-1])


def test_non_finite_metric_becomes_null(settings, monkeypatch):
    # frictionless monotonic rise: long all the way, no losing bar -> profit factor = inf
    prices = ohlcv(60)
    rising = [100.0 + i for i in range(60)]
    prices["open"] = prices["close"] = rising
    prices["high"] = prices["close"] + 1
    prices["low"] = prices["close"] - 1

    import app.refresh as mod

    original = mod.backtest
    monkeypatch.setattr(
        mod, "backtest", lambda p, s: original(p, s, fee_bps=0, slippage_bps=0)
    )
    result = compute_result(settings, FakeLoader(prices), NOW)
    assert result["metrics"]["profit_factor"] is None


def test_too_few_candles_raises(settings):
    with pytest.raises(RefreshError, match="need more than"):
        compute_result(settings, FakeLoader(ohlcv(8)), NOW)


async def test_refresh_once_stores_result(settings):
    store = ResultStore()
    ok = await refresh_once(store, settings, FakeLoader(ohlcv(200)))

    snap = store.snapshot()
    assert ok
    assert snap.result["data"]["bars"] == 200
    assert snap.last_attempt_ok is True


async def test_refresh_failure_keeps_previous_result(settings):
    store = ResultStore()
    await refresh_once(store, settings, FakeLoader(ohlcv(200)))
    before = store.snapshot()

    ok = await refresh_once(store, settings, FakeLoader(error=DataLoaderError("down")))

    after = store.snapshot()
    assert not ok
    assert after.result is before.result
    assert after.computed_at == before.computed_at
    assert after.last_attempt_ok is False


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class PipelineSession:
    """Only the HTTP layer faked, behaving like the pipeline API (ascending, start inclusive)."""

    def __init__(self, rows):
        self.rows = rows
        self.urls: list[str] = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        start = pd.Timestamp(params["start"]) if "start" in params else None
        page = [r for r in self.rows if start is None or pd.Timestamp(r["timestamp"]) >= start]
        return _Resp(page[: params["limit"]])


async def test_refresh_through_real_loader_against_mocked_api(settings):
    prices = ohlcv(100)
    rows = [
        {"timestamp": ts.isoformat(), **{c: str(prices.at[ts, c]) for c in prices.columns}}
        for ts in prices.index
    ]
    session = PipelineSession(rows)
    loader = DataLoader(base_url=settings.pipeline_url, page_limit=40, session=session)
    store = ResultStore()

    assert await refresh_once(store, settings, loader)
    assert store.snapshot().result["data"]["bars"] == 100
    assert session.urls[0] == "http://pipeline.test/ohlcv/BTCUSDT/1h"
