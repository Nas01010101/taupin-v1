import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { effectFor, riskView, trapWindow, gpsToCell } from '../js/risk.js';
import { esc } from '../js/ui.js';

const data = p => JSON.parse(readFileSync(new URL(`../data/${p}`, import.meta.url), 'utf8'));
const risk = data('risk.json'), soil = data('soil.json'), field = data('field.json');
const ww = { id: 'wireworm', name: 'Wireworm', unclear: false, prob: 0.9 };

test('baseline table has 3 rotations x 5 years, every cell with a cited trace', () => {
  const v = riskView(risk, 'upland');
  assert.equal(v.rows.length, 3);
  for (const r of v.rows) {
    assert.equal(r.years.length, 5);
    for (const y of r.years) assert.ok(y.trace.length && y.trace.every(t => /\[.+\]$/.test(t)));
  }
  assert.equal(v.rxCount, 0);
  assert.ok(v.rows.every(r => r.years.every(y => y.ifTrap === null)));
});

test('a wireworm photo adds the trap scenario without changing the baseline levels', () => {
  const before = riskView(risk, 'upland'), after = riskView(risk, 'upland', [effectFor(ww)]);
  assert.deepEqual(after.rows.map(r => r.years.map(y => y.wireworm)), before.rows.map(r => r.years.map(y => y.wireworm)));
  const first = after.rows.find(r => r.rotation === 'B_corn_soy_wheat').years[0];
  assert.deepEqual([first.wireworm, first.ifTrap.wireworm, first.ifTrap.rx], ['MODERATE', 'HIGH', true]);
  assert.ok(after.rxIfTrap > after.rxCount);
});

test('rootworm photo flags corn-after-corn years only', () => {
  const v = riskView(risk, 'upland', [effectFor({ id: 'corn_rootworm', name: 'CRW', unclear: false })]);
  const a = v.rows.find(r => r.rotation === 'A_continuous_corn').years.map(y => y.crwFlag);
  assert.deepEqual(a, [false, true, true, true, true]);
  assert.ok(v.rows.find(r => r.rotation === 'B_corn_soy_wheat').years.every(y => !y.crwFlag));
});

test('unclear and unknown classes leave the table unchanged', () => {
  assert.equal(effectFor({ ...ww, unclear: true }).kind, 'unclear');
  assert.equal(effectFor({ id: 'new_thing', name: 'New', unclear: false }).kind, 'unscored');
  const v = riskView(risk, 'pocket', [effectFor({ ...ww, unclear: true })]);
  assert.ok(!v.ww && v.rows.every(r => r.years.every(y => !y.ifTrap)));
});

test('trap window summary from soil.json', () => {
  const t = trapWindow(soil);
  assert.equal(t.mean12, soil.trap_12C_mean);
  assert.equal(t.lastYear, '2025');
});

test('gps maps into the parcel and rejects outside points', () => {
  const p = field.parcel, mid = { latitude: (p.nw[0] + p.se[0]) / 2, longitude: (p.nw[1] + p.se[1]) / 2 };
  const c = gpsToCell(mid, p);
  assert.ok(Math.abs(c.row - (p.size - 1) / 2) <= 1 && Math.abs(c.col - (p.size - 1) / 2) <= 1);
  assert.equal(gpsToCell({ latitude: 0, longitude: 0 }, p), null);
});

test('escape covers html metacharacters', () => {
  assert.equal(esc('<img src=x onerror="a">&\''), '&lt;img src=x onerror=&quot;a&quot;&gt;&amp;&#39;');
  assert.equal(esc(null), '');
});

test('the risk headline holds: by 2028 rotating out of corn is below corn every year, both zones', () => {
  const rank = { NONE: 0, LOW: 1, MODERATE: 2, HIGH: 3 };
  for (const z of ['upland', 'pocket']) {
    const v = riskView(risk, z), lvl = k => rank[v.rows.find(r => r.rotation === k).years[2].wireworm];
    assert.ok(lvl('B_corn_soy_wheat') < lvl('A_continuous_corn') && lvl('C_with_buckwheat') < lvl('A_continuous_corn'), z);
  }
});
