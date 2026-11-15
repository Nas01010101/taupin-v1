// Finds: where a photographed soil animal was found. Saved only when the farmer taps "Save where I
// found it", kept in this browser's localStorage and never sent anywhere. Pure functions except
// load/save, which take the storage object, so node --test can check every one.
import { esc } from './ui.js';
import { findLine } from './scout.js';

export const FINDS_KEY = 'taupin-finds';
export const MAX_FINDS = 500;

const round = (v, k) => Math.round(v * 10 ** k) / 10 ** k;
const okCoord = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

// One log entry. pos = { lat, lon, accuracy_m, source: 'device' | 'photo' }; decision from classify.js.
export function makeFind(pos, decision, { count = null, time = new Date() } = {}) {
  if (!pos || !okCoord(pos.lat, pos.lon) || !decision) return null;
  const n = Number(count);
  return {
    lat: round(pos.lat, 6), lon: round(pos.lon, 6),
    accuracy_m: Number.isFinite(pos.accuracy_m) ? Math.round(pos.accuracy_m) : null,
    source: pos.source === 'photo' ? 'photo' : 'device',
    time: time.toISOString(),
    label: String(decision.name), confidence: round(Number(decision.prob), 4),
    answered_or_unclear: decision.unclear ? 'unclear' : 'answered',
    count: count !== '' && count != null && Number.isInteger(n) && n >= 0 && n <= 999 ? n : null,
  };
}

// Storage can be missing or throw (private window, blocked site data): both give an empty list.
export function loadFinds(storage) {
  try {
    const list = JSON.parse(storage.getItem(FINDS_KEY));
    return Array.isArray(list) ? list.filter(f => f && okCoord(f.lat, f.lon)) : [];
  } catch { return []; }
}
export function saveFinds(storage, finds) {
  try { storage.setItem(FINDS_KEY, JSON.stringify(finds.slice(-MAX_FINDS))); return true; } catch { return false; }
}
export function clearFinds(storage) {
  try { storage.removeItem(FINDS_KEY); return true; } catch { return false; }
}

// The latest find, as the default position for the own-field NASA POWER lookup.
export function latestSite(finds) {
  const f = finds[finds.length - 1];
  return f ? { lat: round(f.lat, 4), lon: round(f.lon, 4) } : null;
}

// Affine fit (lat, lon) -> (row, col) by least squares on the trap points, which carry both.
// The grid is UTM, so this absorbs the small rotation against lines of latitude.
export function gridFit(traps) {
  const solve = key => {
    // Normal equations for v = a + b*lat + c*lon, centred for conditioning.
    const n = traps.length, mlat = traps.reduce((s, t) => s + t.lat, 0) / n, mlon = traps.reduce((s, t) => s + t.lon, 0) / n;
    let sxx = 0, sxy = 0, syy = 0, sxv = 0, syv = 0, mv = 0;
    for (const t of traps) mv += t[key] / n;
    for (const t of traps) {
      const x = t.lat - mlat, y = t.lon - mlon, v = t[key] - mv;
      sxx += x * x; sxy += x * y; syy += y * y; sxv += x * v; syv += y * v;
    }
    const det = sxx * syy - sxy * sxy;
    const b = (sxv * syy - syv * sxy) / det, c = (syv * sxx - sxv * sxy) / det;
    return (lat, lon) => mv + b * (lat - mlat) + c * (lon - mlon);
  };
  return { row: solve('row'), col: solve('col') };
}

// Grid cell of a point, or null when it falls outside the demo square.
export function cellOf(field, lat, lon, fit = gridFit(field.traps)) {
  const row = Math.round(fit.row(lat, lon)), col = Math.round(fit.col(lat, lon)), N = field.parcel.size;
  return row >= 0 && row < N && col >= 0 && col < N ? { row, col } : null;
}

export function splitFinds(field, finds) {
  const fit = gridFit(field.traps), inside = [], outside = [];
  finds.forEach((f, i) => { const cell = cellOf(field, f.lat, f.lon, fit); (cell ? inside : outside).push({ ...f, i, cell }); });
  return { inside, outside };
}

const COLS = ['time', 'lat', 'lon', 'accuracy_m', 'source', 'label', 'confidence', 'answered_or_unclear', 'count'];
const csvCell = v => (v == null ? '' : /[",\n\r]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
export const findsCSV = finds => [COLS.join(','), ...finds.map(f => COLS.map(k => csvCell(f[k])).join(','))].join('\n') + '\n';
export const findsGeoJSON = finds => JSON.stringify({ type: 'FeatureCollection', features: finds.map(f => ({
  type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] },
  properties: Object.fromEntries(COLS.filter(k => k !== 'lat' && k !== 'lon').map(k => [k, f[k] ?? null])),
})) }, null, 1) + '\n';

// The finds panel: the save buttons when a photo has a result, then what is logged.
export function findsHTML({ canSave, finds, inside, outside }) {
  const save = canSave
    ? '<div class="own-btn"><label class="small">How many with it (optional) <input id="find-count" type="number" min="0" max="999" step="1" inputmode="numeric"></label>'
      + '<button type="button" class="ghost" data-find="device">Save where I found it</button>'
      + '<button type="button" class="ghost" data-find="photo">Use the photo\'s GPS instead</button></div>'
      + '<p class="small muted">The position is read only when you tap, and kept on this device. Nothing is uploaded.</p>'
    : '';
  if (!finds.length) return save;
  const list = outside.length
    ? `<ul class="finds small">${outside.map(f => `<li>${esc(findLine(f))}</li>`).join('')}</ul>` : '';
  return save
    + `<p class="small">${esc(finds.length)} find${finds.length === 1 ? '' : 's'} saved on this device. `
    + `${esc(inside.length)} inside the demo square, shown as pins on the field${outside.length ? `; ${esc(outside.length)} outside it, listed here` : ''}.</p>`
    + list
    + '<div class="files"><button type="button" class="ghost" data-find="csv">Export finds (CSV)</button>'
    + '<button type="button" class="ghost" data-find="geojson">Export finds (GeoJSON)</button>'
    + '<button type="button" class="ghost" data-find="delete">Delete all finds</button></div>';
}

// GPS from a JPEG's EXIF block, or null. Read only when the farmer asks for it.
export function exifGPS(buf) {
  const v = new DataView(buf instanceof ArrayBuffer ? buf : buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
  if (v.byteLength < 4 || v.getUint16(0) !== 0xffd8) return null;
  let p = 2;
  while (p + 4 <= v.byteLength) {
    const marker = v.getUint16(p), len = v.getUint16(p + 2);
    if (marker === 0xffe1 && p + 10 <= v.byteLength && v.getUint32(p + 4) === 0x45786966) return tiffGPS(v, p + 10);
    if ((marker & 0xff00) !== 0xff00 || marker === 0xffda) return null;
    p += 2 + len;
  }
  return null;
}

function tiffGPS(v, t) {
  try {
    const le = v.getUint16(t) === 0x4949, u16 = o => v.getUint16(t + o, le), u32 = o => v.getUint32(t + o, le);
    const entries = ifd => { const n = u16(ifd); return Array.from({ length: n }, (_, i) => ifd + 2 + 12 * i); };
    const gpsEntry = entries(u32(4)).find(e => u16(e) === 0x8825);
    if (gpsEntry == null) return null;
    const tags = {};
    for (const e of entries(u32(gpsEntry + 8))) tags[u16(e)] = e;
    const ref = tag => (tags[tag] != null ? String.fromCharCode(v.getUint8(t + tags[tag] + 8)) : '');
    const dms = tag => {
      if (tags[tag] == null) return NaN;
      const o = u32(tags[tag] + 8), r = i => u32(o + 8 * i) / u32(o + 8 * i + 4);
      return r(0) + r(1) / 60 + r(2) / 3600;
    };
    const lat = dms(2) * (ref(1) === 'S' ? -1 : 1), lon = dms(4) * (ref(3) === 'W' ? -1 : 1);
    return okCoord(lat, lon) && !(lat === 0 && lon === 0) ? { lat: round(lat, 6), lon: round(lon, 6) } : null;
  } catch { return null; }
}
