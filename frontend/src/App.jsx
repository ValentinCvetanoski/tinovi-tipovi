import { useEffect, useMemo, useState } from "react";
import { useSnapshot } from "./api";
import { dateTime } from "./format";
import MatchList from "./components/MatchList";
import Performance from "./components/Performance";
import Ticket from "./components/Ticket";
import TipList from "./components/TipList";

const TABS = [
  { id: "safe", label: "Sigurni" },
  { id: "value", label: "Vrednost" },
  { id: "goals", label: "Golovi" },
  { id: "all", label: "Site natprevari" },
  { id: "perf", label: "Kolku pogoduva" },
];

const STORAGE_KEY = "tinovi-tiket";

function loadTicket() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? {};
  } catch {
    return {};
  }
}

export default function App() {
  const { data, error, waking, retry } = useSnapshot();
  const [tab, setTab] = useState("safe");
  const [ticket, setTicket] = useState(loadTicket);

  const matchesById = useMemo(
    () => Object.fromEntries((data?.matches ?? []).map((m) => [m.id, m])),
    [data],
  );

  // Drop matches from the slip once they are no longer upcoming.
  useEffect(() => {
    if (!data) return;
    setTicket((t) => Object.fromEntries(Object.entries(t).filter(([id]) => matchesById[id])));
  }, [data, matchesById]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ticket));
    } catch {
      /* storage can be unavailable (private mode); the slip still works */
    }
  }, [ticket]);

  const toggle = (id, code) =>
    setTicket((t) => {
      const next = { ...t };
      if (next[id] === code) delete next[id];
      else next[id] = code;
      return next;
    });

  const remove = (id) =>
    setTicket((t) => {
      const next = { ...t };
      delete next[id];
      return next;
    });

  return (
    <div className="app">
      <header className="top">
        <h1 className="wordmark">
          Tinovi tipovi
        </h1>
        <p className="tagline">Shansi od statistichki model, provereni so koeficientite na pazarot.</p>
        {data && <p className="updated">Azhurirano {dateTime(data.updated_at)}</p>}
      </header>

      {!data && !error && (
        <div className="state" role="status">
          <p>{waking ? "Serverot se budi. Prviot pat ova trae do edna minuta." : "Se vchituva…"}</p>
          <div className="loader" aria-hidden="true" />
        </div>
      )}

      {error && (
        <div className="state state--error" role="alert">
          <p>{error}</p>
          <button type="button" className="button" onClick={retry}>
            Probaj povtorno
          </button>
        </div>
      )}

      {data && (
        <div className="layout">
          <main>
            <nav className="tabs" aria-label="Kategorii">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="tab"
                  aria-current={tab === t.id ? "page" : undefined}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                  {data.tips[t.id] && <span className="tab__n">{data.tips[t.id].length}</span>}
                </button>
              ))}
            </nav>

            {["safe", "value", "goals"].includes(tab) && (
              <TipList kind={tab} tips={data.tips[tab]} matchesById={matchesById} ticket={ticket} onToggle={toggle} />
            )}
            {tab === "all" && (
              <MatchList matches={data.matches} leagues={data.leagues} ticket={ticket} onToggle={toggle} />
            )}
            {tab === "perf" && <Performance perf={data.performance} />}
          </main>

          <Ticket ticket={ticket} matchesById={matchesById} onRemove={remove} onClear={() => setTicket({})} />
        </div>
      )}

      <footer className="foot">
        <p>Samo za 18+. Tipovite se procenki, ne garancii. Igraj odgovorno i vlozhuvaj samo kolku shto mozhesh da izgubish.</p>
        <p>
          Podatoci: <a href="https://www.football-data.co.uk/">football-data.co.uk</a>
        </p>
      </footer>
    </div>
  );
}
