import { useState } from "react";
import { odds as fmtOdds, pct, pickInfo } from "../format";

/**
 * The betting slip. Shows the total odds next to the honest chance that the
 * whole slip wins (product of the individual chances).
 */
export default function Ticket({ ticket, matchesById, onRemove, onClear }) {
  const [stake, setStake] = useState(100);
  const [open, setOpen] = useState(false);

  const legs = Object.entries(ticket)
    .map(([id, code]) => {
      const m = matchesById[id];
      return m ? { id, code, m, ...pickInfo(m, code) } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.m.kickoff.localeCompare(b.m.kickoff));

  const priced = legs.every((l) => l.odds);
  const total = priced ? legs.reduce((acc, l) => acc * l.odds, 1) : null;
  const chance = legs.reduce((acc, l) => acc * (l.p ?? 0), 1);
  const win = total ? stake * total : null;
  const value = total ? chance * total - 1 : null;

  return (
    <aside className={`slip${open ? " is-open" : ""}`} aria-label="Tvoj tiket">
      <button type="button" className="slip__bar" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>Tiket ({legs.length})</span>
        <span className="slip__bar-odds">{legs.length ? fmtOdds(total) : "prazen"}</span>
      </button>

      <div className="slip__body">
        <div className="slip__head">
          <h2>Tvoj tiket</h2>
          {legs.length > 0 && (
            <button type="button" className="link" onClick={onClear}>
              Ischisti
            </button>
          )}
        </div>

        {legs.length === 0 ? (
          <p className="slip__empty">Klikni na koeficient za da dodadesh natprevar.</p>
        ) : (
          <>
            <ul className="slip__legs">
              {legs.map((l) => (
                <li key={l.id}>
                  <div>
                    <span className="slip__match">
                      {l.m.home} – {l.m.away}
                    </span>
                    <span className="slip__pick">
                      <b>{l.code}</b> {l.label}, shansa {pct(l.p)}
                    </span>
                  </div>
                  <span className="slip__odds">{fmtOdds(l.odds)}</span>
                  <button type="button" className="slip__x" onClick={() => onRemove(l.id)} aria-label={`Otstrani ${l.m.home} – ${l.m.away}`}>
                    ×
                  </button>
                </li>
              ))}
            </ul>

            <dl className="slip__sum">
              <div>
                <dt>Vkupen koeficient</dt>
                <dd className="slip__total">{fmtOdds(total)}</dd>
              </div>
              <div>
                <dt>Shansa tiketot da pomine</dt>
                <dd>{pct(chance, chance < 0.1 ? 1 : 0)}</dd>
              </div>
              <div>
                <dt>
                  <label htmlFor="stake">Ulog (den.)</label>
                </dt>
                <dd>
                  <input
                    id="stake"
                    type="number"
                    min="10"
                    step="10"
                    inputMode="numeric"
                    value={stake}
                    onChange={(e) => setStake(Math.max(0, Number(e.target.value) || 0))}
                  />
                </dd>
              </div>
              <div>
                <dt>Mozhna dobivka</dt>
                <dd>{win ? `${Math.round(win).toLocaleString("mk-MK")} den.` : "–"}</dd>
              </div>
            </dl>

            {value != null && (
              <p className={`slip__note ${value > 0 ? "good" : ""}`}>
                {value > 0
                  ? `Koeficientot e povisok od fer cenata. Na dolg rok ovoj tiket vrakja okolu ${Math.round(value * 100)}% povekje od vlozhenoto.`
                  : `Na dolg rok ovoj tiket gubi okolu ${Math.round(-value * 100)}% od vlozhenoto.`}
              </p>
            )}
            {legs.length >= 4 && (
              <p className="slip__note">Sekoj dopolnitelen natprevar ja namaluva shansata.</p>
            )}
            {!priced && <p className="slip__note">Za nekoj od izborite nemame koeficient.</p>}
          </>
        )}
      </div>
    </aside>
  );
}
