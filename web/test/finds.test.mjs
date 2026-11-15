import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeFind, loadFinds, saveFinds, clearFinds, latestSite, gridFit, cellOf, splitFinds, findsCSV, findsGeoJSON, findsHTML, exifGPS, FINDS_KEY } from '../js/finds.js';
import { recordText, findLine } from '../js/scout.js';
import { trapWindow } from '../js/risk.js';

const field = JSON.parse(readFileSync(new URL('../data/field.json', import.meta.url)));
const soil = JSON.parse(readFileSync(new URL('../data/soil.json', import.meta.url)));
const dec = { name: 'Wireworm', prob: 0.97123, unclear: false };
const time = new Date('2026-05-14T14:32:10Z');
const memory = () => { const m = new Map(); return { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: k => m.delete(k), m }; };

test('a find carries the position, the answer and an optional count', () => {
  const f = makeFind({ lat: 45.5013123, lon: -73.7651456, accuracy_m: 8.4, source: 'device' }, dec, { count: '3', time });
  assert.deepEqual(f, { lat: 45.501312, lon: -73.765146, accuracy_m: 8, source: 'device', time: '2026-05-14T14:32:10.000Z',
    label: 'Wireworm', confidence: 0.9712, answered_or_unclear: 'answered', count: 3 });
  assert.equal(makeFind({ lat: 1, lon: 2 }, { ...dec, unclear: true }, { count: '' }).answered_or_unclear, 'unclear');
  assert.equal(makeFind({ lat: 1, lon: 2 }, dec, { count: '-2' }).count, null);
  assert.equal(makeFind({ lat: 91, lon: 0 }, dec), null);
  assert.equal(makeFind(null, dec), null);
});

test('storage that throws or holds junk gives an empty list, and saving survives a blocked store', () => {
  const bad = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
  assert.deepEqual(loadFinds(bad), []);
  assert.deepEqual(loadFinds(null), []);
  assert.equal(saveFinds(bad, []), false);
  assert.equal(clearFinds(bad), false);
  const s = memory();
  s.setItem(FINDS_KEY, '{not json');
  assert.deepEqual(loadFinds(s), []);
  const f = makeFind({ lat: 45.5, lon: -73.76 }, dec, { time });
  assert.equal(saveFinds(s, [f, { lat: 'x' }]), true);
  assert.deepEqual(loadFinds(s), [f]);
  assert.equal(clearFinds(s), true);
  assert.deepEqual(loadFinds(s), []);
});

test('the latest find is the default field position, to 4 decimals', () => {
  assert.equal(latestSite([]), null);
  assert.deepEqual(latestSite([makeFind({ lat: 1, lon: 2 }, dec), makeFind({ lat: 46.123456, lon: -72.98767 }, dec)]), { lat: 46.1235, lon: -72.9877 });
});

test('trap points map back to their own grid cells, and far points fall outside the square', () => {
  const fit = gridFit(field.traps);
  for (const t of field.traps) {
    const c = cellOf(field, t.lat, t.lon, fit);
    assert.ok(Math.abs(c.row - t.row) <= 1 && Math.abs(c.col - t.col) <= 1, `${t.id}: ${JSON.stringify(c)}`);
  }
  assert.equal(cellOf(field, 46.81, -71.21), null);   // Quebec City
  const { inside, outside } = splitFinds(field, [makeFind(field.traps[0], dec), makeFind({ lat: 46.81, lon: -71.21 }, dec)]);
  assert.equal(inside.length, 1); assert.equal(outside.length, 1); assert.equal(outside[0].i, 1);
});

test('CSV and GeoJSON exports hold every field of every find', () => {
  const f = makeFind({ lat: 45.5, lon: -73.76, accuracy_m: 5 }, { name: 'Ground beetle, "adult"', prob: 0.5, unclear: true }, { time, count: 2 });
  const csv = findsCSV([f]).trim().split('\n');
  assert.equal(csv[0], 'time,lat,lon,accuracy_m,source,label,confidence,answered_or_unclear,count');
  assert.equal(csv[1], '2026-05-14T14:32:10.000Z,45.5,-73.76,5,device,"Ground beetle, ""adult""",0.5,unclear,2');
  const g = JSON.parse(findsGeoJSON([f]));
  assert.deepEqual(g.features[0].geometry.coordinates, [-73.76, 45.5]);
  assert.equal(g.features[0].properties.count, 2);
});

test('the finds panel escapes every value and offers export and delete only when there are finds', () => {
  assert.equal(findsHTML({ canSave: false, finds: [], inside: [], outside: [] }), '');
  assert.match(findsHTML({ canSave: true, finds: [], inside: [], outside: [] }), /Save where I found it/);
  const f = makeFind({ lat: 46.81, lon: -71.21 }, { name: '<img src=x onerror=alert(1)>', prob: 0.9, unclear: false }, { time });
  const html = findsHTML({ canSave: false, finds: [f], inside: [], outside: [{ ...f, i: 0 }] });
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
  assert.match(html, /Export finds \(CSV\)/); assert.match(html, /Delete all finds/);
  assert.ok(!html.includes('style="'));
});

test('the scouting record lists the saved finds', () => {
  const f = makeFind({ lat: 45.501312, lon: -73.765146, accuracy_m: 8, source: 'device' }, dec, { time, count: 3 });
  assert.equal(findLine(f), '2026-05-14 14:32 UTC, Wireworm (97.1 %), 45.50131 N, 73.76515 W (within 8 m), 3 found');
  const base = { date: '2026-05-14', field, window: trapWindow(soil), sheet: { counts: {} }, rank: null };
  assert.match(recordText({ ...base, finds: [f] }), /Finds saved on this device\n {2}2026-05-14 14:32 UTC, Wireworm/);
  assert.match(recordText(base), /Finds saved on this device\n {2}None\./);
});

// A minimal JPEG with an EXIF block: IFD0 -> GPS IFD with 45 30' 4.68" N, 73 45' 54.36" W.
function jpegWithGPS(le = true) {
  const tiff = new DataView(new ArrayBuffer(200));
  const u16 = (o, v) => tiff.setUint16(o, v, le), u32 = (o, v) => tiff.setUint32(o, v, le);
  u16(0, le ? 0x4949 : 0x4d4d); u16(2, 42); u32(4, 8);
  u16(8, 1); u16(10, 0x8825); u16(12, 4); u32(14, 1); u32(18, 26); u32(22, 0);   // IFD0: one entry, GPS IFD at 26
  const gps = 26; u16(gps, 4);
  const entry = (i, tag, type, count, value) => { const e = gps + 2 + 12 * i; u16(e, tag); u16(e + 2, type); u32(e + 4, count); u32(e + 8, value); };
  entry(0, 1, 2, 2, 0); tiff.setUint8(gps + 2 + 8, 'N'.charCodeAt(0));
  entry(1, 2, 5, 3, 100);
  entry(2, 3, 2, 2, 0); tiff.setUint8(gps + 2 + 24 + 8, 'W'.charCodeAt(0));
  entry(3, 4, 5, 3, 130);
  [[45, 1], [30, 1], [468, 100]].forEach(([n, d], i) => { u32(100 + 8 * i, n); u32(104 + 8 * i, d); });
  [[73, 1], [45, 1], [5436, 100]].forEach(([n, d], i) => { u32(130 + 8 * i, n); u32(134 + 8 * i, d); });
  const app1 = new Uint8Array([0xff, 0xe1, 0, 8 + 200, 0x45, 0x78, 0x69, 0x66, 0, 0]);
  return new Uint8Array([0xff, 0xd8, ...app1, ...new Uint8Array(tiff.buffer), 0xff, 0xd9]);
}

test('GPS is read from a JPEG EXIF block in either byte order, and absent GPS gives null', () => {
  for (const le of [true, false]) assert.deepEqual(exifGPS(jpegWithGPS(le)), { lat: 45.5013, lon: -73.7651 });
  assert.equal(exifGPS(new Uint8Array([0xff, 0xd8, 0xff, 0xd9])), null);
  assert.equal(exifGPS(new Uint8Array([0x89, 0x50, 0x4e, 0x47])), null);
});
