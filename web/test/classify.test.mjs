import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { roundHalfEven, targetSize, resizeWeights, preprocess, softmax, decide, formatAnswer, checkLabels, UNCLEAR } from '../js/classify.js';
import { loadModel, classifyPixels } from '../js/model.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const fx = p => `${root}tests/fixtures/${p}`;
const labels = JSON.parse(readFileSync(fx('model/labels.json'), 'utf8'));

// Same pattern as tests/fixtures/make_fixture.py golden_image().
function golden(w, h) {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const p = (y * w + x) * 4;
    d[p] = (x * 7 + y * 3) % 256; d[p + 1] = (x * y) % 256; d[p + 2] = (x + 2 * y) % 256; d[p + 3] = 255;
  }
  return d;
}
const solid = (w, h, rgb) => { const d = new Uint8ClampedArray(w * h * 4); for (let i = 0; i < w * h; i++) d.set([...rgb, 255], i * 4); return d; };

test('round half to even matches Python', () => {
  assert.deepEqual([0.5, 1.5, 2.5, 2.4, 2.6, 3.5].map(roundHalfEven), [0, 2, 2, 2, 3, 4]);
});

test('short side becomes S, long side truncated', () => {
  assert.deepEqual(targetSize(37, 53, 8), [8, 11]);
  assert.deepEqual(targetSize(4000, 3000, 224), [298, 224]);
});

test('resize weights sum to one', () => {
  for (const r of resizeWeights(4000, 298, 37, 224)) assert.ok(Math.abs(r.w.reduce((a, b) => a + b, 0) - 1) < 1e-9);
});

test('preprocess matches the Python golden tensor', () => {
  const g = JSON.parse(readFileSync(fx('preprocess_golden.json'), 'utf8'));
  const x = preprocess(golden(g.w, g.h), g.w, g.h, labels);
  assert.equal(x.length, g.x.length);
  let worst = 0;
  for (let i = 0; i < x.length; i++) worst = Math.max(worst, Math.abs(x[i] - g.x[i]));
  assert.ok(worst < 1e-4, `max diff ${worst}`);
});

test('softmax with temperature', () => {
  const p = softmax([2, 0, 0]);
  assert.ok(Math.abs(p.reduce((a, b) => a + b) - 1) < 1e-12 && p[0] > 0.78);
  assert.ok(softmax([2, 0, 0], 4)[0] < p[0]);
});

test('abstain below threshold', () => {
  assert.equal(decide([0.7, 0.2, 0.1], labels).unclear, false);
  const r = decide([0.5, 0.3, 0.2], labels);
  assert.equal(r.unclear, true);
  assert.ok(formatAnswer(r).startsWith(UNCLEAR));
  assert.equal(formatAnswer(decide([0.9, 0.05, 0.05], labels)), 'Red test bug (90.0 %), pest');
});

test('labels contract is checked', () => {
  assert.throws(() => checkLabels({ classes: [] }));
  assert.equal(checkLabels(labels), labels);
});

test('missing model is reported, not thrown', async () => {
  const fetchFn = async () => ({ ok: false, status: 404 });
  const m = await loadModel({ ort: {}, fetchFn });
  assert.equal(m.status, 'missing');
});

test('fixture model runs in onnxruntime-web and picks the dominant colour', async () => {
  const ort = await import(`${root}web/vendor/ort/ort.wasm.min.mjs`);
  const fetchFn = async url => ({ ok: true, json: async () => JSON.parse(readFileSync(fx('model/labels.json'), 'utf8')) });
  const m = await loadModel({ ort, fetchFn, wasmPaths: `${root}web/vendor/ort/`, modelBytes: readFileSync(fx('model/taupin.onnx')) });
  assert.equal(m.status, 'ready', m.reason);
  assert.equal((await classifyPixels(m, solid(40, 30, [230, 20, 20]), 40, 30)).id, 'red_bug');
  assert.equal((await classifyPixels(m, solid(30, 40, [20, 20, 230]), 30, 40)).id, 'blue_bug');
  const grey = await classifyPixels(m, solid(16, 16, [128, 128, 128]), 16, 16);
  assert.equal(grey.unclear, true);
});
