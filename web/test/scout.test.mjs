import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { THRESHOLDS, cleanCount, liftSummary, verdict, trapsCSV, trapsGPX, trapsGeoJSON, recordText } from '../js/scout.js';
import { trapWindow } from '../js/risk.js';

const field = JSON.parse(readFileSync(new URL('../data/field.json', import.meta.url)));
const soil = JSON.parse(readFileSync(new URL('../data/soil.json', import.meta.url)));
const fill = (n, lift = 0, base = {}) => { for (const t of field.traps) (base[t.id] ??= [])[lift] = n; return base; };

test('a count is a whole number of larvae or nothing', () => {
  assert.equal(cleanCount('3'), 3);
  assert.equal(cleanCount(0), 0);
  for (const bad of ['', null, undefined, '-1', '2.5', 'abc', '1e9']) assert.equal(cleanCount(bad), null);
});

test('each lift is compared on its own, and a mean equal to the threshold counts as reached', () => {
  const at = liftSummary(field.traps, { counts: fill(3), genus: 'hypnoidus' });
  assert.equal(at.lifts[0].mean, 3);
  assert.equal(at.reached, true);
  // 2 per trap is under 3 for Hypnoidus and over 1 for Agriotes: the species decides.
  assert.equal(liftSummary(field.traps, { counts: fill(2), genus: 'hypnoidus' }).reached, false);
  assert.equal(liftSummary(field.traps, { counts: fill(2), genus: 'agriotes' }).reached, true);
  // Two low lifts and one high one: the high lift alone reaches the threshold, not the average.
  const s = liftSummary(field.traps, { counts: fill(4, 2, fill(0, 1, fill(0))), genus: 'hypnoidus' });
  assert.deepEqual(s.lifts.map(l => l.reached), [false, false, true]);
  assert.equal(s.reached, true);
});

test('blank traps are left out of the mean and an unknown species falls back to the default', () => {
  const s = liftSummary(field.traps, { counts: { A: ['4'], B: [''], C: ['x'] }, genus: 'nope' });
  assert.equal(s.genus, 'hypnoidus');
  assert.deepEqual([s.lifts[0].n, s.lifts[0].total, s.lifts[1]], [1, 4, null]);
});

test('the verdict stops at the count and names what is missing', () => {
  const min = field.trap_rules.min_traps;
  assert.match(verdict(liftSummary(field.traps, { counts: {} }), min), /No trap counted yet/);
  const one = verdict(liftSummary(field.traps, { counts: fill(0) }), min);
  assert.match(one, /1 of 3 lifts counted/);
  const three = verdict(liftSummary(field.traps, { counts: fill(0, 2, fill(1, 1, fill(0))) }), min);
  assert.match(three, /Three lifts counted, none at/);
  assert.match(three, /The agronomist decides/);
  const hit = verdict(liftSummary(field.traps, { counts: fill(5) }), min);
  assert.match(hit, /Lift 1 is at or above/);
  assert.match(hit, /the agronomist decides which/);
  assert.doesNotMatch(hit + three, /prescri|should|must|safe|no need/i);
  assert.match(verdict(liftSummary(field.traps, { counts: { A: [9] } }), min), new RegExp(`Lift 1 has 1 of the ${min} traps`));
});

test('trap files carry every trap in decimal degrees', () => {
  const sheet = { counts: fill(2), dates: ['2026-05-18'] };
  const csv = trapsCSV(field, sheet).trim().split('\n');
  assert.equal(csv[0], 'trap,zone,latitude,longitude,lift1_2026-05-18,lift2,lift3');
  assert.equal(csv.length, field.traps.length + 1);
  assert.match(csv[1], /^A,\d,45\.\d{6},-73\.\d{6},2,,$/);
  const gpx = trapsGPX(field);
  assert.equal(gpx.match(/<wpt /g).length, field.traps.length);
  assert.match(gpx, /<wpt lat="45\.\d{6}" lon="-73\.\d{6}"><name>Trap A<\/name>/);
  const gj = JSON.parse(trapsGeoJSON(field, sheet));
  assert.equal(gj.features.length, field.traps.length);
  const [lon, lat] = gj.features[0].geometry.coordinates;
  assert.ok(lon < -73 && lat > 45, 'GeoJSON order is longitude, latitude');
  assert.deepEqual(gj.features[0].properties.wireworms_per_lift, [2, null, null]);
});

test('trap files escape names that come from the field file', () => {
  const odd = { traps: [{ id: 'A"<&,', zone: '1', lat: 45.5, lon: -73.7 }] };
  assert.match(trapsGPX(odd), /Trap A&quot;&lt;&amp;,/);
  assert.match(trapsCSV(odd, {}), /^"A""<&,",1,/m);
});

test('the record lists the traps, the count, the sources and who decides', () => {
  const txt = recordText({ date: '2026-05-25', field, window: trapWindow(soil), sheet: { counts: fill(1), dates: ['2026-05-25'], genus: 'hypnoidus' },
    rank: { text: 'Middle', year: '2025', n: 82 }, photos: ['Wireworm, 97.5 %, upland'] });
  for (const t of field.traps) assert.ok(txt.includes(t.lat.toFixed(6)) && txt.includes(t.lon.toFixed(6)), `trap ${t.id}`);
  assert.match(txt, /NASA POWER TSOIL1, 1995 to 2025/);
  assert.match(txt, /Lift 1: 10 wireworms in 10 traps, 1 per trap, lifted 2026-05-25/);
  assert.match(txt, /Middle third for 2025 among the 82 Quebec fields/);
  assert.match(txt, /Wireworm, 97\.5 %, upland/);
  assert.match(txt, /cerom\.qc\.ca\/vffqc/);
  assert.match(txt, /The agronomist signs\./);
  assert.doesNotMatch(txt, /undefined|NaN|null/);
  assert.match(recordText({ date: 'd', field, window: trapWindow(soil), sheet: { counts: {} }, rank: null }), /Not available for this year/);
});

test('thresholds cover the four genera of the trap method', () => {
  assert.deepEqual(Object.keys(THRESHOLDS).sort(), ['agriotes', 'hypnoidus', 'limonius', 'melanotus']);
});
