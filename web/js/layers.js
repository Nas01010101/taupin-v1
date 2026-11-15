// Field layers baked by src/taupin/layers.py: decoding the .bin rasters, colour ramps and legend
// rows. No imports, so the pitch deck can inline it next to scene.js.

// The draped views, in switcher order. `layer` is the manifest key; terrain colours the height.
export const VIEWS = [
  { key: 'terrain', layer: 'height', label: 'Terrain' },
  { key: 'twi', layer: 'twi', label: 'Wetness index' },
  { key: 'ndvi', layer: 'ndvi', label: 'Vegetation' },
  { key: 'lst', layer: 'lst', label: 'Spring surface temperature' },
  { key: 'soil', layer: 'soil', label: 'Soil' },
  { key: 'zones', layer: 'zones', label: 'Scouting zones' },
];

// value = offset + scale * q; q === nodata is NaN. Little-endian, row-major from the north-west.
export function decode(buf, enc) {
  const q = enc.dtype === 'u2' ? new Uint16Array(buf) : new Uint8Array(buf);
  const out = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) out[i] = q[i] === enc.nodata ? NaN : enc.offset + enc.scale * q[i];
  return out;
}

// Ramps as colour stops over 0..1. Wetness runs dry tan to wet blue, NDVI bare brown to green,
// temperature cool blue to warm red around the parcel mean (0).
const RAMPS = {
  height: [[0, [92, 120, 74]], [0.5, [150, 160, 98]], [1, [196, 178, 132]]],
  twi: [[0, [222, 204, 160]], [0.5, [120, 180, 170]], [1, [36, 84, 160]]],
  ndvi: [[0, [150, 112, 70]], [0.5, [200, 200, 110]], [1, [40, 120, 50]]],
  lst: [[0, [52, 96, 180]], [0.5, [240, 238, 228]], [1, [196, 62, 44]]],
};
// Land classes; blue comes last so soil units with four or fewer classes never look like water.
const CLASS = [[214, 160, 70], [180, 100, 190], [96, 176, 96], [200, 90, 80], [90, 156, 214], [120, 120, 120]];
const WATER = [70, 130, 200];

export function ramp(name, t) {
  const s = RAMPS[name];
  t = Math.max(0, Math.min(1, t));
  let i = 1;
  while (i < s.length - 1 && t > s[i][0]) i++;
  const [t0, a] = s[i - 1], [t1, b] = s[i], k = (t - t0) / (t1 - t0);
  return a.map((v, j) => Math.round(v + (b[j] - v) * k));
}

// Value range a ramp spans: temperature is symmetric around 0 so white is the parcel mean.
export function span(layer) {
  const [lo, hi] = layer.range;
  if (layer.key === 'lst') { const m = Math.max(Math.abs(lo), Math.abs(hi)); return [-m, m]; }
  return [lo, hi];
}

const isWater = cls => cls.components?.length && cls.components.every(c => c.name === 'Water');

// [r, g, b] for one value of a layer, or null for no data.
export function colorOf(layer, v) {
  if (Number.isNaN(v)) return null;
  if (layer.kind === 'classes') {
    const i = layer.classes.findIndex(c => c.id === v);
    if (i < 0) return null;
    if (isWater(layer.classes[i])) return WATER;
    // Count only land classes so the palette starts at the first land unit.
    const n = layer.classes.slice(0, i).filter(c => !isWater(c)).length;
    return CLASS[n % CLASS.length];
  }
  const [lo, hi] = span(layer);
  return ramp(layer.key, (v - lo) / (hi - lo || 1));
}

const fmt = (v, d) => Number(v).toFixed(d);

// Legend rows: classes list each class; ramps give three swatches (low, middle, high).
export function legend(layer) {
  if (layer.kind === 'classes') {
    return layer.classes.map(c => ({
      color: colorOf(layer, c.id),
      label: layer.key === 'soil'
        ? `${c.symbol}: ${c.components.map(p => `${p.name}${c.components.length > 1 ? ` ${p.pct} %` : ''}`).join(', ')}`
        : `Zone ${c.id}: wetness ${c.twi}, NDVI ${c.ndvi}, ${c.lst > 0 ? '+' : ''}${c.lst} °C, soil ${c.soil}`,
      detail: layer.key === 'soil'
        ? c.components.filter(p => p.drainage).map(p => `${p.name}: ${p.drainage}${p.texture ? `; ${p.texture}` : ''}`).join(' | ')
        : `${c.area_ha} ha, traps ${c.traps.join(', ') || 'none'}`,
    }));
  }
  const [lo, hi] = span(layer), d = layer.key === 'ndvi' ? 2 : 1;
  return [lo, (lo + hi) / 2, hi].map(v => ({ color: colorOf(layer, v), label: fmt(v, d) }));
}

// Plain-language resolution line: 30 m and 100 m layers must never read as 2 m data.
export function resolutionText(layer) {
  if (layer.native_res_m == null) return `Map polygons (1:20 000), drawn on ${layer.grid_res_m} m cells`;
  if (layer.native_res_m < layer.grid_res_m) return `${layer.native_res_m} m lidar, averaged to ${layer.grid_res_m} m cells`;
  return `Native ${layer.native_res_m} m, shown as ${layer.grid_res_m} m cells`;
}
