"""
Tinovi Tipovi API.

A background thread rebuilds the snapshot every REFRESH_HOURS; requests are
served from memory, so they are instant and the data source is never hammered.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from . import config
from .engine import build_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tipovi")

_state: dict = {"snapshot": None, "error": None, "building": False}
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


def _refresh() -> bool:
    """Rebuild the snapshot. Returns True on success."""
    with _lock:
        if _state["building"]:
            return False
        _state["building"] = True
    try:
        snapshot = build_snapshot()
        _state.update(snapshot=snapshot, error=None)
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
    return {"name": "Tinovi Tipovi API", "endpoints": ["/api/snapshot", "/api/health"]}


@app.get("/api/health")
def health():
    snap = _state["snapshot"]
    return {
        "ok": True,
        "ready": snap is not None,
        "building": _state["building"],
        "updated_at": snap["updated_at"] if snap else None,
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
