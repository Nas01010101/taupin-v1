import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ra, et0, kcAt, plantingDoy, cropYear, climatology, rotationMetrics, rank, versus, gaps } from '../js/soilwater.js';
import { riskView } from '../js/risk.js';

const data = p => JSON.parse(readFileSync(new URL(`../data/${p}`, import.meta.url), 'utf8'));
const crops = data('crops.json'), weather = data('weather.json'), risk = data('risk.json'), rot = data('rotations.json');
const close = (a, b, tol) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);

test('Ra and Hargreaves ET0 match the FAO-56 worked examples', () => {
  close(ra(-20, 246), 32.2, 0.1);                 // FAO-56 Example 8: 20 S, 3 September
  close(ra(45, 172), 41.5, 1);                   // June solstice at 45 N
  assert.equal(et0(null, 10, 45, 100), null);
  close(et0(30, 15, 45, 196), 0.0023 * 40.3 * Math.sqrt(15) * 0.408 * ra(45, 196), 1e-9);
});

test('Kc curve: flat, rising, flat, falling, then zero', () => {
  const c = crops.crops.corn, [li, ld, lm, ll] = c.stages;
  assert.equal(kcAt(c, 0), 0.3);
  close(kcAt(c, li + ld / 2), (0.3 + 1.2) / 2, 1e-9);
  assert.equal(kcAt(c, li + ld + 1), 1.2);
  close(kcAt(c, li + ld + lm + ll - 1e-9), 0.35, 1e-6);
  assert.equal(kcAt(c, li + ld + lm + ll), 0);
});

test('sowing day is the first day from 1 March with a 10-day mean at the threshold', () => {
  const days = Array.from({ length: 200 }, (_, i) => ({ doy: i + 1, tmax: i < 120 ? 5 : 20, tmin: i < 120 ? 0 : 10 }));
  assert.equal(plantingDoy(days, 15), 130);      // the first all-warm 10-day window ends on day 130
  assert.equal(plantingDoy(days, 30), null);
  const early = days.map(d => ({ ...d, tmax: 30, tmin: 20 }));
  assert.equal(plantingDoy(early, 13), 60);       // nothing before 1 March
});

test('heavy rain counts only on bare soil, above 0 C, April to November', () => {
  const c = { kc: [0.3, 1.2, 0.35], stages: [10, 10, 10, 10], plant_t10: 20 };
  const days = Array.from({ length: 365 }, (_, i) => ({ doy: i + 1, tmax: i >= 100 ? 25 : 5, tmin: i >= 100 ? 15 : -5, rain: 0 }));
  for (const d of [95, 115, 125, 200, 340]) days[d - 1].rain = 30;   // plant 110: 115 bare (before cover at 120), 125 covered
  const y = cropYear(days, c, 45);
  assert.deepEqual([y.plant, y.harvest, y.bareHeavy], [110, 150, 2]);   // 95 is cold, 340 after 30 Nov
});

test('demo climatology: 25 years, corn sown after wheat, buckwheat left as a gap', () => {
  const cl = climatology(weather, crops.crops, weather.site.lat, crops.heavy_rain_mm);
  assert.deepEqual([cl.years, cl.n], [[2001, 2025], 25]);
  assert.ok(cl.crops.wheat.plant < cl.crops.corn.plant);
  assert.ok(cl.crops.corn.plant > 120 && cl.crops.corn.plant < 160);
  assert.ok(cl.crops.corn.need > 300 && cl.crops.corn.need < 700);
  assert.ok(cl.crops.soybean.deficitDry >= cl.crops.soybean.deficit);
  assert.equal(cl.crops.buckwheat, null);
});

test('rotation totals, ranking by priority, and benefits against the current rotation', () => {
  const cl = climatology(weather, crops.crops, weather.site.lat, crops.heavy_rain_mm);
  const view = riskView(risk, 'upland');
  const rows = view.rows.map(r => ({ id: r.rotation, metrics: rotationMetrics(risk.rotations[r.rotation], cl, crops, r) }));
  const byId = Object.fromEntries(rows.map(r => [r.id, r.metrics]));
  assert.equal(byId.A_continuous_corn.total.n, 5 * 145);
  assert.equal(byId.D_corn_soy.total.n, 145 + 15 + 120 + 15 + 120);   // soybean leaves 25 kg N/ha to the next corn
  assert.equal(byId.C_with_buckwheat.unknown.water, 1);
  assert.ok(byId.A_continuous_corn.total.pest > byId.B_corn_soy_wheat.total.pest);
  const all = rank(rows, ['pests', 'water', 'soil', 'nitrogen', 'organic']);
  assert.equal(all.at(-1).id, 'C_with_buckwheat');   // gaps on water and nitrogen: ranked after the complete ones
  assert.equal(all.at(-1).complete, false);
  const pestFirst = rank(rows, ['pests']);
  assert.notEqual(pestFirst[0].id, 'A_continuous_corn');
  assert.equal(pestFirst.at(-1).id, 'A_continuous_corn');
  const nFirst = rank(rows, ['nitrogen']);
  assert.equal(byId.C_with_buckwheat.total.n, null);   // buckwheat leaves no sourced N credit: the sum stays unknown
  assert.deepEqual(nFirst.slice(-2).map(r => r.id), ['A_continuous_corn', 'C_with_buckwheat']);   // unknown ranks last
  assert.ok(nFirst.slice(0, -1).every((r, i) => i === 0 || r.score <= nFirst[i - 1].score));
  const b = versus(byId.B_corn_soy_wheat, byId.A_continuous_corn);
  assert.ok(b.some(x => x.good && /nitrogen/.test(x.text)));
  assert.deepEqual(versus(byId.A_continuous_corn, byId.A_continuous_corn), []);
});

test('every rotation has a card; gaps list unsourced and assumed values', () => {
  for (const id of Object.keys(risk.rotations)) {
    const c = rot.rotations[id];
    assert.ok(c && c.why && c.evidence.length && c.risks.length && c.gaps.length, id);
  }
  assert.ok(rot.rotations[rot.default_current]);
  const g = gaps(risk.rotations.C_with_buckwheat, crops);
  assert.ok(g.some(t => /Buckwheat: no sourced water use/.test(t)));
  assert.ok(g.some(t => /Soybean: assumption/.test(t)));
  assert.ok(!gaps(['corn'], crops).length);
});

test('every crop value has a source key that exists, or is null', () => {
  for (const c of Object.values(crops.crops)) {
    for (const k of ['kc_src', 'stages_src', 'usle_src', 'n_src', 'credit_src', 'yield_src', 'ratio_src']) {
      if (c[k] != null) assert.ok(crops.sources[c[k]], `${c.name} ${k}`);
    }
  }
});
