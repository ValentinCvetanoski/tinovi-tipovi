"""Turns bookmaker odds into probabilities and blends them with the model."""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from .data import Match


def devig(odds: tuple[float, ...]) -> list[float] | None:
    """
    Remove the bookmaker margin with the power method: find k so that
    sum((1/odds)^k) = 1. Unlike simple normalising, this takes more margin off
    long shots, which is where bookmakers hide most of it.
    """
    inv = np.array([1 / o for o in odds if o and o > 1])
    if len(inv) != len(odds):
        return None
    total = inv.sum()
    if abs(total - 1) < 1e-9:
        return inv.tolist()
    try:
        k = brentq(lambda k: np.sum(inv**k) - 1, 0.5, 3.0)
    except ValueError:
        return (inv / total).tolist()
    return (inv**k).tolist()


def market_probs(m: Match) -> dict | None:
    """Average of the margin-free Betfair Exchange and market-average prices."""
    out: dict[str, float] = {}
    three_way = [p for src in ("bfe", "avg") if src in m.odds and (p := devig(m.odds[src]))]
    if three_way:
        h, d, a = np.mean(three_way, axis=0)
        out.update(home=float(h), draw=float(d), away=float(a))
    two_way = [p for src in ("bfe", "avg") if src in m.ou and (p := devig(m.ou[src]))]
    if two_way:
        o, u = np.mean(two_way, axis=0)
        out.update(over25=float(o), under25=float(u))
    return out or None


def _pool(model: list[float], market: list[float], w: float) -> list[float]:
    """Logarithmic pooling: p ~ model^w * market^(1-w)."""
    mo = np.clip(np.array(model), 1e-6, 1)
    mk = np.clip(np.array(market), 1e-6, 1)
    p = mo**w * mk ** (1 - w)
    return (p / p.sum()).tolist()


def blend(model: dict | None, market: dict | None, w: float) -> dict | None:
    """Combine model and market. w = how much weight the model gets (0..1)."""
    if model is None and market is None:
        return None
    if model is None:
        return dict(market)
    out = {k: model[k] for k in ("home", "draw", "away", "over25", "under25", "btts")}
    if market and "home" in market:
        out["home"], out["draw"], out["away"] = _pool(
            [model["home"], model["draw"], model["away"]],
            [market["home"], market["draw"], market["away"]],
            w,
        )
    if market and "over25" in market:
        out["over25"], out["under25"] = _pool(
            [model["over25"], model["under25"]], [market["over25"], market["under25"]], w
        )
    return out
