"""Downloads and parses the football-data.co.uk CSV files."""

from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from . import config

log = logging.getLogger(__name__)

UK = ZoneInfo("Europe/London")  # kick-off times in the files are UK time
CACHE_DIR = os.path.join(tempfile.gettempdir(), "tipovi-cache")


@dataclass
class Match:
    league: str
    kickoff: datetime  # UTC
    home: str
    away: str
    hg: int | None = None  # full-time goals (None for upcoming matches)
    ag: int | None = None
    hxg: float | None = None  # expected goals, when the file has them
    axg: float | None = None
    # odds[source] = (home, draw, away); ou[source] = (over 2.5, under 2.5)
    odds: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    ou: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.league}-{self.kickoff:%Y%m%d}-{self.home}-{self.away}".replace(" ", "_")

    @property
    def played(self) -> bool:
        return self.hg is not None and self.ag is not None


# Pre-match odds columns. Max = best price across bookmakers, Avg = market
# average, BFE = Betfair Exchange (very low margin, so the sharpest signal here).
ODDS_SOURCES = {"max": "Max", "avg": "Avg", "bfe": "BFE"}


def _num(row: dict, key: str, allow_zero: bool = False) -> float | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value > 0 or (allow_zero and value == 0):
        return value
    return None


def _kickoff(date_s: str, time_s: str) -> datetime | None:
    date_s, time_s = (date_s or "").strip(), (time_s or "").strip() or "15:00"
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            local = datetime.strptime(f"{date_s} {time_s}", fmt).replace(tzinfo=UK)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def parse_csv(text: str, league: str | None = None) -> list[Match]:
    """Parse one football-data CSV. If league is None, use the Div column."""
    matches = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip(): v for k, v in row.items()}
        div = (row.get("Div") or "").strip()
        home, away = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
        kickoff = _kickoff(row.get("Date", ""), row.get("Time", ""))
        if not home or not away or kickoff is None:
            continue
        lg = league or div
        if lg not in config.LEAGUES:
            continue

        hg, ag = _num(row, "FTHG", allow_zero=True), _num(row, "FTAG", allow_zero=True)

        m = Match(
            league=lg,
            kickoff=kickoff,
            home=home,
            away=away,
            hg=int(hg) if hg is not None else None,
            ag=int(ag) if ag is not None else None,
            hxg=_num(row, "HxG", allow_zero=True),
            axg=_num(row, "AxG", allow_zero=True),
        )
        for key, prefix in ODDS_SOURCES.items():
            h, d, a = _num(row, f"{prefix}H"), _num(row, f"{prefix}D"), _num(row, f"{prefix}A")
            if h and d and a:
                m.odds[key] = (h, d, a)
            o, u = _num(row, f"{prefix}>2.5"), _num(row, f"{prefix}<2.5")
            if o and u:
                m.ou[key] = (o, u)
        matches.append(m)
    return matches


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def fetch_text(path: str, client: httpx.Client) -> str | None:
    """Download with a small disk cache. Falls back to a stale copy if the site is down."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, path.replace("/", "_"))
    max_age = config.REFRESH_HOURS * 3600 * 0.9
    if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < max_age:
        with open(cache_file, "rb") as f:
            return _decode(f.read())
    try:
        r = client.get(f"{config.BASE_URL}/{path}")
        if r.status_code == 404:
            return None  # e.g. a new season that has not started yet
        r.raise_for_status()
        with open(cache_file, "wb") as f:
            f.write(r.content)
        return _decode(r.content)
    except httpx.HTTPError as exc:
        log.warning("Download failed for %s: %s", path, exc)
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as f:
                return _decode(f.read())
        return None


def load_all() -> tuple[dict[str, list[Match]], dict[str, set[str]], list[Match]]:
    """
    Returns (history by league, teams that played in the league last season,
    upcoming fixtures).
    """
    cur, prev = config.season_codes()
    jobs = [(lg, season) for lg in config.LEAGUES for season in (prev, cur)]
    headers = {"User-Agent": "tinovi-tipovi/2.0 (+https://github.com)"}

    with httpx.Client(timeout=config.HTTP_TIMEOUT, headers=headers, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            texts = list(pool.map(lambda j: fetch_text(f"mmz4281/{j[1]}/{j[0]}.csv", client), jobs))
        fixtures_text = fetch_text("fixtures.csv", client)

    history: dict[str, list[Match]] = {lg: [] for lg in config.LEAGUES}
    last_season_teams: dict[str, set[str]] = {lg: set() for lg in config.LEAGUES}
    for (lg, season), text in zip(jobs, texts):
        if not text:
            continue
        parsed = [m for m in parse_csv(text, lg) if m.played]
        history[lg].extend(parsed)
        if season == prev:
            last_season_teams[lg] = {t for m in parsed for t in (m.home, m.away)}

    now = datetime.now(timezone.utc)
    fixtures = [m for m in parse_csv(fixtures_text or "") if m.kickoff > now and not m.played]
    for lg in history:
        history[lg].sort(key=lambda m: m.kickoff)
    fixtures.sort(key=lambda m: m.kickoff)
    log.info(
        "Loaded %d historical matches and %d upcoming fixtures",
        sum(len(v) for v in history.values()),
        len(fixtures),
    )
    return history, last_season_teams, fixtures
