"""Hourly job: pipeline OHLCV -> Season 2 engine -> in-memory store."""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from data.loader import DataLoader
from engine.backtester import backtest
from engine.costs import turnover
from engine.metrics import max_drawdown, profit_factor, sharpe_ratio, total_return
from strategy.sma_crossover import SMACrossover

from app.config import Settings
from app.store import ResultStore

logger = logging.getLogger(__name__)


class RefreshError(RuntimeError):
    """The data came back, but cannot support a meaningful backtest."""


def make_loader(settings: Settings) -> DataLoader:
    return DataLoader(
        base_url=settings.pipeline_url, timeout=settings.request_timeout_seconds
    )


def compute_result(settings: Settings, loader: DataLoader, now: datetime) -> dict[str, Any]:
    """Run one backtest on the lookback window ending at ``now``. Blocking."""
    prices = loader.load(
        settings.symbol,
        settings.timeframe,
        start=now - timedelta(days=settings.lookback_days),
        end=now,
    )
    if len(prices) <= settings.sma_slow:
        raise RefreshError(
            f"{len(prices)} candles, need more than sma_slow={settings.sma_slow}"
        )

    signal = SMACrossover(fast=settings.sma_fast, slow=settings.sma_slow).generate(prices)
    result = backtest(prices, signal)

    return {
        "strategy": {
            "name": "sma_crossover",
            "fast": settings.sma_fast,
            "slow": settings.sma_slow,
        },
        "data": {
            "symbol": settings.symbol,
            "timeframe": settings.timeframe,
            "start": prices.index[0].isoformat(),
            "end": prices.index[-1].isoformat(),
            "bars": len(prices),
        },
        "metrics": {
            "total_return": _finite(total_return(result.equity)),
            "sharpe_ratio": _finite(
                sharpe_ratio(result.net_returns, settings.periods_per_year)
            ),
            "max_drawdown": _finite(max_drawdown(result.equity)),
            "profit_factor": _finite(profit_factor(result.net_returns)),
            "position_changes": int((turnover(result.position) > 0).sum()),
        },
        "equity": [
            {"timestamp": ts.isoformat(), "equity": float(value)}
            for ts, value in result.equity.items()
        ],
    }


async def refresh_once(
    store: ResultStore, settings: Settings, loader: DataLoader
) -> bool:
    """One refresh attempt. Never raises: a failure keeps the previous result."""
    now = datetime.now(timezone.utc)
    try:
        # the DataLoader is synchronous (requests + sleep-based retries)
        result = await asyncio.to_thread(compute_result, settings, loader, now)
    except Exception:
        logger.exception("refresh failed, keeping previous result")
        store.record_failure(now)
        return False
    store.set_result(result, now)
    logger.info("refresh ok: %d bars", result["data"]["bars"])
    return True


async def run_periodic(
    store: ResultStore, settings: Settings, loader: DataLoader
) -> None:
    """Refresh at startup, then every ``refresh_interval_seconds`` until cancelled."""
    while True:
        await refresh_once(store, settings, loader)
        await asyncio.sleep(settings.refresh_interval_seconds)


def _finite(value: float) -> float | None:
    """JSON has no inf/NaN (e.g. profit factor with no losing bar) -> null."""
    value = float(value)
    return value if math.isfinite(value) else None
