import { test } from 'node:test';
import assert from 'node:assert/strict';
import { metricsHTML, metricsRows, resultHTML, galleryHTML, trapsHTML, countResultHTML } from '../js/ui.js';
import { liftSummary } from '../js/scout.js';

test('metrics read the model splits only, never the baselines', () => {
  const m = { version: 'v1', model: { val: { accuracy: 0.9, n: 10 }, test: { accuracy: 0.8, n: 5 } },
    clip_zero_shot: { x: { val: { accuracy: 0.5 } } } };
  assert.deepEqual(metricsRows(m).map(r => r.split), ['Validation', 'Test (sealed)']);
  assert.match(metricsHTML(m), /80\.0 %/);
  assert.doesNotMatch(metricsHTML(m), /50\.0 %/);
  assert.equal(metricsHTML({}), 'No accuracy figures in model/metrics.json yet.');
});

test('result states render and escape file-derived names', () => {
  for (const kind of ['idle', 'loading', 'missing', 'error']) assert.equal(typeof resultHTML({ kind, name: '<b>x</b>', message: '<i>' }), 'string');
  assert.doesNotMatch(resultHTML({ kind: 'loading', name: '<b>x</b>' }), /<b>x<\/b>/);
  const decision = { id: 'a', name: 'Blue <b>test</b> bug', prob: 0.9, unclear: false, top: [{ name: 'Blue <b>test</b> bug', prob: 0.9 }] };
  const html = resultHTML({ kind: 'result', decision, effect: { kind: 'none', note: 'n' }, thumb: 'data:,', abstain: 0.5 });
  assert.match(html, /Blue &lt;b&gt;test&lt;\/b&gt; bug/);
  assert.doesNotMatch(html, /<b>test<\/b>/);
});

test('gallery links only http(s) sources', () => {
  const html = galleryHTML([{ file: 'g.jpg', caption: 'c', credit: 'x', source: 'javascript:alert(1)', licence: 'CC0' }], null);
  assert.doesNotMatch(html, /javascript:/);
});

test('an unclear photo shows the lab route, a named one does not', () => {
  const base = { id: 'a', name: 'Wireworm', prob: 0.5, top: [{ name: 'Wireworm', prob: 0.5 }] };
  const st = unclear => ({ kind: 'result', decision: { ...base, unclear }, effect: { kind: 'none', note: 'n' }, thumb: 'data:,', abstain: 0.89 });
  const html = resultHTML(st(true));
  assert.match(html, /online request form/);
  assert.match(html, /phytolab@mapaq\.gouv\.qc\.ca/);
  assert.match(html, /Taupin sends nothing/);
  assert.doesNotMatch(resultHTML(st(false)), /online request form/);
});

test('count sheet has one input per trap per lift and escapes saved values', () => {
  const field = { traps: [{ id: 'A', zone: '1', lat: 45.5, lon: -73.7, row: 1, col: 1 }], trap_rules: { min_traps: 10, spacing_m: 25, source: 's', note: 'n' }, layers: [] };
  const html = trapsHTML(field, { counts: { A: ['"><b>'] }, dates: ['"><i>'], genus: 'agriotes' });
  assert.equal(html.match(/data-trap="A"/g).length, 3);
  assert.doesNotMatch(html, /<b>|<i>/);
  assert.match(html, /value="agriotes" selected/);
  const res = countResultHTML(liftSummary(field.traps, { counts: { A: [4] }, genus: 'agriotes' }), 10);
  assert.match(res, /class="callout"/);
  assert.match(res, /Lift 1 has 1 of the 10 traps/);
});
