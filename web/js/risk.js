// What a photo means for the field. The levels come from web/data/risk.json, baked by the Python
// engine (src/taupin/engine.py); nothing here recomputes a risk level. A photo is an
// identification, not a count, so a wireworm photo does not raise a level by itself: it marks
// presence and shows what the engine gives if bait traps then reach the RAP threshold.
import { UNCLEAR } from './classify.js';

export const ROTATION_NAMES = {
  A_continuous_corn: 'Corn every year',
  B_corn_soy_wheat: 'Corn, soybean, wheat',
  C_with_buckwheat: 'With buckwheat',
  D_corn_soy: 'Corn and soybean',
};
export const CROP_SHORT = { soybean: 'soy', buckwheat: 'buckw.' };

// Keyed by class id from model/labels.json; ids not listed here are shown as not scored.
const EFFECTS = {
  wireworm: { kind: 'wireworm', src: 'RAP',
    note: 'Wireworm larva identified. A photo shows presence, not how many: set bait traps in the window below to get larvae per trap.' },
  click_beetle: { kind: 'wireworm', src: 'RAP',
    note: 'Click beetle adult identified. Adults lay eggs in grassy ground, so larvae can follow: confirm with bait traps.' },
  corn_rootworm: { kind: 'rootworm', src: 'MAPAQ_CRW',
    note: 'Corn rootworm adult identified. Eggs laid in corn hatch in next year’s corn; one year out of corn breaks the cycle.' },
  white_grub: { kind: 'unscored', note: 'White grub identified. This engine does not score white grubs; show the photo to the agronomist.' },
  ground_beetle: { kind: 'beneficial', note: 'Ground beetle: a predator of soil pests. No action.' },
  earthworm: { kind: 'beneficial', note: 'Earthworm: not an insect, good for the soil. No action.' },
  millipede: { kind: 'none', note: 'Millipede: not a wireworm and not a field-crop pest here. No action.' },
  other: { kind: 'none', note: 'Not one of the soil animals this tool scores. The risk table is unchanged.' },
};

export function effectFor(d) {
  if (!d || d.unclear) return { kind: 'unclear', note: `${UNCLEAR}. The risk table is unchanged.` };
  return EFFECTS[d.id] ?? { kind: 'unscored', note: `${d.name}: not scored by this engine.` };
}

const LEVEL_RANK = { NONE: -1, LOW: 0, MODERATE: 1, HIGH: 2 };

// evidence: list of effectFor() results for confirmed photos. Returns the table the panel draws.
export function riskView(risk, zone, evidence = []) {
  const z = risk.zones[zone], base = z.scenarios.baseline, trap = z.scenarios.trap_threshold;
  const ww = evidence.some(e => e.kind === 'wireworm'), crw = evidence.some(e => e.kind === 'rootworm');
  const rows = Object.keys(base).map(rk => ({
    rotation: rk,
    name: ROTATION_NAMES[rk] ?? rk,
    years: base[rk].map((r, i) => {
      const t = trap[rk][i];
      const ifTrap = ww && (t.wireworm !== r.wireworm || t.prescription_supportable !== r.prescription_supportable)
        ? { wireworm: t.wireworm, rx: t.prescription_supportable, trace: t.trace } : null;
      return {
        year: r.year, crop: r.crop, short: CROP_SHORT[r.crop] ?? r.crop,
        wireworm: r.wireworm, crw: r.corn_rootworm, rx: r.prescription_supportable, trace: r.trace,
        ifTrap,
        crwFlag: crw && LEVEL_RANK[r.corn_rootworm] >= 1,
      };
    }),
  }));
  return { zone, label: z.label, genus: z.dominant_genus, threshold: z.trap_threshold, rows, ww, crw,
    cells: rows.length * rows[0].years.length,
    rxCount: rows.reduce((n, r) => n + r.years.filter(y => y.rx).length, 0),
    rxIfTrap: rows.reduce((n, r) => n + r.years.filter(y => (y.ifTrap ? y.ifTrap.rx : y.rx)).length, 0) };
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = iso => `${Number(iso.slice(8, 10))} ${MON[Number(iso.slice(5, 7)) - 1]}`;   // same style as soil.json means

export function trapWindow(soil) {
  const years = Object.keys(soil.per_year).sort(), last = years[years.length - 1], y = soil.per_year[last];
  return {
    mean12: soil.trap_12C_mean, mean8: soil.larvae_8C_mean, span: soil.years,
    lastYear: last, last12: fmt(y.trap_12C), last8: fmt(y.larvae_8C), lastCrw: y.crw_hatch ? fmt(y.crw_hatch) : null,
    trend: soil.trap_12C_trend_days_per_decade, ci: soil.trap_12C_trend_95ci_days_per_decade,
  };
}

// Photo GPS -> parcel cell, or null outside the parcel (linear map; the parcel is 600 m).
export function gpsToCell(gps, parcel) {
  const [nlat, wlon] = parcel.nw, [slat, elon] = parcel.se;
  if (!gps || gps.latitude > nlat || gps.latitude < slat || gps.longitude < wlon || gps.longitude > elon) return null;
  const n = parcel.size - 1;
  return { row: Math.round(((nlat - gps.latitude) / (nlat - slat)) * n), col: Math.round(((gps.longitude - wlon) / (elon - wlon)) * n) };
}
