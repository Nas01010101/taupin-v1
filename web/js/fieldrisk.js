// The trained field risk model (data/risk_model.json) run in the browser. Same formula as
// src/taupin/fieldrisk.py: z = intercept + sum(coef * (transform(x) - mean) / sd). The page shows
// z only as a rank against the 82 training fields (data/field_risk.json cut points), never as a
// probability: the model was fitted on 11 positive fields and is not calibrated for one farm.

export function transform(kind, x) {
  if (kind === 'log1p') return Math.log1p(x);
  if (kind === 'log') return Math.log(x);
  if (kind === 'identity' || kind === '0/1') return Number(x);
  throw new Error(`unknown transform ${kind}`);
}

export function score(model, inputs) {
  let z = model.intercept;
  for (const f of model.features) {
    const x = inputs[f.name];
    if (x == null || Number.isNaN(Number(x))) throw new Error(`missing input ${f.name}`);
    z += model.coef[f.name] * (transform(f.transform, x) - f.mean) / f.sd;
  }
  return z;
}

export const RANKS = ['low', 'mid', 'high'];
export const rankOf = (z, [a, b]) => (z <= a ? 'low' : z <= b ? 'mid' : 'high');

// POWER daily parameters ({YYYYMMDD: value}) -> the two weather inputs for a scouting year.
// Mirrors risk/fetch_power.py features(); -999 is POWER's missing value.
export function powerFeatures(p, year) {
  const win = (s, a, b) => Object.entries(s ?? {}).filter(([d, v]) => d >= a && d <= b && v > -900).map(([, v]) => v);
  const gw = win(p.GWETROOT, `${year}0401`, `${year}0531`), ts = win(p.TSOIL1, `${year - 1}1201`, `${year}0331`);
  return {
    gwet_spring: gw.length ? Math.round(1000 * gw.reduce((a, b) => a + b, 0) / gw.length) / 1000 : null,
    tsoil_winter_min_c: ts.length ? Math.min(...ts) : null,
  };
}

// Names of the inputs that fall outside what the 82 training fields covered.
export function outsideTraining(inputs, ranges) {
  return Object.entries(ranges).filter(([k, [lo, hi]]) => inputs[k] < lo || inputs[k] > hi).map(([k]) => k);
}

// One scouting year for the field: the class, the inputs used and any extrapolation.
export function fieldRanking(model, fr, { year, forageYears = 0, lightSoil = 0 }) {
  const w = fr.per_year[year];
  if (!w) return null;
  const inputs = { light_soil: lightSoil, forage_years: forageYears, ...w };
  const z = score(model, inputs);
  return { year, inputs, z, rank: rankOf(z, fr.rank_cutpoints), outside: outsideTraining(inputs, fr.training_range) };
}
