# Backtester Service

A small, stateless FastAPI service that keeps a backtest **live**: every hour it
pulls fresh OHLCV from the market data pipeline's REST API, re-runs the
vectorized backtester engine on it, and serves the latest result.

> **Engineering demo, not a trading signal.** The result is a simulation of a
> plain SMA crossover used to exercise the engine end to end on real, refreshed
> data. It is not a recommendation, a forecast, or a record of real
> performance, and every `/results` response says so.

## What it is / what it is not

**It is** glue between two existing services: it adds no quant logic of its
own. Data comes from the [market-data-pipeline](https://github.com/yanisnourry/market-data-pipeline)
API; signal, backtest and metrics come from the
[vectorized-backtester](https://github.com/yanisnourry/vectorized-backtester)
engine, reused as a pinned dependency (no copy of its code).

**It is not** a strategy research tool. There is one demo strategy (SMA
crossover), no parameter search, and no history of past runs.

## How it works

```
market-data-pipeline API  --(HTTP, cluster DNS)-->  refresh job (hourly)
                                                        |
                                             vectorized-backtester engine
                                                        |
                                                  in-memory store
                                                        |
portfolio site (server-side)  <--(ClusterIP)--  GET /results, GET /health
```

- One refresh at startup, then every hour, on the last 30 days of `BTCUSDT` 1h.
- The latest result lives **in memory only**. No database, no credentials:
  nothing to leak, nothing to back up. A restart recomputes it.
- A failed refresh (pipeline down, gap in the data) keeps the previous result
  and marks it `stale` once it is older than two refresh periods.

## API

Only two routes; FastAPI's `/docs` and `/openapi.json` are disabled.

### `GET /results`

`503` until the first successful refresh, then:

```json
{
  "disclaimer": "Simulated backtest of a demo SMA crossover, shown as an engineering demo. Not a trading signal, a recommendation, or a record of real performance.",
  "computed_at": "2026-09-29T20:00:03+00:00",
  "stale": false,
  "strategy": {"name": "sma_crossover", "fast": 10, "slow": 30},
  "data": {"symbol": "BTCUSDT", "timeframe": "1h", "start": "...", "end": "...", "bars": 720},
  "metrics": {
    "total_return": 0.0132,
    "sharpe_ratio": 0.84,
    "max_drawdown": -0.047,
    "profit_factor": 1.12,
    "position_changes": 23
  },
  "equity": [{"timestamp": "...", "equity": 1.0}]
}
```

Metrics are net of transaction costs (engine defaults). A metric that is not
finite (e.g. profit factor with no losing bar) is `null`. The current position
is deliberately not exposed.

### `GET /health`

Always `200` (liveness: a pipeline outage should not get the pod restarted).
Freshness is in the body: `has_result`, `stale`, `computed_at`,
`last_attempt_at`, `last_attempt_ok`.

## Configuration

Environment variables, all optional:

| Variable | Default |
|---|---|
| `PIPELINE_URL` | `http://api.pipeline.svc.cluster.local:8000` |
| `SYMBOL` | `BTCUSDT` |
| `TIMEFRAME` | `1h` |
| `LOOKBACK_DAYS` | `30` |
| `SMA_FAST` / `SMA_SLOW` | `10` / `30` |
| `REFRESH_INTERVAL_SECONDS` | `3600` |
| `REQUEST_TIMEOUT_SECONDS` | `10` |
| `LOG_LEVEL` | `INFO` |

## Run locally

Python 3.11+, with a pipeline API reachable locally:

```bash
pip install -r requirements.txt
PIPELINE_URL=http://localhost:8000 uvicorn app.main:app --port 8001
curl localhost:8001/results
```

Tests (the pipeline API is mocked, no network needed):

```bash
pytest
```

## Deployment

CI runs the tests, then builds the image and pushes it to
`ghcr.io/yanisnourry/backtester-service` (tags `latest` and commit sha). It is
deployed on k3s from a separate `infra` repository, pinned by sha, as a single
replica behind a `ClusterIP` Service: never exposed to the internet, only
called server-side by the portfolio site. The image runs as a non-root user and
supports a read-only root filesystem.

## Known limitations

- **Gaps fail the refresh.** The engine's `DataLoader` refuses a series with a
  missing candle rather than patching it. A hole in the pipeline's data inside
  the lookback window means failed refreshes and a `stale` result until the
  pipeline backfills it.
- **Single replica by design.** State is in memory; two replicas would serve
  two different results.

Design decisions and trade-offs: [`docs/architecture.md`](docs/architecture.md).
