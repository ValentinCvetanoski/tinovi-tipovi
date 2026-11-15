from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from app import config, data, engine
from app.market import blend, devig
from app.model import fit, score_probabilities

from .synthetic import League, build_files


@pytest.fixture(scope="module")
def leagues():
    return [League("E0", seed=1, with_xg=True), League("D1", n_teams=18, seed=2, with_xg=False)]


@pytest.fixture(scope="module")
def files(leagues):
    return build_files(leagues, date.today())


@pytest.fixture
def offline(monkeypatch, files, tmp_path):
    monkeypatch.setattr(config, "LEAGUES", {"E0": ("Anglija", "Premier League"), "D1": ("Germanija", "Bundesliga")})
    monkeypatch.setattr(data, "fetch_text", lambda path, client: files.get(path))
    # tests replay the whole recent history unless they say otherwise
    monkeypatch.setattr(config, "HISTORY_START", datetime.now(timezone.utc) - timedelta(days=60))


def test_devig_removes_margin():
    p = devig((1.5, 4.2, 6.5))
    assert abs(sum(p) - 1) < 1e-9
    # power method takes more off the long shot than the favourite
    naive = np.array([1 / 1.5, 1 / 4.2, 1 / 6.5]) / sum([1 / 1.5, 1 / 4.2, 1 / 6.5])
    assert p[0] > naive[0] and p[2] < naive[2]


def test_score_probabilities_sum_to_one():
    p = score_probabilities(1.6, 1.1, -0.05)
    assert abs(p["home"] + p["draw"] + p["away"] - 1) < 1e-9
    assert abs(p["over25"] + p["under25"] - 1) < 1e-9
    assert p["home"] > p["away"]


def test_blend_extremes():
    model = {"home": 0.6, "draw": 0.25, "away": 0.15, "over25": 0.5, "under25": 0.5, "btts": 0.5}
    market = {"home": 0.4, "draw": 0.3, "away": 0.3, "over25": 0.6, "under25": 0.4}
    assert blend(model, market, 1.0)["home"] == pytest.approx(0.6)
    assert blend(model, market, 0.0)["home"] == pytest.approx(0.4)
    assert 0.4 < blend(model, market, 0.5)["home"] < 0.6
    assert blend(None, market, 0.5)["home"] == 0.4


def test_parser_handles_real_header(files):
    ms = data.parse_csv(files["mmz4281/2627/E0.csv"], "E0")
    assert ms and all(m.played for m in ms)
    m = ms[0]
    assert m.kickoff.tzinfo is not None
    assert set(m.odds) == {"max", "avg", "bfe"} and set(m.ou) == {"max", "avg", "bfe"}
    assert m.hxg is not None
    # two-digit years (older files) also parse
    old = files["mmz4281/2627/E0.csv"].replace("/2026,", "/26,")
    assert len(data.parse_csv(old, "E0")) == len(ms)


def test_model_recovers_true_strengths(files, leagues, offline):
    history, last_season, _ = data.load_all()
    lg = leagues[0]
    r = fit(history["E0"], datetime.now(timezone.utc), last_season["E0"])
    teams = [t for t in lg.cur_teams if r.knows(t)]
    true_strength = [lg.attack[t] + lg.defence[t] for t in teams]
    fitted = [r.attack[r.index[t]] + r.defence[r.index[t]] for t in teams]
    assert np.corrcoef(true_strength, fitted)[0, 1] > 0.85
    assert 0.1 < r.home_adv < 0.4


def test_snapshot_end_to_end(offline):
    snap = engine.build_snapshot()
    assert snap["status"] == "ok"
    assert snap["matches"], "expected upcoming matches"
    m = snap["matches"][0]
    p = m["probs"]
    assert abs(p["home"] + p["draw"] + p["away"] - 1) < 1e-3
    assert m["model"] and m["market"] and m["xg"]
    perf = snap["performance"]
    assert perf["matches"] > 50
    assert 0 <= perf["blend_weight"] <= 1
    # the blend should never be worse than the market alone on the data it was tuned on
    assert perf["overall"]["blend"]["log_loss"] <= perf["overall"]["market"]["log_loss"] + 1e-9
    for cat in ("safe", "value", "goals"):
        assert cat in snap["tips"]


def test_unknown_teams_fall_back_to_market(offline, files, monkeypatch):
    extra = files["fixtures.csv"].splitlines()
    row = extra[1].split(",")
    row[3], row[4] = "Brand New FC", "Another New FC"
    patched = dict(files, **{"fixtures.csv": "\n".join(extra + [",".join(row)]) + "\n"})
    monkeypatch.setattr(data, "fetch_text", lambda path, client: patched.get(path))
    snap = engine.build_snapshot()
    m = next(m for m in snap["matches"] if m["home"] == "Brand New FC")
    assert m["model"] is None and m["market"] is not None
    assert abs(m["probs"]["home"] + m["probs"]["draw"] + m["probs"]["away"] - 1) < 1e-3


def test_predictions_work_before_backtest(offline):
    history, last_season, fixtures = data.load_all()
    snap = engine.build_predictions(history, last_season, fixtures, perf=None)
    assert snap["matches"] and snap["performance"] is None
    assert snap["blend_weight"] == engine.DEFAULT_BLEND


def _expected_win(pick, score):
    hg, ag = map(int, score.split("-"))
    return {
        "1": hg > ag, "X": hg == ag, "2": hg < ag,
        "3+": hg + ag >= 3, "0-2": hg + ag <= 2,
        "GG": hg > 0 and ag > 0, "NG": hg == 0 or ag == 0,
    }[pick]


def test_past_tips_are_scored_correctly(offline):
    history, last_season, _ = data.load_all()
    perf, past = engine.backtest(history, last_season)
    assert past, "expected past tips"
    assert {t["category"] for t in past} <= {"safe", "value", "goals"}
    assert [t["kickoff"] for t in past] == sorted((t["kickoff"] for t in past), reverse=True)
    for t in past:
        assert t["won"] == _expected_win(t["pick"], t["score"])


def test_past_tips_start_at_history_start(offline, monkeypatch):
    history, last_season, _ = data.load_all()
    start = datetime.now(timezone.utc) - timedelta(days=20)
    monkeypatch.setattr(config, "HISTORY_START", start)
    _, past = engine.backtest(history, last_season)
    assert past and all(datetime.fromisoformat(t["kickoff"]) >= start for t in past)

    # launch day in the future (nothing finished yet): empty list, stats still work
    monkeypatch.setattr(config, "HISTORY_START", datetime.now(timezone.utc) + timedelta(days=1))
    perf, past = engine.backtest(history, last_season)
    assert past == [] and perf["matches"] > 50

    # far in the past: tips keep accumulating beyond the 70-day stats window
    monkeypatch.setattr(config, "HISTORY_START", datetime.now(timezone.utc) - timedelta(days=150))
    _, long_past = engine.backtest(history, last_season)
    oldest = datetime.fromisoformat(long_past[-1]["kickoff"])
    assert oldest < datetime.now(timezone.utc) - timedelta(days=config.BACKTEST_DAYS + 7)


def test_past_tips_never_use_future_data(offline, monkeypatch):
    """Every replayed prediction must come from a fit made before kick-off."""
    real_fit = engine.fit
    fits = []

    def spy(matches, as_of, last):
        r = real_fit(matches, as_of, last)
        if r is not None:
            r._as_of = as_of
            real_predict = r.predict

            def predict(home, away, _r=r, _p=real_predict):
                fits.append((_r._as_of, home, away))
                return _p(home, away)

            r.predict = predict
        return r

    monkeypatch.setattr(engine, "fit", spy)
    history, last_season, _ = data.load_all()
    _, past = engine.backtest(history, last_season)
    kickoff = {(m.home, m.away): m.kickoff for ms in history.values() for m in ms}
    assert fits
    for as_of, home, away in fits:
        assert as_of <= kickoff[(home, away)]


def test_summarize():
    tips = [
        {"won": True, "odds": 2.0, "avg_odds": 1.9},
        {"won": False, "odds": 1.5, "avg_odds": 1.45},
        {"won": True, "odds": 1.8, "avg_odds": None},
    ]
    s = engine.summarize(tips)
    assert s["tips"] == 3 and s["won"] == 2
    assert s["profit_best_odds"] == pytest.approx((2.0 - 1) + (-1) + (1.8 - 1))
    assert s["profit_avg_odds"] == pytest.approx((1.9 - 1) + (-1))


def test_history_endpoint(offline):
    from fastapi.testclient import TestClient

    from app import main

    main._state.update(history=None, perf=None)
    client = TestClient(main.app)  # no "with": the background refresher stays off
    assert client.get("/api/history").json() == {"status": "pending"}

    history, last_season, _ = data.load_all()
    perf, past = engine.backtest(history, last_season)
    main._state.update(perf=perf, history=past)

    r = client.get("/api/history", params={"category": "safe", "limit": 5}).json()
    assert r["status"] == "ok" and len(r["items"]) == 5
    assert all(t["category"] == "safe" for t in r["items"])
    assert r["summary"]["tips"] == sum(t["category"] == "safe" for t in past)
    assert r["since"] == config.HISTORY_START.isoformat()

    page2 = client.get("/api/history", params={"category": "safe", "limit": 5, "offset": 5}).json()
    assert {t["match_id"] for t in page2["items"]}.isdisjoint({t["match_id"] for t in r["items"]})

    lost = client.get("/api/history", params={"result": "lost", "limit": 200}).json()
    assert lost["items"] and not any(t["won"] for t in lost["items"])

    lg = r["leagues"][0]["code"]
    only = client.get("/api/history", params={"league": lg, "limit": 200}).json()
    assert all(t["league"] == lg for t in only["items"])

    assert client.get("/api/history", params={"category": "bogus"}).status_code == 422
    main._state.update(history=None, perf=None)
