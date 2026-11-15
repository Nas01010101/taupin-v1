// Insect photo classification in the browser, mirroring src/taupin/classify.py step for step.
// Preprocess (model/labels.json contract): resize so the short side is S with a triangle
// (antialiased bilinear) filter, the kernel of PIL BILINEAR and torchvision Resize; centre crop
// S x S; scale to 0..1; normalise. Written out instead of canvas drawImage scaling, whose filter
// differs by browser, so the page and `taupin classify` compute the same numbers.

export const UNCLEAR = 'unclear: send to the lab';

// Python's round(): half to even, as torchvision CenterCrop uses.
export function roundHalfEven(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

export function targetSize(w, h, s) {
  return w <= h ? [s, Math.trunc((s * h) / w)] : [Math.trunc((s * w) / h), s];
}

// Triangle-filter taps for output pixels start..start+count-1: [{lo, w: Float64Array}].
export function resizeWeights(inSize, outSize, start, count) {
  const scale = inSize / outSize, fs = Math.max(scale, 1), rows = [];
  for (let k = 0; k < count; k++) {
    const center = (start + k + 0.5) * scale;
    const lo = Math.max(Math.floor(center - fs + 0.5), 0), hi = Math.min(Math.floor(center + fs + 0.5), inSize);
    const w = new Float64Array(Math.max(0, hi - lo));
    let total = 0;
    for (let x = lo; x < hi; x++) { const v = Math.max(0, 1 - Math.abs((x + 0.5 - center) / fs)); w[x - lo] = v; total += v; }
    if (total > 0) for (let i = 0; i < w.length; i++) w[i] /= total;
    rows.push({ lo, w });
  }
  return rows;
}

// data: RGBA bytes (ImageData.data) of a w x h image. Returns Float32Array [3*S*S] in NCHW order.
export function preprocess(data, w, h, labels) {
  const s = labels.input_size, [nw, nh] = targetSize(w, h, s);
  const top = roundHalfEven((nh - s) / 2), left = roundHalfEven((nw - s) / 2);
  const wy = resizeWeights(h, nh, top, s), wx = resizeWeights(w, nw, left, s);
  // Horizontal pass only on the source rows the vertical taps touch.
  const rowLo = wy[0].lo, rowHi = wy[s - 1].lo + wy[s - 1].w.length;
  const tmp = new Float64Array((rowHi - rowLo) * s * 3);
  for (let y = rowLo; y < rowHi; y++) {
    const base = y * w * 4, o = (y - rowLo) * s * 3;
    for (let x = 0; x < s; x++) {
      const { lo, w: k } = wx[x];
      let r = 0, g = 0, b = 0;
      for (let i = 0; i < k.length; i++) { const p = base + (lo + i) * 4; r += k[i] * data[p]; g += k[i] * data[p + 1]; b += k[i] * data[p + 2]; }
      tmp[o + x * 3] = r; tmp[o + x * 3 + 1] = g; tmp[o + x * 3 + 2] = b;
    }
  }
  const out = new Float32Array(3 * s * s), { mean, std } = labels;
  for (let y = 0; y < s; y++) {
    const { lo, w: k } = wy[y];
    for (let x = 0; x < s; x++) {
      for (let c = 0; c < 3; c++) {
        let v = 0;
        for (let i = 0; i < k.length; i++) v += k[i] * tmp[((lo - rowLo + i) * s + x) * 3 + c];
        out[c * s * s + y * s + x] = (v / 255 - mean[c]) / std[c];
      }
    }
  }
  return out;
}

export function softmax(logits, temperature = 1) {
  const z = Array.from(logits, v => v / temperature), m = Math.max(...z);
  const e = z.map(v => Math.exp(v - m)), t = e.reduce((a, b) => a + b, 0);
  return e.map(v => v / t);
}

export function decide(probs, labels) {
  const ranked = probs.map((p, i) => i).sort((a, b) => probs[b] - probs[a]);
  const i = ranked[0], cls = labels.classes[i];
  return {
    id: cls.id, name: cls.name, pest: !!cls.pest, prob: probs[i],
    unclear: probs[i] < Number(labels.abstain_below ?? 0),
    top: ranked.slice(0, 3).map(j => ({ id: labels.classes[j].id, name: labels.classes[j].name, prob: probs[j] })),
  };
}

export function formatAnswer(r) {
  const pct = `${(100 * r.prob).toFixed(1)} %`;
  return r.unclear ? `${UNCLEAR} (best guess ${r.name}, ${pct})` : `${r.name} (${pct})${r.pest ? ', pest' : ''}`;
}

// Basic contract check so a malformed labels.json fails with a message, not a NaN.
export function checkLabels(l) {
  const ok = l && Array.isArray(l.classes) && l.classes.length > 1 && l.classes.every(c => c.id && c.name)
    && Number.isInteger(l.input_size) && l.input_size > 0
    && Array.isArray(l.mean) && l.mean.length === 3 && Array.isArray(l.std) && l.std.length === 3;
  if (!ok) throw new Error('model/labels.json does not match the contract (classes, input_size, mean, std)');
  return l;
}
