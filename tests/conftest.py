from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import Settings


def ohlcv(n_bars: int, seed: int = 7, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Hourly contract frame (the DataLoader output shape), random-walk closes."""
    rng = np.random.default_rng(seed)
    closes = 30_000 + np.cumsum(rng.normal(0, 80, n_bars))
    end = end or pd.Timestamp("2026-09-29 12:00", tz="UTC")
    idx = pd.date_range(end=end, periods=n_bars, freq="1h", name="timestamp")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 20,
            "low": closes - 20,
            "close": closes,
            "volume": rng.uniform(10, 100, n_bars),
        },
        index=idx,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(pipeline_url="http://pipeline.test", sma_fast=3, sma_slow=8)
