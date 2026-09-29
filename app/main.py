"""FastAPI app: GET /health, GET /results. Internal (ClusterIP) only."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response

from app.config import Settings
from app.refresh import make_loader, run_periodic
from app.store import ResultStore

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

DISCLAIMER = (
    "Simulated backtest of a demo SMA crossover, shown as an engineering demo. "
    "Not a trading signal, a recommendation, or a record of real performance."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    app.state.settings = settings
    app.state.store = ResultStore()
    task = asyncio.create_task(
        run_periodic(app.state.store, settings, make_loader(settings))
    )
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# No /docs, /redoc or /openapi.json: nothing exposed beyond the two routes.
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health(request: Request):
    # Liveness only: a missing or stale result is reported, not failed on,
    # so a pipeline outage never gets this pod restarted in a loop.
    snap = request.app.state.store.snapshot()
    now = datetime.now(timezone.utc)
    return {
        "status": "ok",
        "has_result": snap.result is not None,
        "stale": snap.is_stale(now, request.app.state.settings.stale_after_seconds),
        "computed_at": _iso(snap.computed_at),
        "last_attempt_at": _iso(snap.last_attempt_at),
        "last_attempt_ok": snap.last_attempt_ok,
    }


@app.get("/results")
async def results(request: Request, response: Response):
    snap = request.app.state.store.snapshot()
    if snap.result is None:
        response.status_code = 503
        return {"detail": "no backtest result yet", "disclaimer": DISCLAIMER}

    now = datetime.now(timezone.utc)
    return {
        "disclaimer": DISCLAIMER,
        "computed_at": _iso(snap.computed_at),
        "stale": snap.is_stale(now, request.app.state.settings.stale_after_seconds),
        **snap.result,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
