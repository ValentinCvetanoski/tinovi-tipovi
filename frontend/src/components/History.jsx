import { useCallback, useEffect, useState } from "react";
import { fetchHistory } from "../api";
import { kickoff, odds as fmtOdds, pct, PICKS } from "../format";

const CATEGORIES = [
  { id: "all", label: "Site tipovi" },
  { id: "safe", label: "Sigurni" },
  { id: "value", label: "Vrednost" },
  { id: "goals", label: "Golovi" },
];
const RESULTS = [
  { id: "all", label: "Site ishodi" },
  { id: "won", label: "Pominati" },
  { id: "lost", label: "Padnati" },
];
const CATEGORY_NAME = { safe: "Sigurni", value: "Vrednost", goals: "Golovi" };
const PAGE = 40;

function money(units) {
  if (units == null) return "–";
  const den = Math.round(units * 100);
  return `${den > 0 ? "+" : ""}${den.toLocaleString("mk-MK")} den.`;
}

function Chips({ label, options, value, onChange }) {
  return (
    <div className="filters" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" className="chip" aria-pressed={value === o.id} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function groupByDay(items) {
  const groups = [];
  for (const t of items) {
    const day = kickoff(t.kickoff).day;
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(t);
    else groups.push({ day, items: [t] });
  }
  return groups;
}

export default function History() {
  const [category, setCategory] = useState("all");
  const [result, setResult] = useState("all");
  const [league, setLeague] = useState("");
  const [page, setPage] = useState(null); // last response, items accumulated
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(
    async (offset = 0) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchHistory({ category, league, result, offset, limit: PAGE });
        setPage((prev) =>
          offset > 0 && prev?.status === "ok" ? { ...res, items: [...prev.items, ...res.items] } : res,
        );
      } catch (e) {
        setError(e.message || "Ne mozhevme da gi vchitame minatite tipovi.");
      } finally {
        setLoading(false);
      }
    },
    [category, league, result],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  if (error) {
    return (
      <div className="state state--error" role="alert">
        <p>{error}</p>
        <button type="button" className="button" onClick={() => load(0)}>
          Probaj povtorno
        </button>
      </div>
    );
  }

  if (!page) return <p className="empty">Se vchituva…</p>;

  if (page.status === "pending") {
    return (
      <div className="empty">
        <p>Minatite tipovi se presmetuvaat. Ova trae edna do dve minuti po budenjeto na serverot.</p>
        <button type="button" className="button" onClick={() => load(0)} disabled={loading}>
          Vchitaj povtorno
        </button>
      </div>
    );
  }

  const s = page.summary;
  const sinceDate = page.since ? new Date(page.since) : null;
  const since = sinceDate
    ? `${sinceDate.getUTCDate()}.${sinceDate.getUTCMonth() + 1}.${sinceDate.getUTCFullYear()}`
    : "pochetokot";
  const filtered = category !== "all" || result !== "all" || league !== "";
  const dataThrough = page.data_through ? kickoff(page.data_through).day : null;

  return (
    <section className="history" aria-label="Minati tipovi">
      <p className="intro">
        Site tipovi od {since} navamu, so konechniot rezultat. Sekoj tip se presmetuva samo so podatocite od pred
        pochetokot na natprevarot.
        {dataThrough && (
          <>
            {" "}
            Rezultatite stignuvaat od football-data.co.uk dva pati nedelno. Posleden rezultat vo podatocite:{" "}
            <strong>{dataThrough}</strong>.
          </>
        )}
      </p>

      <div className="history__filters">
        <Chips label="Kategorija" options={CATEGORIES} value={category} onChange={setCategory} />
        <Chips label="Ishod" options={RESULTS} value={result} onChange={setResult} />
        <label className="select">
          <span className="visually-hidden">Liga</span>
          <select value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">Site ligi</option>
            {page.leagues.map((l) => (
              <option key={l.code} value={l.code}>
                {l.country}, {l.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {s.tips > 0 && (
        <div className="record" aria-live="polite">
          <p className="record__main">
            Pominaa {s.won} od {s.tips} tipovi <span className="record__pct">({pct(s.hit_rate)})</span>
          </p>
          <p className="record__money">
            Ako vlozhuvashe 100 den. na sekoj tip:{" "}
            <strong className={s.profit_best_odds > 0 ? "good" : "bad"}>{money(s.profit_best_odds)}</strong> so
            najdobriot koeficient, <span className={s.profit_avg_odds > 0 ? "good" : "bad"}>{money(s.profit_avg_odds)}</span>{" "}
            so prosechniot.
          </p>
        </div>
      )}

      {page.items.length === 0 ? (
        <p className="empty">
          {filtered
            ? "Nema tipovi za ovie filtri."
            : `Seushte nema rezultati za tipovite od ${since} navamu. Tie kje se pojavat tuka koga izvorot kje gi dodade rezultatite, obichno eden do tri dena po natprevarot.`}
        </p>
      ) : (
        <>
          {groupByDay(page.items).map((g) => (
            <div key={g.day} className="day">
              <h3 className="day__title">{g.day}</h3>
              <ol className="rows">
                {g.items.map((t) => (
                  <li key={`${t.match_id}-${t.category}`} className={`row row--past ${t.won ? "is-won" : "is-lost"}`}>
                    <div className="row__when">
                      <span>{kickoff(t.kickoff).time}</span>
                    </div>
                    <div className="row__teams">
                      <span className="teams">
                        {t.home} <span className="score">{t.score.replace("-", " : ")}</span> {t.away}
                      </span>
                      <span className="meta">
                        {t.country}, {t.league_name}
                        {category === "all" && <> | {CATEGORY_NAME[t.category]}</>}
                      </span>
                    </div>
                    <div className="row__past">
                      <span className="past-pick">
                        <b>{t.pick}</b>
                        <span className="meta">
                          {PICKS[t.pick]?.label ?? t.pick}, {pct(t.p)}
                        </span>
                      </span>
                      <span className="past-odds">{fmtOdds(t.odds)}</span>
                      <span className={`verdict ${t.won ? "verdict--won" : "verdict--lost"}`}>
                        {t.won ? "Pomina" : "Padna"}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          ))}

          {page.items.length < page.total && (
            <button type="button" className="button more" onClick={() => load(page.items.length)} disabled={loading}>
              {loading ? "Se vchituva…" : `Prikazhi ushte (${page.total - page.items.length} preostanuvaat)`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
