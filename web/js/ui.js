// HTML string renderers. Pure (no DOM access) so node --test can check them. Every value that
// comes from a file, the model or the user goes through esc() before it reaches markup.
import { UNCLEAR, formatAnswer } from './classify.js';

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = s => (s == null ? '' : String(s).replace(/[&<>"']/g, c => ESC[c]));
const pct = p => `${(100 * p).toFixed(1)} %`;
const LEVEL = { LOW: 'low', MODERATE: 'mod', HIGH: 'high' };

export function resultHTML(st) {
  if (st.kind === 'idle') return `<p class="muted">No photo yet. Drop one here, choose a file, or pick one from the gallery.</p>`;
  if (st.kind === 'loading') return `<p class="muted" aria-busy="true">Classifying ${esc(st.name)}…</p>`;
  if (st.kind === 'missing') return `<p><strong>Model not installed.</strong> The field, trap window and risk table still work. ` +
    `To add it, put <code>taupin.onnx</code> and <code>labels.json</code> in <code>model/</code> and start with <code>python -m taupin</code>.</p>`;
  if (st.kind === 'error') return `<p class="bad"><strong>Could not classify.</strong> ${esc(st.message)}</p>`;
  const d = st.decision, top = d.top.slice(1).map(t => `${esc(t.name)} ${pct(t.prob)}`).join(', ');
  const head = d.unclear
    ? `<p class="answer unclear">${esc(UNCLEAR)}</p><p class="muted">Best guess ${esc(d.name)} at ${pct(d.prob)}, below the ${pct(st.abstain)} the model card sets for an answer.</p>`
    : `<p class="answer${d.pest ? ' pest' : ''}">${esc(d.name)} <span class="prob">${pct(d.prob)}</span></p>`;
  return `<div class="result">${st.thumb ? `<img src="${esc(st.thumb)}" alt="" width="72" height="72">` : ''}<div>${head}` +
    (top ? `<p class="top3">Next: ${top}</p>` : '') + `</div></div>` +
    `<p class="effect">${esc(st.effect.note)}</p>` +
    (st.cell ? `<p class="muted small where">Pinned in the ${esc(st.zoneLabel)}. Click the field to move it.</p>` : '');
}

// TSOIL1 curves for the recent years with the 8 and 12 C lines; x = days from 1 Mar.
export function soilChartSVG(soil, { w = 320, h = 150 } = {}) {
  const years = Object.keys(soil.daily).sort(), pad = { l: 28, r: 8, t: 8, b: 20 };
  const all = years.flatMap(y => soil.daily[y].tsoil), n = Math.max(...years.map(y => soil.daily[y].tsoil.length));
  const lo = Math.min(0, Math.floor(Math.min(...all))), hi = Math.ceil(Math.max(...all) / 5) * 5;
  const X = i => pad.l + (i / (n - 1)) * (w - pad.l - pad.r), Y = t => pad.t + (1 - (t - lo) / (hi - lo)) * (h - pad.t - pad.b);
  const line = (y, k) => `<polyline class="yr${k === years.length - 1 ? ' last' : ''}" points="${soil.daily[y].tsoil
    .map((t, i) => `${X(i).toFixed(1)},${Y(t).toFixed(1)}`).join(' ')}"><title>${esc(y)}</title></polyline>`;
  const thr = (t, cls) => `<line class="${cls}" x1="${pad.l}" x2="${w - pad.r}" y1="${Y(t)}" y2="${Y(t)}"/>` +
    `<text x="${w - pad.r - 2}" y="${Y(t) - 3}" text-anchor="end">${t} °C</text>`;
  const months = [['Mar', 0], ['Apr', 31], ['May', 61], ['Jun', 92], ['Jul', 122]].filter(([, d]) => d < n)
    .map(([m, d]) => `<text x="${X(d)}" y="${h - 6}">${m}</text>`).join('');
  const meanX = X(soil.trap_12C_mean_doy - 60);   // DOY 60 = 1 Mar in a non-leap year
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Soil temperature 0-10 cm, 1 March to 31 July, ${esc(years[0])}-${esc(years[years.length - 1])}, with the 8 and 12 degree lines">` +
    `<text x="2" y="${Y(hi) + 4}">${hi}</text><text x="2" y="${Y(lo)}">${lo}</text>` +
    years.map(line).join('') + thr(soil.thresholds_c.larvae, 'thr8') + thr(soil.thresholds_c.trap, 'thr12') +
    `<line class="mean" x1="${meanX}" x2="${meanX}" y1="${pad.t}" y2="${h - pad.b}"/>${months}</svg>`;
}

export function trapHTML(tw, soil, evidence) {
  const sign = tw.trend >= 0 ? '+' : '';
  const ww = evidence.some(e => e.kind === 'wireworm');
  return `${ww ? `<p class="callout">A wireworm or click beetle was photographed. Set bait traps from <strong>${esc(tw.mean12)}</strong> (mean) and count larvae per trap.</p>` : ''}` +
    `<dl class="facts"><div><dt>Bait traps</dt><dd>${esc(tw.mean12)}<span>${esc(tw.last12)} in ${esc(tw.lastYear)}</span></dd></div>` +
    `<div><dt>Larvae move up</dt><dd>${esc(tw.mean8)}<span>${esc(tw.last8)} in ${esc(tw.lastYear)}</span></dd></div>` +
    (tw.lastCrw ? `<div><dt>Rootworm hatch</dt><dd>${esc(tw.lastCrw)}<span>in ${esc(tw.lastYear)}</span></dd></div>` : '') + `</dl>` +
    soilChartSVG(soil) +
    `<details class="more"><summary>Method and sources</summary><p>The trap date is the end of the first 7 days averaging 12 °C or more at 0-10 cm after 1 March. ` +
    `Trend ${sign}${tw.trend.toFixed(2)} ± ${tw.ci.toFixed(2)} days per decade (95 %): no clear shift.</p>` +
    `<ul class="src"><li>${esc(soil.sources.tsoil)}</li><li>${esc(soil.sources.trap)}</li><li>${esc(soil.sources.crw)}</li></ul></details>`;
}

export function riskTableHTML(view, sel) {
  const years = view.rows[0].years.map(y => `<th scope="col">${esc(y.year)}</th>`).join('');
  const cell = (r, y, i) => {
    const on = sel && sel.rotation === r.rotation && sel.i === i;
    const t = y.ifTrap ? `<span class="iftrap" title="if traps reach ${esc(view.threshold)} per trap">→ ${esc(y.ifTrap.wireworm)}${y.ifTrap.rx ? ' Rx' : ''}</span>` : '';
    return `<td><button type="button" class="cell ${LEVEL[y.wireworm] ?? ''}${on ? ' on' : ''}${y.crwFlag ? ' crw' : ''}" data-rot="${esc(r.rotation)}" data-i="${i}" aria-pressed="${on}">` +
      `<span class="crop">${esc(y.short)}</span><span class="lv">${esc(y.wireworm)}</span>${t}` +
      `<span class="crwl">CRW ${esc(y.crw)}</span>${y.rx ? '<span class="rx">Rx</span>' : ''}</button></td>`;
  };
  return `<table class="risk"><caption>${esc(view.label)}</caption>` +
    `<thead><tr><th scope="col">Rotation</th>${years}</tr></thead><tbody>` +
    view.rows.map(r => `<tr><th scope="row">${esc(r.name)}</th>${r.years.map((y, i) => cell(r, y, i)).join('')}</tr>`).join('') +
    `</tbody></table>`;
}

export function riskSummaryHTML(view) {
  const parts = [];
  if (view.ww) parts.push(`Arrows show the engine's level if bait traps then reach ${esc(view.threshold)} larvae per trap (${esc(view.genus)}). ` +
    `Prescription would be supportable in ${view.rxIfTrap} of 15 cells, against ${view.rxCount} now. The photo alone changes no level: it is an identification, not a count.`);
  if (view.crw) parts.push('Outlined cells are corn after corn, where rootworm eggs laid this year hatch next year.');
  return parts.length ? `<p class="callout">${parts.join(' ')}</p>` : '';
}

export function traceHTML(view, sel) {
  if (!sel) return '';
  const r = view.rows.find(x => x.rotation === sel.rotation), y = r?.years[sel.i];
  if (!y) return '';
  const li = t => `<li>${esc(t)}</li>`;
  return `<h3>${esc(r.name)}, ${esc(y.year)} (${esc(y.crop)})</h3><ul class="trace">${y.trace.map(li).join('')}</ul>` +
    (y.ifTrap ? `<p class="muted small">If traps reach the threshold:</p><ul class="trace">${y.ifTrap.trace.map(li).join('')}</ul>` : '');
}

export function evidenceHTML(list) {
  if (!list.length) return '';
  return `<ul class="evidence">${list.map((e, i) => `<li><img src="${esc(e.thumb)}" alt="" width="40" height="40">` +
    `<span>${esc(formatAnswer(e.decision))}<br><span class="muted small">${esc(e.zoneLabel)}</span></span>` +
    `<button type="button" class="ghost" data-remove="${i}" aria-label="Remove photo ${i + 1}">Remove</button></li>`).join('')}</ul>`;
}

export function galleryHTML(items, labels) {
  if (!items.length) return '<p class="muted">No credited photos found.</p>';
  const known = new Set((labels?.classes ?? []).map(c => c.id));
  return `<ul class="gallery">${items.map((it, i) => `<li><button type="button" data-g="${i}" aria-label="Classify ${esc(it.caption)}">` +
    `<img src="${esc(it.file)}" alt="${esc(it.caption)}" loading="lazy" width="160" height="120"></button>` +
    `<p>${esc(it.caption)}${labels && it.class_id && !known.has(it.class_id) ? ' <span class="muted">(not a model class)</span>' : ''}</p>` +
    `<p class="muted small">${esc(it.author)}, ${esc(it.licence)}${/^https?:\/\//.test(it.source ?? '') ? `, <a href="${esc(it.source)}" rel="noopener">source</a>` : ''}</p></li>`).join('')}</ul>`;
}

// model/metrics.json layout is owned by train/; find every block that reports accuracy so the
// page quotes the file as written instead of assuming key names. Baselines are listed separately.
const SPLIT_NAMES = { val: 'Validation', test: 'Test (sealed)', ood: 'Out-of-distribution photos' };

// metrics.json from train/ keeps the chosen model's splits under "model"; baselines and the
// threshold sweep sit elsewhere and are not this model's headline figures.
export function metricsRows(m) {
  if (!m || typeof m !== 'object') return [];
  const src = m.model && typeof m.model === 'object' ? m.model : m;
  return Object.entries(src).filter(([, v]) => v && typeof v.accuracy === 'number')
    .map(([k, v]) => ({ split: SPLIT_NAMES[k] ?? k, ...v }));
}

export function metricsHTML(m) {
  const rows = metricsRows(m);
  if (!rows.length) return 'No accuracy figures in model/metrics.json yet.';
  const f = v => (typeof v === 'number' ? `${(100 * v).toFixed(1)} %` : 'n/a');
  return `<table class="metrics"><thead><tr><th scope="col">Split</th><th scope="col">Photos</th><th scope="col">Accuracy</th><th scope="col">Macro-F1</th>` +
    `<th scope="col">Answered</th><th scope="col">Accuracy when answered</th></tr></thead><tbody>${rows.map(r =>
      `<tr><th scope="row">${esc(r.split)}</th><td>${Number.isFinite(r.n) ? r.n : 'n/a'}</td><td>${f(r.accuracy)}</td><td>${typeof r.macro_f1 === 'number' ? r.macro_f1.toFixed(3) : 'n/a'}</td>` +
      `<td>${f(r.coverage_at_threshold)}</td><td>${f(r.accuracy_at_threshold)}</td></tr>`).join('')}</tbody></table>` +
    `<p class="muted small">From model/metrics.json${m.version ? ` (${esc(m.version)})` : ''}. "Answered" is the share of photos above the abstain threshold.</p>`;
}
