"""
Dixon-Coles football model.

Each team gets an attack and a defence rating. Expected goals for a match are
    home: exp(c + home_adv + attack[home] - defence[away])
    away: exp(c + attack[away] - defence[home])
Recent matches count more (exponential time decay), the target mixes real goals
with expected goals (xG) when available, and a small ridge penalty keeps teams
with little data close to average. Dixon-Coles' rho corrects the low scores
(0-0, 1-0, 0-1, 1-1) that a plain Poisson model gets wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson

from . import config
from .data import Match

MIN_MATCHES = 40


@dataclass
class Ratings:
    index: dict[str, int]
    attack: np.ndarray
    defence: np.ndarray
    home_adv: float
    intercept: float
    rho: float
    games: dict[str, int]

    def knows(self, team: str) -> bool:
        return team in self.index

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        h, a = self.index[home], self.index[away]
        lam = np.exp(self.intercept + self.home_adv + self.attack[h] - self.defence[a])
        mu = np.exp(self.intercept + self.attack[a] - self.defence[h])
        return float(lam), float(mu)

    def predict(self, home: str, away: str) -> dict | None:
        if not (self.knows(home) and self.knows(away)):
            return None
        lam, mu = self.expected_goals(home, away)
        return score_probabilities(lam, mu, self.rho)


def _tau(hg, ag, lam, mu, rho):
    """Dixon-Coles low-score correction factor."""
    t = np.ones_like(lam, dtype=float)
    t = np.where((hg == 0) & (ag == 0), 1 - lam * mu * rho, t)
    t = np.where((hg == 0) & (ag == 1), 1 + lam * rho, t)
    t = np.where((hg == 1) & (ag == 0), 1 + mu * rho, t)
    t = np.where((hg == 1) & (ag == 1), 1 - rho, t)
    return np.clip(t, 1e-10, None)


def score_probabilities(lam: float, mu: float, rho: float) -> dict:
    n = config.MAX_GOALS + 1
    goals = np.arange(n)
    grid = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
    hg, ag = np.meshgrid(goals, goals, indexing="ij")
    grid = grid * _tau(hg, ag, np.full_like(grid, lam), np.full_like(grid, mu), rho)
    grid /= grid.sum()

    flat = np.argsort(grid, axis=None)[::-1][:3]
    top = [
        {"score": f"{i}-{j}", "p": round(float(grid[i, j]), 4)}
        for i, j in (np.unravel_index(k, grid.shape) for k in flat)
    ]
    total = hg + ag
    return {
        "home": float(np.tril(grid, -1).sum()),
        "draw": float(np.trace(grid)),
        "away": float(np.triu(grid, 1).sum()),
        "over25": float(grid[total >= 3].sum()),
        "under25": float(grid[total <= 2].sum()),
        "btts": float(grid[1:, 1:].sum()),
        "xg_home": round(lam, 2),
        "xg_away": round(mu, 2),
        "top_scores": top,
    }


def fit(matches: list[Match], as_of: datetime, last_season_teams: set[str]) -> Ratings | None:
    train = [m for m in matches if m.played and m.kickoff < as_of]
    if len(train) < MIN_MATCHES:
        return None

    teams = sorted({t for m in train for t in (m.home, m.away)})
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([index[m.home] for m in train])
    ai = np.array([index[m.away] for m in train])
    hg = np.array([m.hg for m in train], dtype=float)
    ag = np.array([m.ag for m in train], dtype=float)

    # Training target: blend of xG and goals where xG exists.
    s = config.XG_SHARE
    yh = np.array([s * m.hxg + (1 - s) * m.hg if m.hxg is not None and m.axg is not None else m.hg for m in train], dtype=float)
    ya = np.array([s * m.axg + (1 - s) * m.ag if m.hxg is not None and m.axg is not None else m.ag for m in train], dtype=float)

    days_ago = np.array([(as_of - m.kickoff).total_seconds() / 86400 for m in train])
    w = np.exp(-config.DECAY * days_ago)

    # Promoted teams (not in this league last season) start below average.
    prior = np.zeros(n)
    if last_season_teams:
        for t, i in index.items():
            if t not in last_season_teams:
                prior[i] = config.PROMOTED_PRIOR
    ridge = config.RIDGE

    def nll(theta):
        a, d, h, c = theta[:n], theta[n : 2 * n], theta[2 * n], theta[2 * n + 1]
        log_lam = c + h + a[hi] - d[ai]
        log_mu = c + a[ai] - d[hi]
        lam, mu = np.exp(log_lam), np.exp(log_mu)
        value = -np.sum(w * (yh * log_lam - lam + ya * log_mu - mu))
        value += 0.5 * ridge * (np.sum((a - prior) ** 2) + np.sum((d - prior) ** 2))

        g_lam = -w * (yh - lam)
        g_mu = -w * (ya - mu)
        ga = np.zeros(n)
        gd = np.zeros(n)
        np.add.at(ga, hi, g_lam)
        np.add.at(ga, ai, g_mu)
        np.add.at(gd, ai, -g_lam)
        np.add.at(gd, hi, -g_mu)
        ga += ridge * (a - prior)
        gd += ridge * (d - prior)
        grad = np.concatenate([ga, gd, [g_lam.sum(), g_lam.sum() + g_mu.sum()]])
        return value, grad

    x0 = np.concatenate([prior, prior, [0.25, np.log(max(ya.mean(), 0.5))]])
    res = minimize(nll, x0, jac=True, method="L-BFGS-B")
    theta = res.x
    a, d, h, c = theta[:n], theta[n : 2 * n], theta[2 * n], theta[2 * n + 1]

    lam = np.exp(c + h + a[hi] - d[ai])
    mu = np.exp(c + a[ai] - d[hi])
    rho_res = minimize_scalar(
        lambda r: -np.sum(w * np.log(_tau(hg, ag, lam, mu, r))),
        bounds=(-0.25, 0.25),
        method="bounded",
    )

    games: dict[str, int] = {}
    for m in train:
        games[m.home] = games.get(m.home, 0) + 1
        games[m.away] = games.get(m.away, 0) + 1

    return Ratings(index, a, d, float(h), float(c), float(rho_res.x), games)
