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
