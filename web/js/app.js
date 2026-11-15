// Wires the page: loads the baked data, builds the 3D field, loads the model if installed,
// classifies dropped photos in the browser and redraws the risk panel from the evidence.
import * as ort from '../vendor/ort/ort.wasm.min.mjs';
import { createScene } from './scene.js';
import { loadModel, classifyPixels } from './model.js';
import { effectFor, riskView, trapWindow } from './risk.js';
import * as ui from './ui.js';

const $ = s => document.querySelector(s);
const getJSON = async p => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`); return r.json(); };
const PIN = { wireworm: 0xe3a93f, rootworm: 0xb3361f, beneficial: 0x4f9a5a, none: 0x8a8f8c, unscored: 0x8a8f8c, unclear: 0xf2f2f2 };

const state = { zone: 'upland', sel: null, evidence: [], current: { kind: 'idle' }, model: { status: 'loading' } };
let D, scene;

function zoneOf(cell) { return cell && scene.isPocket(cell.row, cell.col) ? 'pocket' : 'upland'; }

function renderModelStatus() {
  const m = state.model, el = $('#model-status');
  const text = { loading: 'Loading model…', ready: `Model ready, ${m.labels?.classes.length} classes`, missing: 'Model not installed', error: 'Model failed to load' }[m.status];
  el.textContent = text; el.dataset.status = m.status;
  if (m.reason) el.title = m.reason;
  $('#model-metrics').innerHTML = m.status !== 'ready' ? ''
    : D?.metrics ? ui.metricsHTML(D.metrics) : 'No model/metrics.json next to the model, so no accuracy is shown.';
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
  for (const z of ['upland', 'pocket']) $(`#zone-${z}`).addEventListener('click', () => { state.zone = z; renderPanel(); });
  $('#show-pocket').addEventListener('change', e => scene.setPocket(e.target.checked));
  scene.onPick((row, col) => {
    const last = state.evidence[state.evidence.length - 1];
    if (!last) return;
    place(last, { row, col }); rebuildPins(); renderPanel();
  });
}

async function main() {
  const [field, risk, soil, gallery] = await Promise.all(['data/field.json', 'data/risk.json', 'data/soil.json', 'data/gallery.json'].map(getJSON));
  D = { field, risk, soil, gallery: gallery.items, metrics: null };
  scene = createScene($('#field'), field, `data/${field.texture}`);
  $('#site').textContent = `${field.site.name}, ${field.parcel.area_ha} ha parcel at ${field.site.lat} N, ${Math.abs(field.site.lon)} W`;
  $('#field-src').innerHTML = Object.values(field.sources).map(s => `<li>${ui.esc(s)}</li>`).join('');
  $('#gallery').innerHTML = ui.galleryHTML(D.gallery, null);
  bind();
  renderPanel();
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
