import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseCoords, coordText, powerURL, series, crossing, degreeDayDate, doy, doyLabel, linearTrend, liveSoil, liveFieldRisk, fetchField, weatherURL, weatherFrom } from '../js/power.js';

const J = p => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const soil = J('../data/soil.json'), fr = J('../data/field_risk.json'), fx = J('./fixtures/power_2025.json');
const P = fx.properties.parameter;

// A synthetic spring: `cold` until day `warmFrom` of March-July, then `warm`; one series per year.
function synth(years, warmFrom, cold = 2, warm = 15) {
  const out = {};
  for (const y of years) for (let i = 0; i < 153; i++) {
    const d = new Date(Date.UTC(y, 2, 1 + i)).toISOString().slice(0, 10).replaceAll('-', '');
    out[d] = i >= warmFrom(y) ? warm : cold;
  }
  return out;
}

test('coordinates: decimal comma accepted, out of range and text refused', () => {
  assert.deepEqual(parseCoords('45,50131', ' -73.7651 '), { lat: 45.5013, lon: -73.7651 });
  for (const [a, b] of [['91', '0'], ['45', '181'], ['abc', '1'], ['', ''], ['45.5N', '73'], ['1e2', '0']]) assert.equal(parseCoords(a, b), null);
  assert.equal(coordText({ lat: -33.9, lon: 18.4 }), '33.9 S, 18.4 E');
});

test('the request asks NASA POWER for the two parameters, the coordinates and nothing else', () => {
  const u = new URL(powerURL({ lat: 46.1, lon: -72.9 }, new Date('2026-11-14T12:00:00Z')));
  assert.equal(u.origin + u.pathname, 'https://power.larc.nasa.gov/api/temporal/daily/point');
  assert.deepEqual(Object.fromEntries(u.searchParams), { parameters: 'TSOIL1,GWETROOT', community: 'AG', longitude: '-72.9', latitude: '46.1', start: '19941201', end: '20261113', format: 'JSON' });
});

test('fill values are dropped and the series is in date order', () => {
  assert.deepEqual(series({ 20250302: 3, 20250301: -999, 20250228: 1 }), [['2025-02-28', 1], ['2025-03-02', 3]]);
});

test('dates for 2025 at the demo site match the baked soil.json (same rules as soil.py)', () => {
  const s = series(P.TSOIL1);
  assert.deepEqual({ trap_12C: crossing(s, 2025, 12), larvae_8C: crossing(s, 2025, 8), crw_hatch: degreeDayDate(s, 2025) }, soil.per_year['2025']);
});

test('ranking inputs for 2025 at the demo site match the baked field_risk.json', () => {
  const live = liveFieldRisk(P, fr, fr.site);
  assert.deepEqual(live.per_year, { 2025: fr.per_year['2025'] });
  assert.deepEqual([live.rank_cutpoints, live.training_range], [fr.rank_cutpoints, fr.training_range]);
});

test('a single warm day does not open the window; seven days at the threshold do', () => {
  const p = synth([2020], () => 40); p['20200315'] = 30;
  assert.equal(crossing(series(p), 2020, 12), '2020-04-15');   // warm from 10 Apr; six warm days and one cold already average 13.1
  assert.equal(crossing(series(synth([2020], () => 999)), 2020, 12), null);
});

test('day of year, its label and the trend', () => {
  assert.equal(doy('2025-05-14'), 134); assert.equal(doy('2024-03-01'), 61);
  assert.equal(doyLabel(134.2), '14 May'); assert.equal(doyLabel(66), '7 Mar');
  const [slope, ci] = linearTrend([1, 2, 3, 4], [2, 4, 6, 8]);
  assert.equal(slope, 2); assert.equal(ci, 0);
});

test('liveSoil gives the shape the app draws, with the last five years of curves', () => {
  const years = [2018, 2019, 2020, 2021, 2022, 2023], s = liveSoil(synth(years, y => 40 + (y - 2018)), soil.sources);
  assert.deepEqual(s.years, [2018, 2023]);
  assert.deepEqual(Object.keys(s.daily), ['2019', '2020', '2021', '2022', '2023']);
  assert.equal(s.daily[2023].tsoil.length, 153);
  assert.ok(Math.abs(s.trap_12C_trend_days_per_decade - 10) < 1);   // one day later each year; the 2020 leap day shifts it a little
  assert.equal(s.always_warm, false);
  for (const k of Object.keys(soil)) assert.ok(k in s, k);
});

test('soil already at 12 °C on 1 March is flagged; soil that never warms is an error', () => {
  assert.equal(liveSoil(synth([2020, 2021, 2022], () => 0), soil.sources).always_warm, true);
  assert.throws(() => liveSoil(synth([2020, 2021, 2022], () => 999), soil.sources), /does not reach 12/);
  assert.throws(() => liveSoil({ 20200301: -999 }, soil.sources), /no soil temperature/);
});

test('fetchField: soil GET plus a UTC weather GET, and a failed answer becomes a message', async () => {
  const calls = [], ok = async u => { calls.push(u); return { ok: true, json: async () => fx }; };
  await assert.rejects(fetchField({ lat: 45.5, lon: -73.7 }, { soil, fieldRisk: fr }, { fetch: ok }), /enough years/);   // the fixture holds one spring
  assert.equal(calls.length, 2);
  assert.ok(calls.some(u => /IMERG_PRECTOT/.test(u) && /time-standard=UTC/.test(u)));
  await assert.rejects(fetchField({ lat: 0, lon: 0 }, { soil, fieldRisk: fr }, { fetch: async () => ({ ok: false, status: 502 }) }), /answered 502/);
  await assert.rejects(fetchField({ lat: 0, lon: 0 }, { soil, fieldRisk: fr }, { fetch: async () => ({ ok: true, json: async () => ({}) }) }), /no data/);
});

test('weatherURL asks for IMERG in UTC days; weatherFrom drops fill and rejects a mostly empty series', () => {
  const u = new URL(weatherURL({ lat: 45.5, lon: -73.7 }));
  assert.equal(u.searchParams.get('time-standard'), 'UTC');
  assert.equal(u.searchParams.get('start'), '20010101');
  const p = { IMERG_PRECTOT: { 20010101: 1.26, 20010102: 0 }, T2M_MAX: { 20010101: -3, 20010102: -999 }, T2M_MIN: { 20010101: -9, 20010102: -12 } };
  const w = weatherFrom(p, { lat: 45.5, lon: -73.7 });
  assert.deepEqual([w.start, w.rain, w.tmax], ['2001-01-01', [1.3, 0], [-3, null]]);
  assert.equal(weatherFrom({ IMERG_PRECTOT: { 20010101: -999, 20010102: -999 } }, {}), null);
});
