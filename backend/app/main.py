"""
Tinovi Tipovi API.

A background thread rebuilds the snapshot every REFRESH_HOURS; requests are
served from memory, so they are instant and the data source is never hammered.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from . import config
from .data import CACHE_DIR, load_all
from .engine import backtest, build_predictions, summarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tipovi")

_state: dict = {"snapshot": None, "perf": None, "history": None, "error": None, "building": False}
PERF_FILE = os.path.join(CACHE_DIR, "performance.json")
BACKTEST_EVERY_HOURS = float(os.getenv("BACKTEST_EVERY_HOURS", "24"))
_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_loop, daemon=True, name="refresher").start()
    yield


app = FastAPI(title="Tinovi Tipovi API", version="2.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "*").split(",") if o.strip()],
    allow_methods=["GET"],
)


RETRY_AFTER_FAILURE_SECONDS = 300


def _load_perf() -> tuple[dict | None, list[dict] | None]:
    try:
        with open(PERF_FILE) as f:
            saved = json.load(f)
        return saved["perf"], saved["history"]
    except (OSError, ValueError, KeyError, TypeError):
        return None, None


def _save_perf(perf: dict, history: list[dict]) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(PERF_FILE, "w") as f:
            json.dump({"perf": perf, "history": history}, f)
    except OSError:
        pass


def _perf_age_hours(perf: dict | None) -> float:
    if not perf or "computed_at" not in perf:
        return float("inf")
    then = datetime.fromisoformat(perf["computed_at"])
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def _refresh() -> bool:
    """
    Rebuild in two steps so the site is usable quickly after a cold start:
    1. predictions (seconds) are published straight away,
    2. the backtest (slower) runs only when the last one is over a day old,
       then the predictions are rebuilt with the newly tuned blend weight.
    Returns True on success.
    """
    with _lock:
        if _state["building"]:
            return False
        _state["building"] = True
    try:
        history, last_season, fixtures = load_all()
        perf, past = (_state["perf"], _state["history"]) if _state["perf"] else _load_perf()
        _state.update(
            snapshot=build_predictions(history, last_season, fixtures, perf),
            perf=perf,
            history=past,
            error=None,
        )
        if _perf_age_hours(perf) >= BACKTEST_EVERY_HOURS:
            perf, past = backtest(history, last_season)
            _save_perf(perf, past)
            _state.update(
                perf=perf,
                history=past,
                snapshot=build_predictions(history, last_season, fixtures, perf),
            )
        return True
    except Exception as exc:  # keep serving the previous snapshot
        log.exception("Snapshot build failed")
        _state["error"] = f"{type(exc).__name__}: {exc}"
        return False
    finally:
        _state["building"] = False


def _loop() -> None:
    while True:
        ok = _refresh()
        # After a failure, try again in a few minutes instead of waiting hours.
        time.sleep(config.REFRESH_HOURS * 3600 if ok else RETRY_AFTER_FAILURE_SECONDS)


@app.get("/")
def root():
    return {"name": "Tinovi Tipovi API", "endpoints": ["/api/snapshot", "/api/history", "/api/health"]}


@app.get("/api/health")
def health():
    snap = _state["snapshot"]
    return {
        "ok": True,
        "ready": snap is not None,
        "building": _state["building"],
        "updated_at": snap["updated_at"] if snap else None,
        "backtest_at": (_state["perf"] or {}).get("computed_at"),
        "last_error": _state["error"],
    }


@app.get("/api/snapshot")
def snapshot():
    snap = _state["snapshot"]
    if snap is None:
        # First build after a cold start takes a little while.
        return JSONResponse(
            {
                "status": "warming_up" if _state["building"] or not _state["error"] else "failed",
                "message": "Serverot se zagreva, probaj za momentot.",
                "error": _state["error"],
            },
            status_code=503,
            headers={"Retry-After": "10"},
        )
    return JSONResponse(snap, headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/history")
def history(
    category: str = Query("all", pattern="^(all|safe|value|goals)$"),
    league: str | None = None,
    result: str = Query("all", pattern="^(all|won|lost)$"),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Past tips with their results, newest first, plus the record for the filter."""
    past = _state["history"]
    if past is None:
        # The replay runs after the tips are published; it takes a minute or two.
        return {"status": "pending"}

    items = [t for t in past if category == "all" or t["category"] == category]
    if league:
        items = [t for t in items if t["league"] == league]
    summary = summarize(items)
    if result != "all":
        items = [t for t in items if t["won"] == (result == "won")]

    perf = _state["perf"] or {}
    leagues = sorted(
        {(t["league"], t["league_name"], t["country"]) for t in past},
        key=lambda x: (x[2], x[1]),
    )
    return JSONResponse(
        {
            "status": "ok",
            "from": perf.get("from"),
            "to": perf.get("to"),
            "computed_at": perf.get("computed_at"),
            "summary": summary,
            "total": len(items),
            "items": items[offset : offset + limit],
            "leagues": [{"code": c, "name": n, "country": k} for c, n, k in leagues],
        },
        headers={"Cache-Control": "public, max-age=300"},
    )
