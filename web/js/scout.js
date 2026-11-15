// Bait-trap count sheet, trap-point files and the scouting record. Pure data and text: no DOM and
// no network, so node --test can check it. The RAP method (Agri-Réseau doc. 115269) asks for three
// lifts 7 to 10 days apart and compares each lift on its own: wireworms found / traps lifted,
// against the threshold of the dominant species.

// Mirror of TRAP_THRESHOLD in src/taupin/engine.py; tests/test_web.py checks the two agree.
export const THRESHOLDS = { hypnoidus: 3, agriotes: 1, limonius: 1, melanotus: 1 };
export const GENUS_LABEL = { hypnoidus: 'Hypnoidus abbreviatus', agriotes: 'Agriotes', limonius: 'Limonius', melanotus: 'Melanotus' };
export const LIFTS = 3;

// The lab the method sends larvae to for the species name; also the route for an unclear photo.
export const LAB = {
  name: "Laboratoire d'expertise et de diagnostic en phytoprotection (MAPAQ)",
  url: 'https://www.quebec.ca/agriculture-environnement-et-ressources-naturelles/agriculture/protection-cultures/laboratoire-expertise-diagnostic-phytoprotection',
  email: 'phytolab@mapaq.gouv.qc.ca',
  steps: [
    "Fill in the lab's online request form, one form per request.",
    'Reply to the confirmation email with the photo attached, or post the larvae in a jar half full of soil.',
    'A first answer comes within 24 to 48 hours; results take from 24 hours to 2 weeks. The lab charges a fee.',
  ],
};
export const VFFQC = 'VFF QC (CÉROM and MAPAQ), https://cerom.qc.ca/vffqc/';

// A count is a whole number of larvae; anything else (blank, text, negative) is "not lifted".
export function cleanCount(v) {
  if (v === '' || v == null) return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 && n <= 999 ? n : null;
}

const num = x => String(Number(x.toFixed(2)));

// sheet = { counts: { trapId: [lift1, lift2, lift3] }, dates: [d1, d2, d3], genus }
export function liftSummary(traps, sheet) {
  const genus = sheet.genus in THRESHOLDS ? sheet.genus : 'hypnoidus', threshold = THRESHOLDS[genus];
  const lifts = Array.from({ length: LIFTS }, (_, i) => {
    const got = traps.map(t => cleanCount(sheet.counts?.[t.id]?.[i])).filter(n => n != null);
    if (!got.length) return null;
    const total = got.reduce((a, b) => a + b, 0), mean = total / got.length;
    return { lift: i + 1, n: got.length, total, mean, reached: mean >= threshold };
  });
  const done = lifts.filter(Boolean);
  return { genus, threshold, lifts, counted: done.length, reached: done.some(l => l.reached), highest: done.length ? Math.max(...done.map(l => l.mean)) : null };
}

export const liftLine = l => `Lift ${l.lift}: ${l.total} wireworm${l.total === 1 ? '' : 's'} in ${l.n} trap${l.n === 1 ? '' : 's'}, ${num(l.mean)} per trap`;

// What the counts say against the method. The wording stops at the count: the agronomist decides.
export function verdict(s, minTraps) {
  const thr = `the threshold of ${s.threshold} per trap for ${GENUS_LABEL[s.genus]}`;
  if (!s.counted) return 'No trap counted yet. Enter the wireworms found in each trap; each lift is compared with the threshold on its own.';
  const short = s.lifts.filter(l => l && l.n < minTraps).map(l => `Lift ${l.lift} has ${l.n} of the ${minTraps} traps the method asks for.`).join(' ');
  const hit = s.lifts.find(l => l?.reached);
  const text = hit
    ? `Lift ${hit.lift} is at or above ${thr} (${num(hit.mean)} per trap). One lift at the threshold is enough for the method, and trapping can stop. The count can justify a control method; the agronomist decides which.`
    : s.counted < LIFTS
      ? `No lift at ${thr} so far (highest ${num(s.highest)} per trap). ${s.counted} of ${LIFTS} lifts counted: the method asks for three lifts, 7 to 10 days apart.`
      : `Three lifts counted, none at ${thr} (highest ${num(s.highest)} per trap). On wireworms, the count stays under the level the method uses to justify control. The agronomist decides.`;
  return short ? `${text} ${short}` : text;
}

const csvCell = v => (/[",\n\r]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
const xml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[c]));
const liftsOf = (sheet, id) => Array.from({ length: LIFTS }, (_, i) => cleanCount(sheet?.counts?.[id]?.[i]));

export function trapsCSV(field, sheet) {
  const head = ['trap', 'zone', 'latitude', 'longitude', ...Array.from({ length: LIFTS }, (_, i) => `lift${i + 1}${sheet?.dates?.[i] ? `_${sheet.dates[i]}` : ''}`)];
  const rows = field.traps.map(t => [t.id, t.zone, t.lat.toFixed(6), t.lon.toFixed(6), ...liftsOf(sheet, t.id).map(n => n ?? '')]);
  return [head, ...rows].map(r => r.map(csvCell).join(',')).join('\n') + '\n';
}

// GPX 1.1 waypoints: opens in phone map apps and handheld GPS units.
export function trapsGPX(field) {
  const wpts = field.traps.map(t => `  <wpt lat="${t.lat.toFixed(6)}" lon="${t.lon.toFixed(6)}"><name>Trap ${xml(t.id)}</name><desc>Scouting zone ${xml(t.zone)}</desc></wpt>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Taupin" xmlns="http://www.topografix.com/GPX/1/1">\n${wpts.join('\n')}\n</gpx>\n`;
}

export function trapsGeoJSON(field, sheet) {
  return JSON.stringify({ type: 'FeatureCollection', features: field.traps.map(t => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: [t.lon, t.lat] },
    properties: { trap: t.id, zone: t.zone, wireworms_per_lift: liftsOf(sheet, t.id) },
  })) }, null, 1) + '\n';
}

// Plain text the farmer hands to the agronomist. Every line is a value shown in the app.
export function recordText({ date, field, window: tw, sheet, rank, photos = [], own = null }) {
  const r = field.trap_rules, s = liftSummary(field.traps, sheet), side = field.parcel.size * field.parcel.res_m;
  const pad = (v, n) => String(v).padEnd(n);
  const rows = field.traps.map(t => `  ${pad(t.id, 5)}${pad(t.zone, 5)}${pad(t.lat.toFixed(6), 11)}${pad(t.lon.toFixed(6), 12)}`
    + liftsOf(sheet, t.id).map(n => pad(n ?? '-', 7)).join('').trimEnd());
  const lifts = s.lifts.filter(Boolean).map(l => `  ${liftLine(l)}${sheet.dates?.[l.lift - 1] ? `, lifted ${sheet.dates[l.lift - 1]}` : ''}`);
  return [
    'Taupin scouting record', `Written ${date}`, '',
    'Field',
    `  ${field.site.name}: a ${side} m square at ${field.site.lat} N, ${Math.abs(field.site.lon)} W`,
    ...(field.open ? [`  Open ground where traps can go: ${field.open.area_ha} ha`] : []), '',
    'When to trap',
    `  Soil at 0 to 10 cm holds 12 °C for a week around ${tw.mean12} (NASA POWER TSOIL1, ${tw.span[0]} to ${tw.span[1]}); ${tw.last12} in ${tw.lastYear}`,
    ...(own ? [`  This date and the ranking below are for ${own}, not for the square above.`] : []), '',
    `Bait traps (at least ${r.min_traps} per field, about ${r.spacing_m} m apart; ${r.source})`,
    `  ${pad('Trap', 5)}${pad('Zone', 5)}${pad('Latitude', 11)}${pad('Longitude', 12)}${Array.from({ length: LIFTS }, (_, i) => pad(`Lift ${i + 1}`, 7)).join('').trimEnd()}`,
    ...rows, ...lifts,
    `  Dominant species entered: ${GENUS_LABEL[s.genus]} (threshold ${s.threshold} per trap per lift)`,
    `  ${verdict(s, r.min_traps)}`, '',
    'Field ranking',
    rank ? `  ${rank.text} third for ${rank.year} among the ${rank.n} Quebec fields the Taupin model was fitted on. A rank, not a probability.` : '  Not available for this year.', '',
    'Photos named in the app',
    ...(photos.length ? photos.map(p => `  ${p}`) : ['  None.']),
    '  A photo is a first sort; the lab names the species.', '',
    'Also',
    `  ${VFFQC}: the Quebec field-level wireworm risk tool. Three lifts are required to enter a field in it.`,
    `  ${LAB.name}, ${LAB.email}: species identification of the larvae.`, '',
    'Taupin does not decide the prescription. The agronomist signs.', '',
  ].join('\n');
}
