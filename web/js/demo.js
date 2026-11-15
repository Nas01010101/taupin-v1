// ?demo=1: a 12 s scripted sequence for the booth and the README GIF. The state at time t is a
// pure function of t, so window.taupinDemo.seek(t) gives the same frame on every machine:
//   0-12 s   camera orbits the parcel
//   1.5-2.5  a gallery photo drops onto the field       2.5  "classifying"
//   3.5      the model's answer (real inference)        4.0  the low wet pocket is shown
//   4.5-5.5  the pin lands on a pocket cell             6.0  the risk panel takes the evidence
//   7.5      the first-year cell of rotation B opens with its reasons
export const LENGTH = 12;
const T = { photoIn: 1.5, photoOut: 2.5, classify: 2.5, answer: 3.5, pocket: 4, pinIn: 4.5, pinDown: 5.5, panel: 6, trace: 7.5 };

// Pocket cell nearest the parcel centre, from the scene's lidar heights (call after scene.ready).
function nearestPocketCell(scene) {
  const N = scene.size, c = (N - 1) / 2;
  let best = null, bd = Infinity;
  for (let r = 0; r < N; r++) for (let k = 0; k < N; k++) {
    const d = (r - c) ** 2 + (k - c) ** 2;
    if (d < bd && scene.isPocket(r, k)) { bd = d; best = { row: r, col: k }; }
  }
  return best ?? { row: c | 0, col: c | 0 };
}

export async function runDemo({ scene, state, D, ingest, renderPanel }) {
  document.body.classList.add('demo');
  const params = new URLSearchParams(location.search);
  const sample = D.gallery.find(g => g.class_id === 'wireworm') ?? D.gallery.find(g => g.class_id) ?? D.gallery[0];
  const photo = document.createElement('img');
  photo.id = 'demo-photo'; photo.alt = ''; photo.src = sample?.file ?? '';
  document.querySelector('#field').appendChild(photo);

  await scene.ready;
  const cell = nearestPocketCell(scene);
  // Run the real classification once, then rewind; seek() replays the stored answer.
  let entry = null;
  if (sample && state.model.status === 'ready') entry = await ingest(await (await fetch(sample.file)).blob(), sample.caption, cell, { dropMs: 0 });
  const result = state.current;
  state.evidence.length = 0;
  scene.clearPins();
  const pin = entry?.pin ? scene.addPin({ row: cell.row, col: cell.col, thumb: entry.thumb, color: entry.pin.children[1].material.color.getHex(), drop: 0 }) : null;

  let stage = '';
  function seek(t) {
    t = Math.max(0, Math.min(LENGTH, t));
    scene.setOrbit(0.6 + t * 0.22);
    const k = Math.min(1, Math.max(0, (t - T.photoIn) / (T.photoOut - T.photoIn)));
    photo.style.opacity = t < T.photoIn || t >= T.photoOut + 0.3 ? 0 : t < T.photoOut ? 1 : 1 - (t - T.photoOut) / 0.3;
    photo.style.transform = `translate(-50%, ${-120 + 120 * (1 - (1 - k) ** 3)}%) rotate(${(1 - k) * -8}deg)`;
    if (pin) scene.setDrop(pin, (t - T.pinIn) / (T.pinDown - T.pinIn));
    const s = [t >= T.classify, t >= T.answer, t >= T.pocket, t >= T.panel, t >= T.trace].map(Number).join('');
    if (s !== stage) {
      stage = s;
      const missing = state.model.status !== 'ready';
      state.current = t < T.classify ? { kind: 'idle' }
        : t < T.answer ? (missing ? { kind: 'missing' } : { kind: 'loading', name: sample?.caption ?? '' })
          : missing || !entry ? { kind: missing ? 'missing' : 'error', message: 'no sample photo' } : result;
      scene.setPocket(t >= T.pocket);
      state.evidence.length = 0;
      if (entry && t >= T.panel && !entry.decision.unclear) { state.evidence.push(entry); state.zone = entry.zone ?? 'pocket'; }
      else state.zone = 'upland';
      state.sel = t >= T.trace ? { rotation: 'B_corn_soy_wheat', i: 0 } : null;
      renderPanel();
    }
    scene.render();
  }

  let playing = !params.has('pause'), t0 = performance.now();
  scene.setLooping(false);
  const tick = now => {
    if (!playing) return;
    seek(((now - t0) / 1000) % (LENGTH + 2));   // 2 s hold on the last frame before looping
    requestAnimationFrame(tick);
  };
  window.taupinDemo = {
    length: LENGTH, seek: t => { playing = false; seek(t); },
    pause() { playing = false; }, play() { playing = true; t0 = performance.now(); requestAnimationFrame(tick); },
  };
  seek(0);
  window.taupinReady = true;
  if (playing) requestAnimationFrame(tick);
}
