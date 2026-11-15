import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { VIEWS, decode, ramp, span, colorOf, legend, resolutionText } from '../js/layers.js';
import { layerLegendHTML, trapsHTML } from '../js/ui.js';

const web = fileURLToPath(new URL('../', import.meta.url));
const field = JSON.parse(readFileSync(`${web}data/field.json`, 'utf8'));
const L = Object.fromEntries(field.layers.map(l => [l.key, l]));
const load = key => {
  const b = readFileSync(`${web}data/${L[key].file}`);
  return decode(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), L[key].encoding);
};

test('decode applies offset and scale, nodata is NaN', () => {
  const v = decode(new Uint8Array([0, 10, 255]).buffer, { dtype: 'u1', offset: 1, scale: 0.5, nodata: 255 });
  assert.deepEqual([v[0], v[1]], [1, 6]);
  assert.ok(Number.isNaN(v[2]));
  const h = decode(new Uint16Array([0, 65535]).buffer, { dtype: 'u2', offset: 18, scale: 0.01, nodata: 65535 });
  assert.equal(h[0], 18);
  assert.ok(Number.isNaN(h[1]));
});

test('baked layers decode to their manifest range', () => {
  for (const v of VIEWS) assert.ok(L[v.layer], v.layer);
  const h = load('height');
  assert.equal(h.length, field.parcel.size ** 2);
  let lo = Infinity, hi = -Infinity;
  for (const x of h) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
  assert.ok(Math.abs(lo - L.height.range[0]) < 0.01 && Math.abs(hi - L.height.range[1]) < 0.01);
  assert.equal(load('ndvi').length, L.ndvi.size ** 2);
  const soil = load('soil'), ids = new Set(L.soil.classes.map(c => c.id));
  for (const x of soil) assert.ok(Number.isNaN(x) || ids.has(x));
});

test('ramps hit their end stops and temperature centres on the parcel mean', () => {
  assert.deepEqual(ramp('ndvi', 0), [150, 112, 70]);
  assert.deepEqual(ramp('ndvi', 2), [40, 120, 50]);
  const [lo, hi] = span(L.lst);
  assert.equal(lo, -hi);
  assert.deepEqual(colorOf(L.lst, 0), [240, 238, 228]);
  assert.equal(colorOf(L.twi, NaN), null);
});

test('legend and resolution text never present satellite layers as 2 m', () => {
  assert.match(resolutionText(L.ndvi), /Native 30 m, shown as 30 m cells/);
  assert.match(resolutionText(L.lst), /Native 100 m, shown as 30 m cells/);
  assert.match(resolutionText(L.height), /1 m lidar, averaged to 2 m/);
  assert.equal(legend(L.twi).length, 3);
  assert.equal(legend(L.soil).length, L.soil.classes.length);
  const html = layerLegendHTML(L.lst);
  assert.match(html, /100 m/);
  assert.match(html, /Landsat/);
  assert.ok(!html.includes('style='));
});

test('legend escapes text from the manifest', () => {
  const bad = { ...L.soil, name: '<b>x</b>', classes: [{ ...L.soil.classes[0], symbol: '<img>' }] };
  const html = layerLegendHTML(bad);
  assert.ok(!html.includes('<b>x') && !html.includes('<img>'));
});

test('trap list gives every trap with decimal degrees and says zones are not risk', () => {
  const html = trapsHTML(field);
  for (const t of field.traps) assert.ok(html.includes(t.lat.toFixed(6)) && html.includes(t.lon.toFixed(6)));
  assert.match(html, /not a risk map/);
  assert.match(html, /no number of traps per hectare/);
  assert.match(html, /115269/);
});

test('no soil unit or zone is drawn in a blue that reads as water', () => {
  const water = L.soil.classes.find(c => c.components.every(p => p.name === 'Water'));
  const land = L.soil.classes.filter(c => c !== water).map(c => colorOf(L.soil, c.id).join());
  assert.equal(new Set(land).size, land.length);
  if (water) assert.ok(!land.includes(colorOf(L.soil, water.id).join()));   // not every square has a water unit
  assert.ok(!land.includes('90,156,214'));
});
