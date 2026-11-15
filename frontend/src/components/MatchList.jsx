import { useState } from "react";
import { FORM, kickoff, pct, pickInfo } from "../format";
import PickButton from "./PickButton";

function Form({ results }) {
  if (!results?.length) return <span className="meta">nema podatoci</span>;
  return (
    <span className="form" aria-label="Posledni rezultati">
      {results.map((r, i) => (
        <span key={i} className={`form__r form__r--${r}`}>
          {FORM[r]}
        </span>
      ))}
    </span>
  );
}

function Details({ m }) {
  const rows = [
    ["1", "home"],
    ["X", "draw"],
    ["2", "away"],
  ];
  return (
    <div className="details">
      <dl className="facts">
        {m.xg && (
          <div>
            <dt>Ochekuvani golovi</dt>
            <dd>
              {m.xg.home.toFixed(2)} : {m.xg.away.toFixed(2)}
            </dd>
          </div>
        )}
        {m.top_scores?.length > 0 && (
          <div>
            <dt>Najverojatni rezultati</dt>
            <dd>{m.top_scores.map((s) => `${s.score} (${pct(s.p)})`).join(", ")}</dd>
          </div>
        )}
        {m.probs.btts != null && (
          <div>
            <dt>Dvata tima davaat gol</dt>
            <dd>{pct(m.probs.btts)}</dd>
          </div>
        )}
        <div>
          <dt>Forma, {m.home}</dt>
          <dd>
            <Form results={m.form?.home} />
          </dd>
        </div>
        <div>
          <dt>Forma, {m.away}</dt>
          <dd>
            <Form results={m.form?.away} />
          </dd>
        </div>
      </dl>
      {m.model && m.market && (
        <table className="compare">
          <caption>Od kade doagja shansata</caption>
          <thead>
            <tr>
              <th scope="col"></th>
              <th scope="col">Model</th>
              <th scope="col">Pazar</th>
              <th scope="col">Konechno</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([code, key]) => (
              <tr key={code}>
                <th scope="row">{code}</th>
                <td>{pct(m.model[key])}</td>
                <td>{pct(m.market[key])}</td>
                <td>
                  <strong>{pct(m.probs[key])}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function MatchList({ matches, leagues, ticket, onToggle }) {
  const [league, setLeague] = useState("all");
  const [open, setOpen] = useState(null);
  const shown = league === "all" ? matches : matches.filter((m) => m.league === league);

  return (
    <section aria-label="Site natprevari">
      <p className="intro">Klikni na koeficient za da go dodadesh na tiketot. Pod sekoj koeficient e shansata spored nas.</p>
      <div className="filters" role="group" aria-label="Liga">
        <button type="button" className="chip" aria-pressed={league === "all"} onClick={() => setLeague("all")}>
          Site ligi
        </button>
        {leagues.map((l) => (
          <button
            type="button"
            key={l.code}
            className="chip"
            aria-pressed={league === l.code}
            onClick={() => setLeague(l.code)}
          >
            {l.name} <span className="chip__n">{l.matches}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="empty">Nema natprevari vo ovaa liga vo slednite denovi.</p>
      ) : (
        <ol className="rows">
          {shown.map((m) => {
            const k = kickoff(m.kickoff);
            const isOpen = open === m.id;
            return (
              <li key={m.id} className="row row--match">
                <div className="row__when">
                  <span>{k.day}</span>
                  <span>{k.time}</span>
                </div>
                <div className="row__teams">
                  <button
                    type="button"
                    className="teams teams--toggle"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : m.id)}
                  >
                    {m.home} <span className="vs">–</span> {m.away}
                  </button>
                  <span className="meta">
                    {m.country}, {m.league_name}
                  </span>
                </div>
                <div className="row__picks">
                  {["1", "X", "2"].map((code) => (
                    <PickButton
                      key={code}
                      code={code}
                      info={pickInfo(m, code)}
                      active={ticket[m.id] === code}
                      onToggle={() => onToggle(m.id, code)}
                    />
                  ))}
                  <span className="row__gap" aria-hidden="true" />
                  {["3+", "0-2"].map((code) => (
                    <PickButton
                      key={code}
                      code={code}
                      info={pickInfo(m, code)}
                      active={ticket[m.id] === code}
                      onToggle={() => onToggle(m.id, code)}
                    />
                  ))}
                </div>
                {isOpen && <Details m={m} />}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
