"""Runtime settings, read once from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

YEAR = pd.Timedelta(days=365)


@dataclass(frozen=True)
class Settings:
    pipeline_url: str = "http://api.pipeline.svc.cluster.local:8000"
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    lookback_days: int = 30
    sma_fast: int = 10
    sma_slow: int = 30
    refresh_interval_seconds: int = 3600
    request_timeout_seconds: float = 10.0

    @property
    def periods_per_year(self) -> int:
        """Bars per year for ``timeframe``, used to annualize Sharpe."""
        return int(YEAR / pd.Timedelta(self.timeframe))

    @property
    def stale_after_seconds(self) -> int:
        """A result older than two refresh periods means refreshes are failing."""
        return 2 * self.refresh_interval_seconds

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            pipeline_url=os.getenv("PIPELINE_URL", cls.pipeline_url),
            symbol=os.getenv("SYMBOL", cls.symbol),
            timeframe=os.getenv("TIMEFRAME", cls.timeframe),
            lookback_days=int(os.getenv("LOOKBACK_DAYS", cls.lookback_days)),
            sma_fast=int(os.getenv("SMA_FAST", cls.sma_fast)),
            sma_slow=int(os.getenv("SMA_SLOW", cls.sma_slow)),
            refresh_interval_seconds=int(
                os.getenv("REFRESH_INTERVAL_SECONDS", cls.refresh_interval_seconds)
            ),
            request_timeout_seconds=float(
                os.getenv("REQUEST_TIMEOUT_SECONDS", cls.request_timeout_seconds)
            ),
        )
