// Betting-slip codes and what they mean.
export const PICKS = {
  1: { key: "home", label: "pobeda na domakjinot" },
  X: { key: "draw", label: "nereseno" },
  2: { key: "away", label: "pobeda na gostinot" },
  "3+": { key: "over25", label: "3 ili povekje gola" },
  "0-2": { key: "under25", label: "najmnogu 2 gola" },
  GG: { key: "btts", label: "dvata tima davaat gol" },
};

export function pickInfo(match, code) {
  const meta = PICKS[code];
  const p = meta ? match.probs[meta.key] : undefined;
  return { p: p ?? null, odds: match.odds?.[code] ?? null, label: meta?.label ?? code };
}

const DAYS = ["ned", "pon", "vto", "sre", "chet", "pet", "sab"];

export function kickoff(iso) {
  const d = new Date(iso);
  const time = d.toLocaleTimeString("mk-MK", { hour: "2-digit", minute: "2-digit", hour12: false });
  return { day: `${DAYS[d.getDay()]} ${d.getDate()}.${d.getMonth() + 1}`, time };
}

export function dateTime(iso) {
  const k = kickoff(iso);
  return `${k.day}, ${k.time}`;
}

export const pct = (p, digits = 0) => (p == null ? "–" : `${(p * 100).toFixed(digits)}%`);
export const odds = (o) => (o == null ? "–" : o.toFixed(2));
export const signedPct = (x) => (x == null ? "–" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);

// W/D/L -> Macedonian P(obeda) / N(ereseno) / I(zgubi)
export const FORM = { W: "P", D: "N", L: "I" };
