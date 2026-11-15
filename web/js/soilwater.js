// Soil and water columns for the rotation table: crop water need against GPM IMERG rain, heavy
// rain on bare soil, the USLE cover factor, nitrogen and crop residue. Inputs are daily weather
// (web/data/weather.json, or the live POWER request for a user's field) and the per-crop values
// in web/data/crops.json, each with its source. A value with no source stays null and is listed
// as an information gap; it is never filled in.

const RAD = Math.PI / 180;

// FAO-56 Eq. 21: extraterrestrial radiation, MJ m-2 day-1.
export function ra(lat, doy) {
  const phi = lat * RAD, dr = 1 + 0.033 * Math.cos(2 * Math.PI * doy / 365);
  const dec = 0.409 * Math.sin(2 * Math.PI * doy / 365 - 1.39);
  const ws = Math.acos(Math.max(-1, Math.min(1, -Math.tan(phi) * Math.tan(dec))));
  return 24 * 60 / Math.PI * 0.082 * dr * (ws * Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.sin(ws));
}

// FAO-56 Eq. 52 (Hargreaves), mm/day; 0.408 turns MJ m-2 into mm of water.
export function et0(tmax, tmin, lat, doy) {
  if (tmax == null || tmin == null) return null;
  const v = 0.0023 * ((tmax + tmin) / 2 + 17.8) * Math.sqrt(Math.max(0, tmax - tmin)) * 0.408 * ra(lat, doy);
  return Math.max(0, v);
}

// FAO-56 single crop coefficient curve: flat Kc ini, linear rise, flat Kc mid, linear fall.
export function kcAt(crop, day) {
  const [ini, mid, end] = crop.kc, [li, ld, lm, ll] = crop.stages;
  if (day < 0 || day >= li + ld + lm + ll) return 0;
  if (day < li) return ini;
  if (day < li + ld) return ini + (mid - ini) * (day - li) / ld;
  if (day < li + ld + lm) return mid;
  return mid + (end - mid) * (day - li - ld - lm) / ll;
}

const pad = n => String(n).padStart(2, '0');
const iso = d => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

// {start, rain[], tmax[], tmin[]} -> {year: [{doy, rain, tmax, tmin}]} with doy from 1.
export function byYear(w) {
  const out = {}, t0 = Date.parse(w.start + 'T00:00:00Z');
  for (let i = 0; i < w.rain.length; i++) {
    const d = new Date(t0 + i * 864e5), y = d.getUTCFullYear();
    const doy = Math.round((d - Date.UTC(y, 0, 1)) / 864e5) + 1;
    (out[y] ??= []).push({ doy, rain: w.rain[i], tmax: w.tmax[i], tmin: w.tmin[i] });
  }
  return out;
}

// FAO-56 sowing rule: the first day from 1 March on which the 10-day running mean air
// temperature reaches t10. Returns the day of year, or null.
export function plantingDoy(days, t10) {
  const mean = days.map(d => (d.tmax == null || d.tmin == null ? null : (d.tmax + d.tmin) / 2));
  for (let i = 9; i < days.length; i++) {
    if (days[i].doy < 60) continue;
    const win = mean.slice(i - 9, i + 1);
    if (win.some(v => v == null)) continue;
    if (win.reduce((a, b) => a + b, 0) / 10 >= t10) return days[i].doy;
  }
  return null;
}

const APR1 = 91, NOV30 = 334;   // day of year, non-leap; one day off in leap years

// One crop in one year: sowing and harvest days, water need, rain over the season, and heavy-rain
// days that fall while the soil is bare (before about 10 % ground cover or after harvest).
export function cropYear(days, crop, lat, heavy = 25) {
  if (!crop.kc || !crop.stages || crop.plant_t10 == null) return null;
  const plant = plantingDoy(days, crop.plant_t10);
  if (plant == null) return null;
  const len = crop.stages.reduce((a, b) => a + b, 0), harvest = plant + len, cover = plant + crop.stages[0];
  let need = 0, rain = 0, bareHeavy = 0, missing = 0;
  for (const d of days) {
    if (d.doy >= plant && d.doy < harvest) {
      const e = et0(d.tmax, d.tmin, lat, d.doy);
      if (e == null || d.rain == null) { missing++; continue; }
      need += kcAt(crop, d.doy - plant) * e;
      rain += d.rain;
    }
    const bare = d.doy < cover || d.doy >= harvest, warm = d.tmax != null && d.tmin != null && (d.tmax + d.tmin) / 2 > 0;
    if (bare && warm && d.doy >= APR1 && d.doy <= NOV30 && d.rain != null && d.rain >= heavy) bareHeavy++;
  }
  if (missing > len * 0.1) return null;
  return { plant, harvest, need, rain, deficit: need - rain, bareHeavy };
}

const quantile = (xs, q) => {
  const s = [...xs].sort((a, b) => a - b), i = (s.length - 1) * q, lo = Math.floor(i);
  return s[lo] + (s[Math.ceil(i)] - s[lo]) * (i - lo);
};

// Per crop over all full years: medians, the 1-in-5 dry year (80th percentile of the shortfall),
// and the mean number of heavy-rain days on bare soil.
export function climatology(weather, crops, lat, heavy = 25) {
  const years = byYear(weather), full = Object.keys(years).filter(y => years[y].length >= 365).map(Number);
  const out = { years: [Math.min(...full), Math.max(...full)], n: full.length, crops: {} };
  for (const [id, crop] of Object.entries(crops)) {
    const rows = full.map(y => cropYear(years[y], crop, lat, heavy)).filter(Boolean);
    if (!rows.length) { out.crops[id] = null; continue; }
    const col = k => rows.map(r => r[k]);
    out.crops[id] = {
      n: rows.length,
      plant: Math.round(quantile(col('plant'), 0.5)),
      harvest: Math.round(quantile(col('harvest'), 0.5)),
      need: quantile(col('need'), 0.5),
      rain: quantile(col('rain'), 0.5),
      deficit: quantile(col('deficit'), 0.5),
      deficitDry: quantile(col('deficit'), 0.8),
      bareHeavy: col('bareHeavy').reduce((a, b) => a + b, 0) / rows.length,
    };
  }
  return out;
}

const LV = { NONE: 0, LOW: 0, MODERATE: 1, HIGH: 2 };
const mid = r => (r ? (r[0] + r[1]) / 2 : null);
const known = xs => xs.filter(v => v != null);
const mean = xs => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const sum = xs => (xs.length ? xs.reduce((a, b) => a + b, 0) : null);

// One rotation, year by year, plus five-year totals. `pests` is the rotation's row from
// riskView(); tillage is a key of crops.json `tillage`.
export function rotationMetrics(cropIds, clim, cropData, pests, tillage = 'fall_plow') {
  const tf = cropData.tillage[tillage];
  const years = cropIds.map((id, i) => {
    const c = cropData.crops[id], cl = clim.crops[id], prev = i ? cropData.crops[cropIds[i - 1]] : null;
    const credit = prev ? prev.n_credit_next : 0;
    const p = pests?.years[i];
    return {
      crop: id,
      deficit: cl?.deficit ?? null, deficitDry: cl?.deficitDry ?? null, need: cl?.need ?? null,
      bareHeavy: cl?.bareHeavy ?? null,
      c: c.usle_crop == null ? null : c.usle_crop * tf,
      n: c.n_need == null || credit == null ? null : Math.max(0, mid(c.n_need) - credit),
      credit,
      residue: c.yield_kg_ha == null || c.residue_ratio == null ? null : c.yield_kg_ha * c.residue_ratio / 1000,
      pest: p ? LV[p.wireworm] + LV[p.crw] : null,
      wireworm: p?.wireworm ?? null, crw: p?.crw ?? null,
    };
  });
  const col = k => known(years.map(y => y[k]));
  const unknown = k => years.filter(y => y[k] == null).length;
  // A five-year sum with a missing year would look smaller than it is, so it stays unknown.
  const whole = k => (unknown(k) ? null : sum(col(k)));
  return {
    years,
    total: {
      water: mean(col('deficitDry')), waterMedian: mean(col('deficit')),
      bareHeavy: whole('bareHeavy'), c: mean(col('c')),
      n: whole('n'), residue: mean(col('residue')), pest: whole('pest'),
    },
    unknown: { water: unknown('deficitDry'), bareHeavy: unknown('bareHeavy'), c: unknown('c'), n: unknown('n'), residue: unknown('residue'), pest: unknown('pest') },
  };
}

// Each priority maps to one total; `better` says which direction wins.
export const PRIORITIES = {
  pests: { key: 'pest', better: 'low', label: 'Fewer soil pests' },
  water: { key: 'water', better: 'low', label: 'Less water shortfall in a dry year' },
  soil: { key: 'c', better: 'low', label: 'Less soil loss (USLE cover)' },
  nitrogen: { key: 'n', better: 'low', label: 'Less nitrogen to buy' },
  organic: { key: 'residue', better: 'high', label: 'More crop residue returned' },
};

// Score each rotation 0 to 1 on every chosen priority (1 = best of the rotations shown, min-max)
// and rank by the mean. A rotation missing a value on a chosen priority ranks after every fully
// scored one, so a gap never lifts it. Ties keep the input order. Returns rows sorted best first.
export function rank(rotations, chosen) {
  const keys = chosen.filter(k => PRIORITIES[k]);
  const scores = rotations.map(r => ({ id: r.id, parts: {} }));
  for (const k of keys) {
    const { key, better } = PRIORITIES[k];
    const vals = rotations.map(r => r.metrics.total[key]);
    const ok = known(vals), lo = Math.min(...ok), hi = Math.max(...ok);
    vals.forEach((v, i) => {
      scores[i].parts[k] = v == null ? null : hi === lo ? 1 : better === 'low' ? (hi - v) / (hi - lo) : (v - lo) / (hi - lo);
    });
  }
  for (const s of scores) { s.score = mean(known(Object.values(s.parts))); s.complete = Object.values(s.parts).every(v => v != null); }
  return scores.map((s, i) => ({ ...s, i })).sort((a, b) => b.complete - a.complete || (b.score ?? -1) - (a.score ?? -1) || a.i - b.i)
    .map(({ i, ...s }, r) => ({ ...s, rank: r + 1 }));
}

const r0 = v => Math.round(v), r2 = v => Math.round(v * 100) / 100, r1 = v => Math.round(v * 10) / 10;

// Benefits and costs of one rotation against the current one, from the totals only.
export function versus(m, cur) {
  if (m === cur) return [];
  const a = m.total, b = cur.total, out = [];
  const add = (d, good, text) => { if (d != null && Math.abs(d) > 1e-9) out.push({ good, text }); };
  const dw = a.water != null && b.water != null ? b.water - a.water : null;
  add(dw != null && Math.abs(dw) >= 5 ? dw : null, dw > 0, `${Math.abs(r0(dw ?? 0))} mm ${dw > 0 ? 'less' : 'more'} water short per year in a dry year`);
  const dc = a.c != null && b.c != null ? b.c - a.c : null;
  add(dc != null && Math.abs(dc) >= 0.005 ? dc : null, dc > 0, `USLE cover factor ${r2(a.c)} against ${r2(b.c)}: soil loss ${Math.abs(r0(100 * (dc ?? 0) / b.c))} % ${dc > 0 ? 'lower' : 'higher'} on the same slope`);
  const dh = a.bareHeavy != null && b.bareHeavy != null ? b.bareHeavy - a.bareHeavy : null;
  add(dh != null && Math.abs(dh) >= 0.5 ? dh : null, dh > 0, `${r1(Math.abs(dh ?? 0))} ${dh > 0 ? 'fewer' : 'more'} heavy-rain days on bare soil over five years`);
  const dn = a.n != null && b.n != null ? b.n - a.n : null;
  add(dn, dn > 0, `${Math.abs(r0(dn ?? 0))} kg N/ha ${dn > 0 ? 'less' : 'more'} nitrogen to buy over five years`);
  const dr = a.residue != null && b.residue != null ? a.residue - b.residue : null;
  add(dr != null && Math.abs(dr) >= 0.1 ? dr : null, dr > 0, `${r1(Math.abs(dr ?? 0))} t/ha ${dr > 0 ? 'more' : 'less'} crop residue a year`);
  const dp = a.pest != null && b.pest != null ? b.pest - a.pest : null;
  add(dp, dp > 0, `${Math.abs(dp ?? 0)} ${dp > 0 ? 'fewer' : 'more'} pest points over five years (wireworm and rootworm levels)`);
  return out;
}

// Information gaps for a rotation: every crop value used here that has no source.
export function gaps(cropIds, cropData) {
  const out = new Set();
  for (const id of new Set(cropIds)) {
    const c = cropData.crops[id];
    for (const [k, label] of [['kc', 'water use (Kc)'], ['stages', 'season length'], ['n_need', 'nitrogen need'], ['n_credit_next', 'nitrogen left for the next crop'], ['yield_kg_ha', 'Quebec yield'], ['residue_ratio', 'residue ratio']]) {
      if (c[k] == null) out.add(`${c.name}: no sourced ${label}`);
    }
    for (const k of ['kc_note', 'plant_note', 'usle_note']) if (c[k] && /assum/i.test(c[k])) out.add(`${c.name}: ${c[k]}`);
  }
  return [...out];
}

export function doyDate(doy, year = 2025) { return iso(new Date(Date.UTC(year, 0, doy))); }
