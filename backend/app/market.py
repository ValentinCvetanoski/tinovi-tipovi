"""Turns bookmaker odds into probabilities and blends them with the model."""

from __future__ import annotations

import math

from .data import Match


def devig(odds: tuple[float, ...]) -> list[float] | None:
    """
    Remove the bookmaker margin with the power method: find k so that
    sum((1/odds)^k) = 1. Unlike simple normalising, this takes more margin off
    long shots, which is where bookmakers hide most of it.
    """
    if any(not o or o <= 1 for o in odds):
        return None
    inv = [1 / o for o in odds]
    logs = [math.log(x) for x in inv]
    k = 1.0
    for _ in range(30):  # Newton's method; converges in a handful of steps
        powered = [x**k for x in inv]
        f = sum(powered) - 1
        if abs(f) < 1e-12:
            break
        k -= f / sum(p * lg for p, lg in zip(powered, logs))
        if not 0.2 < k < 5:  # odd odds: fall back to plain normalising
            total = sum(inv)
            return [x / total for x in inv]
    return [x**k for x in inv]


def market_probs(m: Match) -> dict | None:
    """Average of the margin-free Betfair Exchange and market-average prices."""
    out: dict[str, float] = {}
    three_way = [p for src in ("bfe", "avg") if src in m.odds and (p := devig(m.odds[src]))]
    if three_way:
        h, d, a = (sum(col) / len(three_way) for col in zip(*three_way))
        out.update(home=h, draw=d, away=a)
    two_way = [p for src in ("bfe", "avg") if src in m.ou and (p := devig(m.ou[src]))]
    if two_way:
        o, u = (sum(col) / len(two_way) for col in zip(*two_way))
        out.update(over25=o, under25=u)
    return out or None


def _pool(model: list[float], market: list[float], w: float) -> list[float]:
    """Logarithmic pooling: p ~ model^w * market^(1-w)."""
    p = [max(a, 1e-6) ** w * max(b, 1e-6) ** (1 - w) for a, b in zip(model, market)]
    total = sum(p)
    return [x / total for x in p]


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
