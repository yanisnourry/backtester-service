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
