// Three.js scene for the parcel: terrain from the 2 m lidar DTM, one draped layer at a time
// (web/js/layers.js), tree crowns at the lidar treetops, a soil-profile skirt on the cut edge,
// bait-trap flags, an optional overlay of the low wet pocket, and photo pins (a stem plus the
// photo as a billboard). Machines and crop plants are left out; this tool is about the soil.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VIEWS, decode, colorOf } from './layers.js';

// Relief is drawn 2 times (12 m over 600 m would read flat); trees are drawn at their lidar height.
const TEX = 1200, EXAG = 2, PROFILE_DEPTH = 24;

// base: URL prefix of field.json's layer files ('data/').
export function createScene(container, field, base = 'data/') {
  const N = field.parcel.size, W = N * field.parcel.res_m;
  const byKey = Object.fromEntries(field.layers.map(l => [l.key, l]));
  const data = {};
  let H = new Float32Array(N * N), hmin = 0, view = 'terrain', showPocket = false;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);
  renderer.domElement.setAttribute('aria-label', '3D view of the parcel; drag to rotate, scroll to zoom');
  renderer.domElement.setAttribute('role', 'img');
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 1, 6000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.46;
  controls.minDistance = 40; controls.maxDistance = 2200;
  scene.add(new THREE.HemisphereLight(0xf2f6ff, 0x3a3020, 1.3));
  const sun = new THREE.DirectionalLight(0xfff2dc, 1.4);
  sun.position.set(-300, 500, -300);            // from the north-west, like the baked hillshade
  scene.add(sun);

  // ------------------------------------------------------------ terrain + draped layer
  const geo = new THREE.PlaneGeometry(W, W, N - 1, N - 1);
  geo.rotateX(-Math.PI / 2);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = TEX;
  const g2 = canvas.getContext('2d');
  const small = document.createElement('canvas');
  small.width = small.height = N;
  const s2 = small.getContext('2d');
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const terrain = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ map: tex }));
  scene.add(terrain);
  const px = TEX / (N - 1);

  function paint() {
    const v = VIEWS.find(x => x.key === view), lay = byKey[v.layer], vals = data[v.layer];
    const hs = data.hillshade, chm = data.canopy, n = lay.size, k = N / n;
    const img = s2.createImageData(N, N);
    for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) {
      const i = r * N + c;
      // 30 m layers: each 2 m cell takes its 30 m cell's value, so blocks stay visible.
      const val = n === N ? vals[i] : vals[Math.floor(r / k) * n + Math.floor(c / k)];
      let rgb = colorOf(lay, val) ?? [150, 146, 136];
      if (view === 'terrain' && chm[i] >= 2) rgb = [70, 96, 58];           // shade under crowns
      const s = 0.6 + 0.5 * hs[i];                 // flat ground (hs 0.71) at 0.95
      const o = i * 4;
      img.data[o] = rgb[0] * s; img.data[o + 1] = rgb[1] * s; img.data[o + 2] = rgb[2] * s; img.data[o + 3] = 255;
      if (showPocket && H[i] <= field.pocket.height_max_m) {
        img.data[o] = img.data[o] * 0.45 + 64 * 0.55; img.data[o + 1] = img.data[o + 1] * 0.45 + 150 * 0.55;
        img.data[o + 2] = img.data[o + 2] * 0.45 + 220 * 0.55;
      }
    }
    s2.putImageData(img, 0, 0);
    // Class and 30 m views stay blocky (nearest); 2 m views are smoothed between cell centres.
    g2.imageSmoothingEnabled = lay.kind !== 'classes' && n === N;
    g2.drawImage(small, -px / 2, -px / 2, TEX + px, TEX + px);   // pixel centres on the vertices
    tex.needsUpdate = true;
    trees.visible = view === 'terrain' || view === 'soil' || view === 'zones';
  }

  const heightAt = (row, col) => {
    const r = Math.max(0, Math.min(N - 1.001, row)), c = Math.max(0, Math.min(N - 1.001, col));
    const r0 = r | 0, c0 = c | 0, fr = r - r0, fc = c - c0, i = r0 * N + c0;
    const h = H[i] * (1 - fr) * (1 - fc) + H[i + 1] * (1 - fr) * fc + H[i + N] * fr * (1 - fc) + H[i + N + 1] * fr * fc;
    return (h - hmin) * EXAG;
  };
  const toWorld = (row, col) => new THREE.Vector3((col / (N - 1) - 0.5) * W, heightAt(row, col), (row / (N - 1) - 0.5) * W);

  // ------------------------------------------------------------ soil-profile skirt
  const profileTex = (() => {
    const c = document.createElement('canvas'); c.width = 8; c.height = 256;
    const x = c.getContext('2d');
    // 0-1.2 m over 24 world units (20x): Ap 0-0.25 m dark topsoil, B clay 0.25-0.9 m, C below; a pale line at
    // 0.10 m marks the TSOIL1 layer the trap window is read from.
    const band = (z0, z1, col) => { x.fillStyle = col; x.fillRect(0, (z0 / 1.2) * 256, 8, ((z1 - z0) / 1.2) * 256 + 1); };
    band(0, 0.25, '#4a3424'); band(0.25, 0.9, '#7a6450'); band(0.9, 1.2, '#8d8070');
    x.fillStyle = '#e8d9a0'; x.fillRect(0, (0.1 / 1.2) * 256 - 1, 8, 2);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  function skirt() {
    const verts = [], uv = [], idx = [];
    const edges = [[0, 0, 0, 1], [0, N - 1, 1, 0], [N - 1, N - 1, 0, -1], [N - 1, 0, -1, 0]];
    for (const [r0, c0, dr, dc] of edges) {
      const b = verts.length / 3;
      for (let k = 0; k < N; k++) {
        const p = toWorld(r0 + dr * k, c0 + dc * k);
        // The profile hangs from the surface: 0 at the ground line, 1.2 m (24 units) below it.
        verts.push(p.x, p.y, p.z, p.x, p.y - PROFILE_DEPTH, p.z);
        uv.push(0, 1, 0, 0);
        if (k) { const a = b + (k - 1) * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx); g.computeVertexNormals();
    scene.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ map: profileTex, side: THREE.DoubleSide })));
  }

  // ------------------------------------------------------------ trees (lidar treetops)
  const trees = new THREE.Group(); scene.add(trees);
  function plantTrees() {
    const list = field.trees, m = new THREE.Matrix4(), q = new THREE.Quaternion(), col = new THREE.Color();
    const crowns = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1),
      new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), list.length);
    list.forEach(([row, col0, h], i) => {
      // Crown shape is drawn, not measured: about 0.3 x height wide, the top 70 % of the tree.
      const r = Math.max(1.5, 0.3 * h), p = toWorld(row, col0);
      m.compose(new THREE.Vector3(p.x, p.y + h * 0.65, p.z), q, new THREE.Vector3(r, h * 0.35, r));
      crowns.setMatrixAt(i, m);
      crowns.setColorAt(i, col.setHSL(0.27 + (i % 7) * 0.008, 0.38, 0.2 + Math.min(h, 30) / 150));
    });
    trees.add(crowns);
  }

  // ------------------------------------------------------------ trap flags
  const traps = new THREE.Group(); scene.add(traps);
  const flagMat = new THREE.MeshLambertMaterial({ color: 0xf2efe6 });
  function letterSprite(txt) {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const x = c.getContext('2d');
    x.fillStyle = '#c8402c'; x.beginPath(); x.arc(32, 32, 28, 0, 7); x.fill();
    x.fillStyle = '#fff'; x.font = '600 36px Inter, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.fillText(txt, 32, 34);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false }));
    s.renderOrder = 3; return s;
  }
  function placeTraps() {
    for (const t of field.traps) {
      const g = new THREE.Group();
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 18, 6), flagMat); pole.position.y = 9;
      const tag = letterSprite(t.id); tag.position.y = 24; tag.scale.set(14, 14, 1);
      g.add(pole, tag);
      g.position.copy(toWorld(t.row, t.col));
      g.userData.trap = t.id;
      traps.add(g);
    }
  }

  // ------------------------------------------------------------ pins
  const pins = new THREE.Group(); scene.add(pins);
  const stemMat = new THREE.MeshLambertMaterial({ color: 0x1d2320 });
  function addPin({ row, col, thumb, color = 0xffffff, drop = 1 }) {
    const g = new THREE.Group();
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 60, 6), stemMat); stem.position.y = 30;
    const head = new THREE.Mesh(new THREE.SphereGeometry(5, 16, 12), new THREE.MeshLambertMaterial({ color }));
    head.position.y = 62;
    g.add(stem, head);
    if (thumb) {
      const t = new THREE.TextureLoader().load(thumb); t.colorSpace = THREE.SRGBColorSpace;
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false }));
      sp.scale.set(70, 70, 1); sp.position.y = 110; sp.renderOrder = 2;
      g.add(sp);
    }
    g.userData.cell = [row, col];
    g.userData.base = toWorld(row, col);
    g.userData.drop = drop;
    pins.add(g);
    setDrop(g, drop);
    return g;
  }
  function setDrop(g, k) {                       // k: 0 = above the view, 1 = planted
    g.userData.drop = k;
    const e = 1 - (1 - Math.min(1, Math.max(0, k))) ** 3;
    g.position.copy(g.userData.base);
    g.position.y = g.userData.base.y + (1 - e) * 400;
    g.visible = k > 0;
  }
  function clearPins() { pins.clear(); }

  // Click on terrain -> (row, col), so a photo without GPS can be placed by hand.
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let pickCb = null, down = null;
  renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObject(terrain)[0];
    if (hit) pickCb?.(Math.round((1 - hit.uv.y) * (N - 1)), Math.round(hit.uv.x * (N - 1)));
  });

  // ------------------------------------------------------------ load layers, build the mesh
  const ready = Promise.all(field.layers.map(async l => {
    const res = await fetch(base + l.file);
    if (!res.ok) throw new Error(`${l.file}: ${res.status}`);
    data[l.key] = decode(await res.arrayBuffer(), l.encoding);
  })).then(() => {
    H = data.height;
    hmin = Infinity;
    for (const h of H) if (h < hmin) hmin = h;      // no Math.min(...H): 90 000 arguments
    const pos = geo.attributes.position;
    for (let i = 0; i < N * N; i++) pos.setY(i, (H[i] - hmin) * EXAG);
    pos.needsUpdate = true;
    geo.computeVertexNormals();
    geo.computeBoundingSphere();
    skirt(); plantTrees(); placeTraps();
    // Pins added before the heights arrived sit at 0; lift them onto the ground.
    for (const g of pins.children) { g.userData.base = toWorld(...g.userData.cell); setDrop(g, g.userData.drop); }
    paint();
  });

  // ------------------------------------------------------------ camera + loop
  let orbitAngle = null, dist = 1100;
  function fit() {
    const dir = new THREE.Vector3(-0.56, 0.48, 0.73).normalize(), v = new THREE.Vector3();
    for (let d = 400; d <= 2200; d += 20) {
      camera.position.copy(dir).multiplyScalar(d); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
      const fits = [[-1, -1], [1, -1], [-1, 1], [1, 1]].every(([a, b]) => {
        v.set(a * W / 2, 0, b * W / 2).project(camera);
        return Math.abs(v.x) < 0.9 && Math.abs(v.y) < 0.82;
      });
      if (fits) { dist = d; break; }
    }
    controls.target.set(0, 0, 0);
  }
  // Fixed orbit for the demo: angle in radians around the parcel at the fitted distance.
  function setOrbit(angle) {
    orbitAngle = angle;
    const r = dist * 0.82, y = dist * 0.48;
    camera.position.set(Math.sin(angle) * r, y, Math.cos(angle) * r);
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
  }
  let userMoved = false;
  controls.addEventListener('start', () => { userMoved = true; });
  function resize() {
    const { clientWidth: w, clientHeight: h } = container;
    renderer.setSize(w, h, false); camera.aspect = w / Math.max(1, h); camera.updateProjectionMatrix();
    if (!userMoved) { fit(); if (orbitAngle !== null) setOrbit(orbitAngle); }
    renderer.render(scene, camera);
  }
  new ResizeObserver(resize).observe(container);
  let looping = true;
  renderer.setAnimationLoop(() => {
    if (!looping) return;
    if (orbitAngle === null) controls.update();
    renderer.render(scene, camera);
  });
  resize();

  const cellOk = (row, col) => Math.max(0, Math.min(N - 1, row)) * N + Math.max(0, Math.min(N - 1, col));
  return {
    ready, addPin, setDrop, clearPins, setOrbit,
    setPocket(on) { showPocket = on; if (data.height) paint(); },
    // key: one of VIEWS (terrain, twi, ndvi, lst, soil, zones).
    setLayer(key) { view = key; if (data.height) paint(); },
    get layer() { return view; },
    setTraps(on) { traps.visible = on; },
    onPick(cb) { pickCb = cb; },
    render() { renderer.render(scene, camera); },
    setLooping(on) { looping = on; },
    // Low wet pocket: lowest 15 % of parcel cells by lidar height (field.pocket); false until ready.
    isPocket: (row, col) => H[cellOk(row, col)] <= field.pocket.height_max_m && !!data.height,
    size: N,
    // The pitch deck sets controls.autoRotate on these; the render loop already calls controls.update().
    camera, controls,
  };
}
