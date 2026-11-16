# Tinovi tipovi

Football tips from a statistical model, checked against the betting market. No API keys, no accounts, no costs.

- **Backend** (`backend/`, Python/FastAPI): runs on Render.
- **Frontend** (`frontend/`, React/Vite): runs on Vercel.

## How it works

1. **Data.** Results, expected goals (xG) and bookmaker odds come from the free CSV files at [football-data.co.uk](https://www.football-data.co.uk/). Upcoming matches come from its `fixtures.csv`. 18 leagues are included (see `backend/app/config.py`).
2. **Model.** A Dixon-Coles model gives every team an attack and a defence rating. Recent matches count more, the target mixes xG with real goals (xG predicts future results better than goals alone), and promoted teams start slightly below average.
3. **Market.** Betfair Exchange and average bookmaker odds are converted to probabilities, with the bookmaker margin removed (power method).
4. **Blend.** Model and market are combined. The weight is not guessed: every refresh, the last 70 days are replayed with the model refit every 3 weeks on past data only, and the weight that would have predicted those matches best is used.
5. **Tips.**
   - *Sigurni*: 1X2 picks with at least a 62% chance and odds of at least 1.25.
   - *Vrednost*: the best available price is at least 3% higher than the fair price.
   - *Golovi*: 3+ or 0-2 goals with at least a 58% chance.

   The *Minati tipovi* tab lists every tip since the launch date (`HISTORY_START`) with the final score and whether it won, plus the record and profit for any filter. The list keeps growing; it does not expire. The *Kolku pogoduva* tab shows how accurate the probabilities were.

   Past tips are rebuilt from the data instead of being stored, because Render's free plan has no permanent disk. They are the tips the app would have given at the time: the model is refit every week on matches played before, and uses the odds published before kick-off.

Data refreshes every 3 hours in the background, so pages load instantly from memory. After a restart, tips go live as soon as the data is downloaded; the backtest runs afterwards (at most once a day) and then fine-tunes the blend.

## Run locally

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # http://localhost:8000/api/snapshot

# frontend (second terminal)
cd frontend
npm install
cp .env.example .env                     # points to http://localhost:8000
npm run dev                              # http://localhost:5173
```

API: `/api/snapshot` (everything for upcoming matches), `/api/history?category=all|safe|value|goals&league=E0&result=all|won|lost&limit=40&offset=0` (past tips), `/api/health`.

Tests: `cd backend && pip install pytest && python -m pytest`. They use generated data, so no internet is needed.

## Deploy

**1. Backend on Render**
- Render dashboard > **New > Blueprint** > pick this repository. It reads `render.yaml`.
- Leave `ALLOWED_ORIGINS` empty for now and create the service.
- When it is live, open `https://<your-service>.onrender.com/api/health`. `"ready": true` means the first snapshot is built (about a minute after start).

**2. Frontend on Vercel**
- Vercel > **Add New > Project** > import this repository.
- **Root Directory**: `frontend` (Vercel detects Vite).
- **Environment Variable**: `VITE_API_URL` = `https://<your-service>.onrender.com`
- Deploy.

**3. Lock the API to your site (optional)**
- On Render, set `ALLOWED_ORIGINS` to your Vercel URL, e.g. `https://tinovi-tipovi.vercel.app`.

### Free-tier note
A free Render service sleeps after 15 minutes without visitors. The first visit after that waits while it wakes up and downloads the data (usually under a minute); the site shows a message and retries on its own. The *Kolku pogoduva* tab fills in a minute or two later.

## Settings

All optional, set as environment variables on Render:

| Variable | Default | Meaning |
|---|---|---|
| `LEAGUES` | all 18 | Comma-separated codes, e.g. `E0,SP1,I1,D1,F1` |
| `REFRESH_HOURS` | `3` | How often to check for new data |
| `XG_SHARE` | `0.6` | Share of xG vs goals in the model's training target |
| `DECAY` | `0.003` | How fast old matches lose weight (per day) |
| `SAFE_MIN_PROB` | `0.62` | Minimum chance for *Sigurni* |
| `VALUE_MIN_EV` | `0.03` | Minimum value for *Vrednost* |
| `GOALS_MIN_PROB` | `0.58` | Minimum chance for *Golovi* |
| `TIPS_LIMIT` | `12` | Tips shown per tab |
| `BACKTEST_EVERY_HOURS` | `24` | How often the backtest is rerun |
| `HISTORY_START` | `2026-11-15` | First day shown in *Minati tipovi* (YYYY-MM-DD) |

## Responsible gambling

Tips are estimates, not guarantees. Bookmakers win in the long run because of their margin; the backtest shows honestly how each tip type would have done. 18+ only.
