"""Generates fake football-data.co.uk CSVs from known team strengths, for tests."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import numpy as np

# Real header of a 2026/27 football-data.co.uk results file.
HEADER = (
    "Div Date Time HomeTeam AwayTeam FTHG FTAG FTR HTHG HTAG HTR Referee HxG AxG HS AS HST AST HF AF HC AC HY AY HR AR "
    "B365H B365D B365A BFDH BFDD BFDA BVH BVD BVA BWH BWD BWA PPH PPD PPA SKBH SKBD SKBA MaxH MaxD MaxA AvgH AvgD AvgA "
    "BFEH BFED BFEA B365>2.5 B365<2.5 Max>2.5 Max<2.5 Avg>2.5 Avg<2.5 BFE>2.5 BFE<2.5 AHh B365AHH B365AHA MaxAHH MaxAHA "
    "AvgAHH AvgAHA BFEAHH BFEAHA B365CH B365CD B365CA BFDCH BFDCD BFDCA BVCH BVCD BVCA BWCH BWCD BWCA PPCH PPCD PPCA "
    "SKBCH SKBCD SKBCA MaxCH MaxCD MaxCA AvgCH AvgCD AvgCA BFECH BFECD BFECA B365C>2.5 B365C<2.5 MaxC>2.5 MaxC<2.5 "
    "AvgC>2.5 AvgC<2.5 BFEC>2.5 BFEC<2.5 AHCh B365CAHH B365CAHA MaxCAHH MaxCAHA AvgCAHH AvgCAHA BFECAHH BFECAHA"
).split()

HOME_ADV, BASE = 0.25, 0.15


class League:
    def __init__(self, code: str, n_teams: int = 20, seed: int = 1, with_xg: bool = True):
        self.code, self.with_xg = code, with_xg
        self.rng = np.random.default_rng(seed)
        self.teams = [f"{code} Team {i:02d}" for i in range(n_teams + 3)]
        self.attack = dict(zip(self.teams, self.rng.normal(0, 0.3, len(self.teams))))
        self.defence = dict(zip(self.teams, self.rng.normal(0, 0.3, len(self.teams))))
        # last season: teams 0..n-1 ; this season: three of them replaced by promoted teams
        self.prev_teams = self.teams[:n_teams]
        self.cur_teams = self.teams[3:]

    def rates(self, h, a):
        lam = np.exp(BASE + HOME_ADV + self.attack[h] - self.defence[a])
        mu = np.exp(BASE + self.attack[a] - self.defence[h])
        return lam, mu

    def true_probs(self, h, a):
        lam, mu = self.rates(h, a)
        g = np.arange(11)
        from scipy.stats import poisson

        grid = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
        tot = g[:, None] + g[None, :]
        return (
            np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum(),
            grid[tot >= 3].sum(), grid[tot <= 2].sum(),
        )

    def _odds(self, probs, margin, noise):
        p = np.array(probs) * np.exp(self.rng.normal(0, noise, len(probs)))
        p = p / p.sum() * (1 + margin)
        return [round(1 / x, 2) for x in p]

    def row(self, d: date, h: str, a: str, played: bool) -> dict:
        ph, pd, pa, po, pu = self.true_probs(h, a)
        r = {k: "" for k in HEADER}
        r.update(Div=self.code, Date=d.strftime("%d/%m/%Y"), Time="15:00", HomeTeam=h, AwayTeam=a)
        avg = self._odds([ph, pd, pa], 0.06, 0.08)
        bfe = self._odds([ph, pd, pa], 0.01, 0.08)
        mx = [round(o * 1.04, 2) for o in avg]
        avg_ou = self._odds([po, pu], 0.06, 0.06)
        bfe_ou = self._odds([po, pu], 0.01, 0.06)
        r.update(zip(["AvgH", "AvgD", "AvgA"], map(str, avg)))
        r.update(zip(["BFEH", "BFED", "BFEA"], map(str, bfe)))
        r.update(zip(["MaxH", "MaxD", "MaxA"], map(str, mx)))
        r.update(zip(["Avg>2.5", "Avg<2.5"], map(str, avg_ou)))
        r.update(zip(["BFE>2.5", "BFE<2.5"], map(str, bfe_ou)))
        r.update(zip(["Max>2.5", "Max<2.5"], map(str, [round(o * 1.04, 2) for o in avg_ou])))
        if played:
            lam, mu = self.rates(h, a)
            hg, ag = self.rng.poisson(lam), self.rng.poisson(mu)
            r.update(FTHG=str(hg), FTAG=str(ag), FTR="H" if hg > ag else "D" if hg == ag else "A")
            if self.with_xg:
                r.update(HxG=f"{lam * self.rng.gamma(8, 1 / 8):.2f}", AxG=f"{mu * self.rng.gamma(8, 1 / 8):.2f}")
        return r

    def season(self, teams, start: date, rounds: int | None = None) -> list[tuple[date, str, str]]:
        """Double round robin, one round per week."""
        n = len(teams)
        order = list(teams)
        fixtures = []
        for rnd in range(2 * (n - 1)):
            d = start + timedelta(days=7 * rnd)
            for i in range(n // 2):
                h, a = order[i], order[n - 1 - i]
                if rnd >= n - 1:
                    h, a = a, h
                fixtures.append((d, h, a))
            order = [order[0]] + [order[-1]] + order[1:-1]
        if rounds is not None:
            fixtures = [f for f in fixtures if (f[0] - start).days // 7 < rounds]
        return fixtures


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADER)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def build_files(leagues: list[League], today: date) -> dict[str, str]:
    """Returns {path: csv_text} for prev season, current season and fixtures.csv."""
    files, fixture_rows = {}, []
    for lg in leagues:
        prev = lg.season(lg.prev_teams, date(2025, 8, 16))
        files[f"mmz4281/2526/{lg.code}.csv"] = to_csv([lg.row(d, h, a, True) for d, h, a in prev])
        cur = lg.season(lg.cur_teams, date(2026, 8, 22))
        played = [f for f in cur if f[0] < today]
        upcoming = [f for f in cur if today <= f[0] < today + timedelta(days=8)]
        files[f"mmz4281/2627/{lg.code}.csv"] = to_csv([lg.row(d, h, a, True) for d, h, a in played])
        fixture_rows += [lg.row(d, h, a, False) for d, h, a in upcoming]
    files["fixtures.csv"] = to_csv(fixture_rows)
    return files
