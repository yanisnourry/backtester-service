# Backtester Service

A small, stateless FastAPI service that keeps a backtest **live**: every hour it
pulls fresh OHLCV from the market data pipeline's REST API, re-runs the
vectorized backtester engine on it, and serves the latest result.

> **Engineering demo, not a trading signal.** The result is a simulation of a
> plain SMA crossover used to exercise the engine end to end. It is not a
> recommendation, a forecast, or a record of real performance.

## Status

Work in progress — repository skeleton only.

## Scope

- `GET /health` — liveness / freshness of the last refresh
- `GET /results` — latest backtest result, with an explicit simulation disclaimer
- No database, no credentials: the last result lives in memory and is
  overwritten on each refresh
- Internal only (Kubernetes `ClusterIP`); the portfolio site calls it server-side

## Depends on

- [market-data-pipeline](https://github.com/yanisnourry/market-data-pipeline) — OHLCV source, over its REST API
- [vectorized-backtester](https://github.com/yanisnourry/vectorized-backtester) — engine and SMA crossover strategy, reused as-is

See [`docs/architecture.md`](docs/architecture.md) for the design decisions.
