"""Builds the full snapshot served by the API: predictions, tips and backtest."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config
from .data import Match, load_all
from .market import blend, market_probs
from .model import Ratings, fit

log = logging.getLogger(__name__)

# Balkan betting-slip codes: 1 / X / 2, 3+ (over 2.5), 0-2 (under 2.5), GG / NG.
PICKS = [
    ("1", "home", "1x2"),
    ("X", "draw", "1x2"),
    ("2", "away", "1x2"),
    ("3+", "over25", "goals"),
    ("0-2", "under25", "goals"),
    ("GG", "btts", "goals"),
    ("NG", "no_btts", "goals"),
]
ODDS_KEY = {"home": 0, "draw": 1, "away": 2}
OU_KEY = {"over25": 0, "under25": 1}
BLEND_GRID = [i / 10 for i in range(11)]
DEFAULT_BLEND = 0.35
REFIT_EVERY_DAYS = 21


# ---------- helpers ----------


def _price(m: Match, key: str, source: str) -> float | None:
    if key in ODDS_KEY and source in m.odds:
        return m.odds[source][ODDS_KEY[key]]
    if key in OU_KEY and source in m.ou:
        return m.ou[source][OU_KEY[key]]
    return None


def _won(m: Match, key: str) -> bool:
    total = m.hg + m.ag
    return {
        "home": m.hg > m.ag,
        "draw": m.hg == m.ag,
        "away": m.hg < m.ag,
        "over25": total >= 3,
        "under25": total <= 2,
        "btts": m.hg > 0 and m.ag > 0,
        "no_btts": m.hg == 0 or m.ag == 0,
    }[key]


def candidates(m: Match, probs: dict) -> list[dict]:
    """Every possible pick for one match, with probability, odds and value."""
    out = []
    p_all = dict(probs, no_btts=1 - probs["btts"]) if "btts" in probs else dict(probs)
    for code, key, kind in PICKS:
        p = p_all.get(key)
        if p is None:
            continue
        best, avg = _price(m, key, "max"), _price(m, key, "avg")
        out.append({
            "pick": code,
            "key": key,
            "kind": kind,
            "p": p,
            "odds": best,
            "avg_odds": avg,
            "fair_odds": 1 / p if p > 0 else None,
            "ev": p * best - 1 if best else None,
        })
    return out


def select_tips(rows: list[tuple[Match, list[dict]]], limit: int | None = None) -> dict[str, list[tuple[Match, dict]]]:
    """Apply the tip rules. At most one tip per match in each category."""
    safe, value, goals = [], [], []
    for m, cands in rows:
        s = [
            c for c in cands
            if c["kind"] == "1x2" and c["p"] >= config.SAFE_MIN_PROB
            and c["odds"] and c["odds"] >= config.MIN_ODDS
        ]
        if s:
            safe.append((m, max(s, key=lambda c: c["p"])))

        v = [
            c for c in cands
            if c["ev"] is not None
            and c["ev"] >= config.VALUE_MIN_EV
            and c["p"] >= config.VALUE_MIN_PROB
            and c["odds"] <= config.VALUE_MAX_ODDS
        ]
        if v:
            value.append((m, max(v, key=lambda c: c["ev"])))

        g = [
            c for c in cands
            if c["key"] in OU_KEY and c["p"] >= config.GOALS_MIN_PROB
            and c["odds"] and c["odds"] >= config.MIN_ODDS
        ]
        if g:
            goals.append((m, max(g, key=lambda c: c["p"])))

    safe.sort(key=lambda t: t[1]["p"], reverse=True)
    value.sort(key=lambda t: t[1]["ev"], reverse=True)
    goals.sort(key=lambda t: t[1]["p"], reverse=True)
    return {"safe": safe[:limit], "value": value[:limit], "goals": goals[:limit]}


def _logloss(p: float) -> float:
    return -math.log(max(p, 1e-9))


# ---------- backtest ----------


def backtest(history: dict[str, list[Match]], last_season: dict[str, set[str]]) -> dict:
    """
    Walk forward over the last BACKTEST_DAYS: refit the model every few weeks
    using only matches played before, then score its predictions against what
    actually happened. This is how we know whether the model helps at all.
    """
    started = time.time()
    records = []  # (league, match, model_probs, market_probs)
    for lg, matches in history.items():
        if not matches:
            continue
        end = matches[-1].kickoff
        start = end - timedelta(days=config.BACKTEST_DAYS)
        cut = start
        while cut <= end:
            nxt = cut + timedelta(days=REFIT_EVERY_DAYS)
            ratings = fit(matches, cut, last_season.get(lg, set()))
            if ratings:
                for m in matches:
                    if cut <= m.kickoff < nxt:
                        mp = ratings.predict(m.home, m.away)
                        mk = market_probs(m)
                        if mp and mk and "home" in mk:
                            records.append((lg, m, mp, mk))
            cut = nxt

    computed_at = datetime.now(timezone.utc).isoformat()
    if not records:
        return {"matches": 0, "blend_weight": DEFAULT_BLEND, "computed_at": computed_at}

    def outcome_p(probs, m):
        return probs["home"] if m.hg > m.ag else probs["draw"] if m.hg == m.ag else probs["away"]

    # Pick the blend weight that would have predicted these matches best.
    losses = {}
    for w in BLEND_GRID:
        losses[w] = np.mean([_logloss(outcome_p(blend(mp, mk, w), m)) for _, m, mp, mk in records])
    best_w = min(losses, key=losses.get)
    log.info("Backtest: %d matches, blend weight %.1f, %.1fs", len(records), best_w, time.time() - started)

    def metrics(recs, getter):
        ll, brier, hits = [], [], []
        for _, m, mp, mk in recs:
            p = getter(mp, mk)
            actual = [m.hg > m.ag, m.hg == m.ag, m.hg < m.ag]
            vec = [p["home"], p["draw"], p["away"]]
            ll.append(_logloss(outcome_p(p, m)))
            brier.append(sum((v - a) ** 2 for v, a in zip(vec, actual)))
            hits.append(int(np.argmax(vec)) == actual.index(True))
        return {
            "log_loss": round(float(np.mean(ll)), 4),
            "brier": round(float(np.mean(brier)), 4),
            "accuracy": round(float(np.mean(hits)), 4),
        }

    sources = {
        "model": lambda mp, mk: mp,
        "market": lambda mp, mk: mk,
        "blend": lambda mp, mk: blend(mp, mk, best_w),
    }
    overall = {name: metrics(records, g) for name, g in sources.items()}

    per_league = []
    for lg in sorted({r[0] for r in records}):
        recs = [r for r in records if r[0] == lg]
        country, name = config.LEAGUES[lg]
        per_league.append({
            "code": lg, "country": country, "name": name, "matches": len(recs),
            **{k: metrics(recs, g) for k, g in sources.items()},
        })

    # How would the tip rules have done?
    rows = [(m, candidates(m, blend(mp, mk, best_w))) for _, m, mp, mk in records]
    tip_stats = {}
    for cat, bets in select_tips(rows).items():
        won = [_won(m, c["key"]) for m, c in bets]
        best = [(c["odds"], _won(m, c["key"])) for m, c in bets if c["odds"]]
        avg = [(c["avg_odds"], _won(m, c["key"])) for m, c in bets if c["avg_odds"]]
        tip_stats[cat] = {
            "tips": len(bets),
            "hit_rate": _r(np.mean(won)) if won else None,
            "avg_odds": _r(np.mean([o for o, _ in best]), 2) if best else None,
            # Profit per 1 unit staked. "best" assumes you always find the top price.
            "roi_avg_odds": _r(np.mean([o * hit - 1 for o, hit in avg])) if avg else None,
            "roi_best_odds": _r(np.mean([o * hit - 1 for o, hit in best])) if best else None,
        }

    dates = [m.kickoff for _, m, _, _ in records]
    return {
        "computed_at": computed_at,
        "matches": len(records),
        "from": min(dates).isoformat(),
        "to": max(dates).isoformat(),
        "blend_weight": best_w,
        "blend_curve": [{"w": w, "log_loss": round(float(v), 4)} for w, v in losses.items()],
        "overall": overall,
        "leagues": per_league,
        "tips": tip_stats,
    }


# ---------- predictions ----------


def _form(history: list[Match], team: str, before: datetime, n: int = 5) -> list[str]:
    out = []
    for m in reversed(history):
        if m.kickoff >= before or team not in (m.home, m.away):
            continue
        gf, ga = (m.hg, m.ag) if m.home == team else (m.ag, m.hg)
        out.append("W" if gf > ga else "D" if gf == ga else "L")
        if len(out) == n:
            break
    return out[::-1]


def _r(x: float | None, nd: int = 4):
    return None if x is None else round(float(x), nd)


def _tip_json(m: Match, c: dict) -> dict:
    country, name = config.LEAGUES[m.league]
    return {
        "match_id": m.id,
        "league": m.league,
        "league_name": name,
        "country": country,
        "kickoff": m.kickoff.isoformat(),
        "home": m.home,
        "away": m.away,
        "pick": c["pick"],
        "p": _r(c["p"]),
        "odds": _r(c["odds"], 2),
        "fair_odds": _r(c["fair_odds"], 2),
        "ev": _r(c["ev"]),
    }


def build_predictions(
    history: dict[str, list[Match]],
    last_season: dict[str, set[str]],
    fixtures: list[Match],
    perf: dict | None,
) -> dict:
    """
    Predictions for upcoming matches. Cheap: only fits the leagues that have
    fixtures. perf is the latest backtest (None while it is still running);
    it supplies the model/market blend weight.
    """
    started = time.time()
    w = perf["blend_weight"] if perf and perf.get("matches") else DEFAULT_BLEND
    now = datetime.now(timezone.utc)

    ratings: dict[str, Ratings | None] = {
        lg: fit(history[lg], now, last_season.get(lg, set())) for lg in {f.league for f in fixtures}
    }

    matches, rows = [], []
    for f in fixtures:
        r = ratings.get(f.league)
        mp = r.predict(f.home, f.away) if r else None
        mk = market_probs(f)
        probs = blend(mp, mk, w)
        if probs is None or "home" not in probs:
            continue
        cands = candidates(f, probs)
        rows.append((f, cands))
        country, name = config.LEAGUES[f.league]
        hist = history.get(f.league, [])
        matches.append({
            "id": f.id,
            "league": f.league,
            "league_name": name,
            "country": country,
            "kickoff": f.kickoff.isoformat(),
            "home": f.home,
            "away": f.away,
            "probs": {k: _r(v) for k, v in probs.items()},
            "model": {k: _r(mp[k]) for k in ("home", "draw", "away", "over25", "btts")} if mp else None,
            "market": {k: _r(v) for k, v in mk.items()} if mk else None,
            "xg": {"home": mp["xg_home"], "away": mp["xg_away"]} if mp else None,
            "top_scores": mp["top_scores"] if mp else [],
            "odds": {c["pick"]: _r(c["odds"], 2) for c in cands if c["odds"]},
            "form": {"home": _form(hist, f.home, f.kickoff), "away": _form(hist, f.away, f.kickoff)},
        })

    tips = {cat: [_tip_json(m, c) for m, c in picked] for cat, picked in select_tips(rows, config.TIPS_LIMIT).items()}
    latest = max((m.kickoff for ms in history.values() for m in ms), default=None)

    leagues = []
    for lg, (country, name) in config.LEAGUES.items():
        count = sum(1 for m in matches if m["league"] == lg)
        if count:
            leagues.append({"code": lg, "country": country, "name": name, "matches": count})

    log.info("Predictions built in %.1fs: %d matches", time.time() - started, len(matches))
    return {
        "status": "ok",
        "updated_at": now.isoformat(),
        "data_through": latest.isoformat() if latest else None,
        "blend_weight": w,
        "leagues": leagues,
        "matches": matches,
        "tips": tips,
        "performance": perf,
    }


def build_snapshot() -> dict:
    """Everything in one go (used by tests and local scripts)."""
    history, last_season, fixtures = load_all()
    perf = backtest(history, last_season)
    return build_predictions(history, last_season, fixtures, perf)
