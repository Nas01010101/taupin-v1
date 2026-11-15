// Trap dates and ranking inputs for any field, from one NASA POWER request made in the browser.
// The date rules are the ones in src/taupin/soil.py and the inputs the ones in
// src/taupin/fieldrisk.py, so the demo site gives the same values as the baked files.
import { powerFeatures } from './fieldrisk.js';

export const TRAP_C = 12, LARVAE_C = 8, CRW_BASE_C = 10.5, CRW_DD = 258, FIRST_YEAR = 1995, RECENT = 5;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ymd = d => d.toISOString().slice(0, 10).replaceAll('-', '');

// Two text inputs -> { lat, lon } to 4 decimals (about 10 m), or null. Accepts a decimal comma.
export function parseCoords(lat, lon) {
  const num = s => (/^\s*-?\d+([.,]\d+)?\s*$/.test(String(s)) ? Number(String(s).replace(',', '.')) : NaN);
  const a = num(lat), b = num(lon);
  if (!(Math.abs(a) <= 90) || !(Math.abs(b) <= 180)) return null;
  return { lat: Math.round(a * 1e4) / 1e4, lon: Math.round(b * 1e4) / 1e4 };
}

export const coordText = ({ lat, lon }) => `${Math.abs(lat)} ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon)} ${lon >= 0 ? 'E' : 'W'}`;

// From 1 Dec before the first year (the winter minimum needs it) to the day before `now`.
export function powerURL({ lat, lon }, now = new Date()) {
  const q = new URLSearchParams({ parameters: 'TSOIL1,GWETROOT', community: 'AG', longitude: lon, latitude: lat,
    start: `${FIRST_YEAR - 1}1201`, end: ymd(new Date(now.getTime() - 864e5)), format: 'JSON' });
  return `https://power.larc.nasa.gov/api/temporal/daily/point?${q}`;
}

// POWER { YYYYMMDD: value } -> sorted [[YYYY-MM-DD, value]] without the -999 fill values.
export function series(param) {
  return Object.entries(param ?? {}).filter(([, v]) => v != null && v > -998)
    .map(([k, v]) => [`${k.slice(0, 4)}-${k.slice(4, 6)}-${k.slice(6)}`, v]).sort((a, b) => (a[0] < b[0] ? -1 : 1));
}
const spring = (s, y) => s.filter(([d]) => d >= `${y}-03-01` && d <= `${y}-12-31`);

// Last day of the first `run`-day window after 1 Mar whose mean is at or above `thr`.
export function crossing(s, year, thr, run = 7) {
  const d = spring(s, year);
  for (let i = 0; i + run <= d.length; i++) {
    let sum = 0;
    for (let j = i; j < i + run; j++) sum += d[j][1];
    if (sum / run >= thr) return d[i + run - 1][0];
  }
  return null;
}

// First day after 1 Mar when soil degree-days above `base` reach `need` (rootworm egg hatch).
export function degreeDayDate(s, year, base = CRW_BASE_C, need = CRW_DD) {
  let acc = 0;
  for (const [d, v] of spring(s, year)) { acc += Math.max(0, v - base); if (acc >= need) return d; }
  return null;
}

export const doy = iso => (Date.parse(iso) - Date.parse(`${iso.slice(0, 4)}-01-01`)) / 864e5 + 1;
export function doyLabel(n) {
  const d = new Date(Date.UTC(2001, 0, Math.round(n)));
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

// Least-squares slope and its 95 % half-width (1.96 standard errors).
export function linearTrend(xs, ys) {
  const n = xs.length, mean = a => a.reduce((p, c) => p + c, 0) / n, mx = mean(xs), my = mean(ys);
  const sxx = xs.reduce((p, x) => p + (x - mx) ** 2, 0);
  const slope = xs.reduce((p, x, i) => p + (x - mx) * (ys[i] - my), 0) / sxx;
  const ss = xs.reduce((p, x, i) => p + (ys[i] - my - slope * (x - mx)) ** 2, 0);
  return [slope, n > 2 ? 1.96 * Math.sqrt(ss / (n - 2) / sxx) : 0];
}

// The object web/data/soil.json holds, for another field. `sources` are the baked file's own lines.
export function liveSoil(tsoil, sources) {
  const s = series(tsoil), rows = {}, r2 = v => Math.round(v * 100) / 100;
  if (!s.length) throw new Error('NASA POWER returned no soil temperature for this place');
  const y0 = Number(s[0][0].slice(0, 4)), y1 = Number(s[s.length - 1][0].slice(0, 4));
  for (let y = y0; y <= y1; y++) {
    if (s[0][0] > `${y}-03-01`) continue;   // the series starts after 1 March of this year
    const t12 = crossing(s, y, TRAP_C), t8 = crossing(s, y, LARVAE_C);
    if (t12 && t8) rows[y] = { trap_12C: t12, larvae_8C: t8, crw_hatch: degreeDayDate(s, y) };
  }
  const ys = Object.keys(rows).map(Number);
  if (ys.length < 3) throw new Error('the soil here does not reach 12 °C in spring in enough years');
  const d12 = ys.map(y => doy(rows[y].trap_12C)), d8 = ys.map(y => doy(rows[y].larvae_8C));
  const mean = a => a.reduce((p, c) => p + c, 0) / a.length, [slope, ci] = linearTrend(ys, d12);
  const daily = {};
  for (const y of ys.slice(-RECENT)) {
    const pts = s.filter(([d]) => d >= `${y}-03-01` && d <= `${y}-07-31`);
    daily[y] = { start: pts[0][0], tsoil: pts.map(([, v]) => r2(v)) };
  }
  return {
    years: [ys[0], ys[ys.length - 1]], thresholds_c: { trap: TRAP_C, larvae: LARVAE_C },
    trap_12C_mean_doy: Math.round(mean(d12) * 10) / 10, trap_12C_mean: doyLabel(mean(d12)),
    larvae_8C_mean_doy: Math.round(mean(d8) * 10) / 10, larvae_8C_mean: doyLabel(mean(d8)),
    trap_12C_trend_days_per_decade: r2(10 * slope), trap_12C_trend_95ci_days_per_decade: r2(10 * ci),
    // 7 March is the earliest date the rule can give: the soil was at 12 °C before 1 March.
    always_warm: ys.every(y => rows[y].trap_12C.endsWith('-03-07')),
    per_year: rows, daily, sources,
  };
}

// The object web/data/field_risk.json holds, for another field: same cutpoints and training range.
export function liveFieldRisk(p, base, site) {
  const last = Object.keys(p.GWETROOT ?? {}).filter(d => p.GWETROOT[d] > -900).sort().pop() ?? '';
  const per_year = {};
  const end = Number(last.slice(0, 4));
  for (let y = Math.max(FIRST_YEAR, end - 10); y <= end; y++) {   // the baked file also lists 11 years
    if (last < `${y}0531`) continue;   // spring not complete yet
    const f = powerFeatures(p, y);
    if (f.gwet_spring != null && f.tsoil_winter_min_c != null) per_year[y] = f;
  }
  if (!Object.keys(per_year).length) throw new Error('NASA POWER returned no soil wetness for this place');
  return { ...base, site, per_year };
}

// One request. Resolves to { site, soil, fr }; rejects with a message the page can show.
export async function fetchField(site, demo, { fetch = globalThis.fetch, now = new Date() } = {}) {
  const res = await fetch(powerURL(site, now));
  if (!res.ok) throw new Error(`NASA POWER answered ${res.status}`);
  const j = await res.json(), p = j?.properties?.parameter;
  if (!p?.TSOIL1) throw new Error('NASA POWER returned no data for this place');
  return { site, soil: liveSoil(p.TSOIL1, demo.soil.sources), fr: liveFieldRisk(p, demo.fieldRisk, site) };
}
