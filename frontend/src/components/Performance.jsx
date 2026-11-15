import { dateTime, pct, signedPct, odds as fmtOdds } from "../format";

const SOURCES = [
  ["model", "Samo modelot"],
  ["market", "Samo pazarot"],
  ["blend", "Kombinirano (ova go koristime)"],
];

const RULES = [
  ["safe", "Sigurni"],
  ["value", "Vrednost"],
  ["goals", "Golovi"],
];

export default function Performance({ perf, onReload }) {
  if (!perf) {
    return (
      <div className="empty">
        <p>Proverkata na tochnosta se presmetuva. Ova trae edna do dve minuti po budenjeto na serverot.</p>
        <button type="button" className="button" onClick={onReload}>
          Vchitaj povtorno
        </button>
      </div>
    );
  }
  if (!perf.matches) {
    return <p className="empty">Seushte nema dovolno odigrani natprevari za merenje.</p>;
  }
  const days = Math.round((new Date(perf.to) - new Date(perf.from)) / 86400000);

  return (
    <section className="perf" aria-label="Kolku pogoduva">
      <p className="intro">
        Proverka na {perf.matches} natprevari od poslednite {days} dena. Modelot gi predvideshe bez da gi vidi
        rezultatite, isto kako shto gi predviduva idnite natprevari.
      </p>

      <h2>Tochnost na shansite</h2>
      <p className="note">
        Log loss meri kolku se tochni procentite (poniskoto e podobro). Pogodok e kolku chesto pobedil favoritot shto
        sme go izbrale. Modelot dobiva {Math.round(perf.blend_weight * 100)}% tezhina, pazarot ostatokot, bidejkji
        taka najdobro bi pogoduvalo na ovie natprevari.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col"></th>
            <th scope="col">Log loss</th>
            <th scope="col">Brier</th>
            <th scope="col">Pogodok</th>
          </tr>
        </thead>
        <tbody>
          {SOURCES.map(([key, label]) => (
            <tr key={key} className={key === "blend" ? "is-ours" : ""}>
              <th scope="row">{label}</th>
              <td>{perf.overall[key].log_loss.toFixed(3)}</td>
              <td>{perf.overall[key].brier.toFixed(3)}</td>
              <td>{pct(perf.overall[key].accuracy, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Kako bi pominale tipovite</h2>
      <p className="note">
        Profit na 1 den. ulog po tip. „Najdobar koeficient“ pretpostavuva deka sekogash ja naogjash najvisokata cena,
        shto vo praksa ne e sekogash mozhno. Mal broj tipovi znachi golema sluchajnost.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col"></th>
            <th scope="col">Tipovi</th>
            <th scope="col">Pogodeni</th>
            <th scope="col">Pros. koef.</th>
            <th scope="col">Profit, prosechen koef.</th>
            <th scope="col">Profit, najdobar koef.</th>
          </tr>
        </thead>
        <tbody>
          {RULES.map(([key, label]) => {
            const s = perf.tips?.[key];
            if (!s) return null;
            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>{s.tips}</td>
                <td>{pct(s.hit_rate, 1)}</td>
                <td>{fmtOdds(s.avg_odds)}</td>
                <td className={s.roi_avg_odds > 0 ? "good" : "bad"}>{signedPct(s.roi_avg_odds)}</td>
                <td className={s.roi_best_odds > 0 ? "good" : "bad"}>{signedPct(s.roi_best_odds)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2>Po liga</h2>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Liga</th>
              <th scope="col">Natprevari</th>
              <th scope="col">Log loss, model</th>
              <th scope="col">Log loss, pazar</th>
              <th scope="col">Log loss, kombinirano</th>
            </tr>
          </thead>
          <tbody>
            {perf.leagues.map((l) => (
              <tr key={l.code}>
                <th scope="row">
                  {l.name} <span className="meta">{l.country}</span>
                </th>
                <td>{l.matches}</td>
                <td className={l.model.log_loss < l.market.log_loss ? "good" : ""}>{l.model.log_loss.toFixed(3)}</td>
                <td>{l.market.log_loss.toFixed(3)}</td>
                <td>{l.blend.log_loss.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        Period: {dateTime(perf.from)} do {dateTime(perf.to)}.
      </p>
    </section>
  );
}
