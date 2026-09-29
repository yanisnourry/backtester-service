# Architecture & technical decisions

## Scope

Glue service. It adds no quant logic: it wires the market data pipeline
(source) to the vectorized backtester engine (computation) and exposes the
latest result over HTTP. The only strategy is the engine's SMA crossover.

## Decision — stateless FastAPI, result in memory

**Chosen:** a single FastAPI process holding the latest backtest result in
memory, refreshed hourly by an internal job.

| | Stateless FastAPI (chosen) | Django + persisted runs |
|---|---|---|
| State | last result only, lost on restart (recomputed at startup) | full run history in a DB |
| Secrets | none | DB credentials |
| Attack surface | two read-only routes, `ClusterIP` only | ORM, admin, DB |
| Fits | "show an up-to-date backtest" | "browse past runs" — not a current need |

The service is called by a public site; keeping it credential-free and
data-free means there is nothing to leak if the pod is compromised or
restarted. A run history would be a deliberate, documented evolution.

## Data flow

```
market-data-pipeline API  --(HTTP, cluster DNS)-->  refresh job
                                                        |
                                             vectorized-backtester engine
                                                        |
                                                  in-memory store
                                                        |
portfolio site (server-side)  <--(ClusterIP)--  GET /results, GET /health
```

The pipeline is reached through its REST API, never its database — same loose
coupling as the backtester itself.

## Decision — consuming `vectorized-backtester`

**Chosen:** a pip dependency on the engine's GitHub archive, pinned to a commit
sha in `requirements.txt` (the engine ships a `pyproject.toml`).

| | Pinned dependency (chosen) | Vendoring |
|---|---|---|
| Source of truth | one — the engine repo | two copies drifting apart |
| Reproducibility | sha-pinned, same bytes every build | same, but by copy |
| Upgrade | bump the sha, deliberate | re-copy, easy to forget a file |

The archive URL (`.../archive/<sha>.tar.gz`) is used rather than `git+https`
so the `python:3.11-slim` image builds without installing `git`. Plotting is an
optional extra (`[plot]`) of the engine, not installed here: the service never
draws, so the image carries no matplotlib.

## Refresh and failure behavior

- **Schedule**: one refresh at startup, then every `REFRESH_INTERVAL_SECONDS`
  (default 3600). A plain `asyncio` task: no scheduler dependency for one job.
- **Window**: the last `LOOKBACK_DAYS` (default 30) of `SYMBOL`/`TIMEFRAME`
  (default `BTCUSDT`/`1h`), SMA `10/30`. The engine's `DataLoader` is
  synchronous, so it runs in a worker thread (`asyncio.to_thread`) instead of
  being rewritten on top of an async client.
- **Failure**: a refresh that raises (pipeline down, hole in the series, too
  few candles) is logged and recorded; the previous result stays served. The
  `DataLoader` refuses a series with a gap rather than patching it, so a hole
  in the pipeline's data inside the window shows up here as failed refreshes.
- **Staleness**: `stale: true` once the last good result is older than two
  refresh periods, on both `/results` and `/health`.
- **Atomic swaps**: the store holds one immutable snapshot (result + timestamps)
  replaced under a lock, so a reader never pairs a result with another run's
  timestamp.

## API surface

| Route | Behavior |
|---|---|
| `GET /results` | `503` until the first successful refresh; then the latest result, a `disclaimer` field and `stale` |
| `GET /health` | always `200` (liveness): a pipeline outage must not get the pod restarted in a loop; freshness is reported in the body |

FastAPI's `/docs`, `/redoc` and `/openapi.json` are disabled. The result
exposes metrics and the equity curve, never the current position: that is the
one field a reader could take for a live signal.
