// Wires the page: loads the baked data, builds the 3D field, loads the model if installed,
// classifies dropped photos in the browser and redraws the risk panel from the evidence.
import * as ort from '../vendor/ort/ort.wasm.min.mjs';
import { createScene } from './scene.js';
import { VIEWS } from './layers.js';
import { loadModel, classifyPixels } from './model.js';
import { effectFor, riskView, trapWindow } from './risk.js';
import { fieldRanking } from './fieldrisk.js';
import { formatAnswer } from './classify.js';
import * as scout from './scout.js';
import * as ui from './ui.js';

const $ = s => document.querySelector(s);
const getJSON = async p => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`); return r.json(); };
const PIN = { wireworm: 0xe3a93f, rootworm: 0xb3361f, beneficial: 0x4f9a5a, none: 0x8a8f8c, unscored: 0x8a8f8c, unclear: 0xf2f2f2 };

const state = { zone: 'upland', sel: null, rankYear: null, forage: 0, evidence: [], current: { kind: 'idle' }, model: { status: 'loading' } };
let D, scene;

// The count sheet lives in this browser only (localStorage); nothing is sent anywhere.
const SHEET_KEY = 'taupin-counts';
function loadSheet() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(SHEET_KEY)) ?? {}; } catch { /* private window or bad JSON: start empty */ }
  return { counts: saved.counts ?? {}, dates: saved.dates ?? [], genus: saved.genus in scout.THRESHOLDS ? saved.genus : null };
}
const sheet = loadSheet();
const today = () => new Date().toLocaleDateString('en-CA');   // YYYY-MM-DD in local time

function recordNow() {
  const r = fieldRanking(D.model, D.fieldRisk, { year: state.rankYear, forageYears: state.forage, lightSoil: 0 });
  return scout.recordText({ date: today(), field: D.field, window: trapWindow(D.soil), sheet,
    rank: r && { text: ui.RANK_TEXT[r.rank], year: r.year, n: D.model.metrics.n },
    photos: state.evidence.map(e => `${formatAnswer(e.decision)}, ${e.zoneLabel}`) });
}

function renderCounts() {
  $('#count-result').innerHTML = ui.countResultHTML(scout.liftSummary(D.field.traps, sheet), D.field.trap_rules.min_traps);
  $('#record').textContent = recordNow();
}

function saveFile(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const FILES = {
  gpx: () => ['taupin-traps.gpx', scout.trapsGPX(D.field), 'application/gpx+xml'],
  csv: () => ['taupin-traps.csv', scout.trapsCSV(D.field, sheet), 'text/csv'],
  geojson: () => ['taupin-traps.geojson', scout.trapsGeoJSON(D.field, sheet), 'application/geo+json'],
  record: () => [`taupin-record-${today()}.txt`, recordNow(), 'text/plain'],
};

function zoneOf(cell) { return cell && scene.isPocket(cell.row, cell.col) ? 'pocket' : 'upland'; }

function renderModelStatus() {
  const m = state.model, el = $('#model-status');
  const text = { loading: 'Loading model…', ready: `Model ready, ${m.labels?.classes.length} classes`, missing: 'Model not installed', error: 'Model failed to load' }[m.status];
  el.textContent = text; el.dataset.status = m.status;
  if (m.reason) el.title = m.reason;
  $('#model-metrics').innerHTML = m.status !== 'ready' ? ''
    : D?.metrics ? ui.metricsHTML(D.metrics) : 'No model/metrics.json next to the model, so no accuracy is shown.';
}

// The soil map units under this parcel (Dorval clay loam and muck) are neither sand
// nor sandy loam, so the model's light-soil input is 0 everywhere here.
const LIGHT_SOIL_NOTE = 'Soil map units in this parcel are clay loam and muck, so the sand or sandy loam input is no everywhere and the rank is the same across the parcel.';

function renderRank() {
  const r = fieldRanking(D.model, D.fieldRisk, { year: state.rankYear, forageYears: state.forage, lightSoil: 0 });
  $('#h-rank').textContent = r ? `${ui.RANK_TEXT[r.rank]} wireworm ranking for ${r.year}` : 'Field wireworm ranking';
  $('#rank').innerHTML = ui.fieldRankHTML(r, D.model, { lightSoilNote: LIGHT_SOIL_NOTE });
  $('#record').textContent = recordNow();
}

function renderPanel() {
  const view = riskView(D.risk, state.zone, state.evidence);
  $('#zone-upland').setAttribute('aria-pressed', state.zone === 'upland');
  $('#zone-pocket').setAttribute('aria-pressed', state.zone === 'pocket');
  $('#risk-summary').innerHTML = ui.riskSummaryHTML(view);
  $('#risk-table').innerHTML = ui.riskTableHTML(view, state.sel);
  $('#trace').innerHTML = ui.traceHTML(view, state.sel);
  const tw = trapWindow(D.soil);
  $('#h-trap').textContent = `Set bait traps around ${tw.mean12}`;
  $('#trap').innerHTML = ui.trapHTML(tw, D.soil, state.evidence);
  $('#evidence').innerHTML = ui.evidenceHTML(state.evidence);
  $('#result').innerHTML = ui.resultHTML(state.current);
  $('#record').textContent = recordNow();
  document.body.classList.toggle('has-ww', view.ww);
}

async function pixelsOf(blob) {
  // from-image applies the EXIF orientation, matching ImageOps.exif_transpose in taupin classify.
  const bmp = await createImageBitmap(blob, { imageOrientation: 'from-image' });
  const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext('2d');
  g.drawImage(bmp, 0, 0);
  const data = g.getImageData(0, 0, bmp.width, bmp.height).data;
  const t = document.createElement('canvas'), s = 160, k = s / Math.min(bmp.width, bmp.height);
  t.width = t.height = s;
  t.getContext('2d').drawImage(bmp, (s - bmp.width * k) / 2, (s - bmp.height * k) / 2, bmp.width * k, bmp.height * k);
  return { data, w: bmp.width, h: bmp.height, thumb: t.toDataURL('image/jpeg', 0.85) };
}

// Classify a photo and, if it is an answer (not unclear), add it to the evidence and pin it.
export async function ingest(blob, name, cell = null, { dropMs = 700 } = {}) {
  if (state.model.status !== 'ready') { state.current = { kind: state.model.status === 'loading' ? 'loading' : 'missing', name }; renderPanel(); return null; }
  state.current = { kind: 'loading', name }; renderPanel();
  try {
    const px = await pixelsOf(blob);
    const decision = await classifyPixels(state.model, px.data, px.w, px.h);
    const effect = effectFor(decision);
    const where = cell ?? { row: Math.floor(scene.size / 2), col: Math.floor(scene.size / 2) };
    const entry = { decision, effect, thumb: px.thumb, cell: where, name };
    state.current = { kind: 'result', decision, effect, thumb: px.thumb, abstain: Number(state.model.labels.abstain_below ?? 0) };
    if (!decision.unclear) {
      entry.pin = scene.addPin({ row: where.row, col: where.col, thumb: px.thumb, color: PIN[effect.kind], drop: dropMs ? 0 : 1 });
      if (dropMs) animateDrop(entry.pin, dropMs);
      state.evidence.push(entry);
      place(entry, where);
    }
    renderPanel();
    return entry;
  } catch (e) {
    state.current = { kind: 'error', message: e.message }; renderPanel();
    return null;
  }
}

function animateDrop(pin, ms) {
  const t0 = performance.now();
  const step = now => { const k = (now - t0) / ms; scene.setDrop(pin, k); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

function place(entry, cell) {
  entry.cell = cell;
  entry.zone = zoneOf(cell);
  entry.zoneLabel = entry.zone === 'pocket' ? 'low wet pocket' : 'upland';
  state.zone = entry.zone;
  Object.assign(state.current, { cell, zoneLabel: entry.zoneLabel });
}

function rebuildPins() {
  scene.clearPins();
  for (const e of state.evidence) e.pin = scene.addPin({ row: e.cell.row, col: e.cell.col, thumb: e.thumb, color: PIN[e.effect.kind] });
}

function bind() {
  const drop = $('#drop'), file = $('#file');
  file.addEventListener('change', () => { const f = file.files[0]; if (f) ingest(f, f.name); file.value = ''; });
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const f = [...e.dataTransfer.files].find(x => x.type.startsWith('image/'));
    if (f) ingest(f, f.name);
  });
  $('#gallery').addEventListener('click', async e => {
    const b = e.target.closest('[data-g]'); if (!b) return;
    const it = D.gallery[Number(b.dataset.g)];
    ingest(await (await fetch(it.file)).blob(), it.caption);
    $('#identify').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  });
  $('#risk-table').addEventListener('click', e => {
    const b = e.target.closest('[data-rot]'); if (!b) return;
    const s = { rotation: b.dataset.rot, i: Number(b.dataset.i) };
    state.sel = state.sel && state.sel.rotation === s.rotation && state.sel.i === s.i ? null : s;
    renderPanel();
  });
  $('#evidence').addEventListener('click', e => {
    const b = e.target.closest('[data-remove]'); if (!b) return;
    state.evidence.splice(Number(b.dataset.remove), 1); rebuildPins(); renderPanel();
  });
  $('#rank-year').addEventListener('change', e => { state.rankYear = e.target.value; renderRank(); });
  $('#rank-forage').addEventListener('input', e => {
    const v = Number(e.target.value);
    state.forage = Number.isFinite(v) ? Math.min(20, Math.max(0, v)) : 0; renderRank();
  });
  for (const z of ['upland', 'pocket']) $(`#zone-${z}`).addEventListener('click', () => { state.zone = z; renderPanel(); });
  $('#sec-traps').addEventListener('input', e => {
    const t = e.target;
    if (t.dataset.trap) (sheet.counts[t.dataset.trap] ??= [])[Number(t.dataset.lift)] = t.value;
    else if (t.dataset.date) sheet.dates[Number(t.dataset.date)] = t.value;
    else if (t.id === 'count-genus') sheet.genus = t.value;
    else return;
    try { localStorage.setItem(SHEET_KEY, JSON.stringify(sheet)); } catch { /* storage blocked: the sheet still works for this visit */ }
    renderCounts();
  });
  $('#sec-traps').addEventListener('click', e => {
    const f = e.target.closest('[data-file]');
    if (f) saveFile(...FILES[f.dataset.file]());
  });
  $('#record-copy').addEventListener('click', async e => {
    try { await navigator.clipboard.writeText(recordNow()); e.target.textContent = 'Copied'; }
    catch { getSelection().selectAllChildren($('#record')); }   // clipboard refused: leave the text selected
  });
  $('#show-pocket').addEventListener('change', e => scene.setPocket(e.target.checked));
  $('#layer').addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) showLayer(b.dataset.view); });
  scene.onPick((row, col) => {
    const last = state.evidence[state.evidence.length - 1];
    if (!last) return;
    place(last, { row, col }); rebuildPins(); renderPanel();
  });
}

// Drape one layer and show its legend; the terrain view lists the lidar height.
function showLayer(key) {
  const v = VIEWS.find(x => x.key === key);
  scene.setLayer(key);
  for (const b of document.querySelectorAll('#layer [data-view]')) b.setAttribute('aria-pressed', String(b.dataset.view === key));
  $('#legend').innerHTML = ui.layerLegendHTML(D.field.layers.find(l => l.key === v.layer));
}

async function main() {
  const [field, risk, soil, gallery, model, fieldRisk] = await Promise.all(['data/field.json', 'data/risk.json', 'data/soil.json',
    'data/gallery.json', 'data/risk_model.json', 'data/field_risk.json'].map(getJSON));
  D = { field, risk, soil, gallery: gallery.items, metrics: null, model, fieldRisk };
  const years = Object.keys(fieldRisk.per_year).sort();
  state.rankYear = years[years.length - 1];
  $('#rank-year').innerHTML = years.map(y => `<option${y === state.rankYear ? ' selected' : ''}>${ui.esc(y)}</option>`).join('');
  scene = createScene($('#field'), field, 'data/');
  $('#layer').innerHTML = VIEWS.map(v => `<button type="button" class="seg" data-view="${ui.esc(v.key)}" aria-pressed="${v.key === 'terrain'}">${ui.esc(v.label)}</button>`).join('');
  showLayer('terrain');
  sheet.genus ??= risk.zones.upland.dominant_genus;
  $('#traps').innerHTML = ui.trapsHTML(field, sheet);
  const side = field.parcel.size * field.parcel.res_m;
  $('#site').textContent = `${field.site.name}: a ${side} m square at ${field.site.lat} N, ${Math.abs(field.site.lon)} W`
    + (field.open ? `, with ${field.open.area_ha} ha of open ground where traps can go` : '');
  $('#field-src').innerHTML = Object.values(field.sources).map(s => `<li>${ui.esc(s)}</li>`).join('');
  $('#gallery').innerHTML = ui.galleryHTML(D.gallery, null);
  bind();
  renderPanel();
  renderRank();
  renderCounts();
  renderModelStatus();
  // Absolute: ort resolves wasmPaths against its own module URL, not the page.
  state.model = await loadModel({ ort, wasmPaths: new URL('vendor/ort/', document.baseURI).href });
  if (state.model.status === 'ready') {
    D.metrics = await fetch('model/metrics.json').then(r => (r.ok ? r.json() : null)).catch(() => null);
    $('#gallery').innerHTML = ui.galleryHTML(D.gallery, state.model.labels);
  }
  if (state.current.kind === 'loading' || state.current.kind === 'missing') state.current = { kind: state.model.status === 'ready' ? 'idle' : 'missing' };
  else if (state.model.status !== 'ready') state.current = { kind: 'missing' };
  renderModelStatus();
  renderPanel();
  if (new URLSearchParams(location.search).has('demo')) (await import('./demo.js')).runDemo({ scene, state, D, ingest, renderPanel });
  else window.taupinReady = true;
}

// Theme: follows the system until the button is used, then remembers the choice.
function setTheme(t) { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; }
setTheme(localStorage.getItem('taupin-theme'));
$('#theme').addEventListener('click', () => {
  const dark = (document.documentElement.dataset.theme ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  const t = dark ? 'light' : 'dark'; setTheme(t); localStorage.setItem('taupin-theme', t);
});

if ('serviceWorker' in navigator && !new URLSearchParams(location.search).has('nosw')) navigator.serviceWorker.register('sw.js').catch(() => {});
main().catch(e => { $('#fatal').hidden = false; $('#fatal').textContent = `Could not start: ${e.message}`; });
