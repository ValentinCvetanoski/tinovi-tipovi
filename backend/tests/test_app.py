from datetime import date, datetime, timezone

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
