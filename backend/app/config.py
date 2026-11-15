"""All settings live here. Everything can be overridden with environment variables."""

import os
from datetime import date

# Free data from football-data.co.uk: no account and no API key needed.
BASE_URL = os.getenv("DATA_BASE_URL", "https://www.football-data.co.uk").rstrip("/")

# football-data.co.uk league code -> (country, league name)
LEAGUES: dict[str, tuple[str, str]] = {
    "E0": ("Anglija", "Premier League"),
    "E1": ("Anglija", "Championship"),
    "E2": ("Anglija", "League One"),
    "E3": ("Anglija", "League Two"),
    "SC0": ("Skotska", "Premiership"),
    "D1": ("Germanija", "Bundesliga"),
    "D2": ("Germanija", "2. Bundesliga"),
    "I1": ("Italija", "Serie A"),
    "I2": ("Italija", "Serie B"),
    "SP1": ("Spanija", "La Liga"),
    "SP2": ("Spanija", "Segunda"),
    "F1": ("Francija", "Ligue 1"),
    "F2": ("Francija", "Ligue 2"),
    "N1": ("Holandija", "Eredivisie"),
    "B1": ("Belgija", "Pro League"),
    "P1": ("Portugalija", "Primeira Liga"),
    "T1": ("Turcija", "Super Lig"),
    "G1": ("Grcija", "Super League"),
}
_enabled = os.getenv("LEAGUES")
if _enabled:
    LEAGUES = {k: v for k, v in LEAGUES.items() if k in _enabled.split(",")}

# How often to re-download data and refit (football-data updates ~twice a week).
REFRESH_HOURS = float(os.getenv("REFRESH_HOURS", "6"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

# --- model ---
# Older matches count less: weight = exp(-DECAY * days_ago). 0.003 = half-life of ~230 days.
DECAY = float(os.getenv("DECAY", "0.003"))
# Share of expected goals (xG) in the training target; the rest is real goals.
XG_SHARE = float(os.getenv("XG_SHARE", "0.6"))
# Pulls team ratings toward the league average when there is little data.
RIDGE = float(os.getenv("RIDGE", "2.0"))
# Promoted teams start slightly below average.
PROMOTED_PRIOR = float(os.getenv("PROMOTED_PRIOR", "-0.15"))
MAX_GOALS = 10

# --- backtest ---
# Matches in the last N days are held out to measure the model honestly.
BACKTEST_DAYS = int(os.getenv("BACKTEST_DAYS", "70"))

# --- tips ---
SAFE_MIN_PROB = float(os.getenv("SAFE_MIN_PROB", "0.62"))
GOALS_MIN_PROB = float(os.getenv("GOALS_MIN_PROB", "0.58"))
MIN_ODDS = float(os.getenv("MIN_ODDS", "1.25"))  # shorter prices are not worth showing
VALUE_MIN_EV = float(os.getenv("VALUE_MIN_EV", "0.03"))
VALUE_MIN_PROB = float(os.getenv("VALUE_MIN_PROB", "0.25"))
VALUE_MAX_ODDS = float(os.getenv("VALUE_MAX_ODDS", "6.0"))
TIPS_LIMIT = int(os.getenv("TIPS_LIMIT", "12"))


def season_codes(today: date | None = None) -> tuple[str, str]:
    """Current and previous season codes, e.g. ('2627', '2526') in Nov 2026."""
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    cur = f"{start % 100:02d}{(start + 1) % 100:02d}"
    prev = f"{(start - 1) % 100:02d}{start % 100:02d}"
    return cur, prev
