import { kickoff, pickInfo, signedPct, odds as fmtOdds } from "../format";
import PickButton from "./PickButton";

const INTRO = {
  safe: "Ishodi 1X2 so najmalku 62% shansa. Niski koeficienti, no pogoduvaat najchesto.",
  value: "Koeficientot e povisok od ona shto go opravduva shansata. Pogoduvaat poretko, no na dolg rok vredat.",
  goals: "3+ ili 0-2 gola, kade shto modelot i pazarot se soglasuvaat.",
};

const EMPTY = {
  safe: "Ovaa nedela nema dovolno sigurni natprevari. Pogledni gi site natprevari.",
  value: "Nema natprevari kade koeficientot e dovolno visok. Toa e dobar znak deka pazarot e tochen.",
  goals: "Nema jasni tipovi za golovi vo slednite denovi.",
};

export default function TipList({ kind, tips, matchesById, ticket, onToggle }) {
  return (
    <section aria-label="Tipovi">
      <p className="intro">{INTRO[kind]}</p>
      {tips.length === 0 ? (
        <p className="empty">{EMPTY[kind]}</p>
      ) : (
        <ol className="rows">
          {tips.map((t) => {
            const match = matchesById[t.match_id];
            if (!match) return null;
            const info = pickInfo(match, t.pick);
            const k = kickoff(t.kickoff);
            return (
              <li key={`${t.match_id}-${t.pick}`} className="row">
                <div className="row__when">
                  <span>{k.day}</span>
                  <span>{k.time}</span>
                </div>
                <div className="row__teams">
                  <span className="teams">
                    {t.home} <span className="vs">–</span> {t.away}
                  </span>
                  <span className="meta">
                    {t.country}, {t.league_name}
                    {kind === "value" && (
                      <>
                        {" "}| fer koeficient {fmtOdds(t.fair_odds)}, vrednost{" "}
                        <strong className="good">{signedPct(t.ev)}</strong>
                      </>
                    )}
                  </span>
                </div>
                <div className="row__pick">
                  <span className="pick-label">{info.label}</span>
                  <PickButton
                    code={t.pick}
                    info={info}
                    active={ticket[t.match_id] === t.pick}
                    onToggle={() => onToggle(t.match_id, t.pick)}
                    wide
                  />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
