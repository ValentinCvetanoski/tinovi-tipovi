import { odds as fmtOdds, pct } from "../format";

/** A price you can click, like on a betting site. Clicking toggles it on the slip. */
export default function PickButton({ code, info, active, onToggle, wide = false }) {
  const disabled = info.p == null;
  return (
    <button
      type="button"
      className={`pick${active ? " is-active" : ""}${wide ? " pick--wide" : ""}`}
      aria-pressed={active}
      disabled={disabled}
      onClick={onToggle}
      title={`${code}: ${info.label}, shansa ${pct(info.p, 1)}`}
    >
      <span className="pick__code">{code}</span>
      <span className="pick__odds">{fmtOdds(info.odds)}</span>
      <span className="pick__p">{pct(info.p)}</span>
    </button>
  );
}
