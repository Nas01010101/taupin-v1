import { test } from 'node:test';
import assert from 'node:assert/strict';
import { metricsHTML, metricsRows, resultHTML, galleryHTML } from '../js/ui.js';

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
