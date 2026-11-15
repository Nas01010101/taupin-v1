import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { score, rankOf, powerFeatures, outsideTraining, fieldRanking } from '../js/fieldrisk.js';
import { fieldRankHTML } from '../js/ui.js';

const data = p => JSON.parse(readFileSync(new URL(`../data/${p}`, import.meta.url), 'utf8'));
const model = data('risk_model.json'), fr = data('field_risk.json');

test('score at the training means is the intercept, as in fieldrisk.py', () => {
  const x = Object.fromEntries(model.features.map(f => [f.name, f.mean]));
  x.forage_years = Math.expm1(x.forage_years);
  assert.ok(Math.abs(score(model, x) - model.intercept) < 1e-9);
  assert.throws(() => score(model, { ...x, gwet_spring: undefined }), /gwet_spring/);
});

test('rank cut points: at or below the first is low, above the second is high', () => {
  assert.equal(rankOf(-5, [-3, -2]), 'low');
  assert.equal(rankOf(-3, [-3, -2]), 'low');
  assert.equal(rankOf(-2.5, [-3, -2]), 'mid');
  assert.equal(rankOf(0, [-3, -2]), 'high');
});

test('POWER windows match the Python bake for every baked year', () => {
  const p = { GWETROOT: { '20260401': 0.8, '20260531': 0.9, '20260601': 0.1, '20260402': -999 },
    TSOIL1: { '20251201': -3, '20260110': -11.2, '20260401': -20 } };
  assert.deepEqual(powerFeatures(p, 2026), { gwet_spring: 0.85, tsoil_winter_min_c: -11.2 });
  assert.deepEqual(powerFeatures({}, 2026), { gwet_spring: null, tsoil_winter_min_c: null });
});

test('every baked year ranks, and extrapolation is named', () => {
  for (const y of Object.keys(fr.per_year)) {
    const r = fieldRanking(model, fr, { year: y });
    assert.ok(['low', 'mid', 'high'].includes(r.rank));
    assert.deepEqual(r.outside, outsideTraining(r.inputs, fr.training_range));
  }
  assert.deepEqual(outsideTraining({ gwet_spring: 0.99, forage_years: 0, tsoil_winter_min_c: -10 }, fr.training_range), ['gwet_spring']);
  assert.equal(fieldRanking(model, fr, { year: '1900' }), null);
});

test('the ranking text never states a probability and shows the validation numbers', () => {
  const html = fieldRankHTML(fieldRanking(model, fr, { year: '2026', forageYears: 3 }), model);
  assert.match(html, /not a probability and not a decision/);
  assert.match(html, /AUC 0\.80 leaving one field out \(95 % CI 0\.63 to 0\.93\)/);
  assert.match(html, /0\.57 on the same fields/);
  assert.match(html, /Brier score 0\.110 against 0\.116/);
  assert.doesNotMatch(html, /\d %<\/td>|probability of/i);
});
