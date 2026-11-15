// Three.js scene for the parcel, ported from field-shift web/twin/scene.js: terrain from NASADEM
// heights, the HLS true-colour texture, an optional overlay of the low wet pocket, a soil-profile
// skirt, and photo pins (a stem plus the photo as a billboard). Machines and crop plants from the
// original are left out; this tool is about what lives in the soil.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const TEX = 1024, EXAG = 3, PROFILE_DEPTH = 24;

export function createScene(container, field, textureUrl) {
  const N = field.parcel.size, W = N * field.parcel.res_m;
  const H = Float32Array.from(field.height), hmin = Math.min(...H);
  const pocket = field.pocket;

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
  controls.minDistance = 150; controls.maxDistance = 2200;
  scene.add(new THREE.HemisphereLight(0xf2f6ff, 0x3a3020, 1.15));
  const sun = new THREE.DirectionalLight(0xfff2dc, 1.5);
  sun.position.set(-300, 500, -200);
  scene.add(sun);

  // ------------------------------------------------------------ terrain + ground texture
  const geo = new THREE.PlaneGeometry(W, W, N - 1, N - 1);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  for (let i = 0; i < N * N; i++) pos.setY(i, (H[i] - hmin) * EXAG);
  geo.computeVertexNormals();
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = TEX;
  const g2 = canvas.getContext('2d');
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const terrain = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ map: tex }));
  scene.add(terrain);
  const sat = new Image();
  const ready = new Promise(r => { sat.onload = r; sat.onerror = r; });
  sat.src = textureUrl;
  let showPocket = false;
  const px = TEX / (N - 1);

  function paint() {
    // Pixel centres sit on the terrain vertices (cell centres), like the pocket overlay below.
    g2.imageSmoothingEnabled = false;
    if (sat.naturalWidth) g2.drawImage(sat, -px / 2, -px / 2, TEX + px, TEX + px);
    else { g2.fillStyle = '#5a5140'; g2.fillRect(0, 0, TEX, TEX); }
    if (showPocket) {
      g2.fillStyle = 'rgba(64,150,220,0.55)';
      for (let i = 0; i < N * N; i++) if (pocket[i]) g2.fillRect(((i % N) - 0.5) * px, (((i / N) | 0) - 0.5) * px, px + 1, px + 1);
    }
    tex.needsUpdate = true;
  }
  ready.then(paint);

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
  {
    const verts = [], uv = [], idx = [];
    const edges = [[0, 0, 0, 1], [0, N - 1, 1, 0], [N - 1, N - 1, 0, -1], [N - 1, 0, -1, 0]];
    for (const [r0, c0, dr, dc] of edges) {
      const base = verts.length / 3;
      for (let k = 0; k < N; k++) {
        const p = toWorld(r0 + dr * k, c0 + dc * k);
        verts.push(p.x, p.y, p.z, p.x, -PROFILE_DEPTH, p.z);
        uv.push(0, 1, 0, 1 - (p.y + PROFILE_DEPTH) / PROFILE_DEPTH);   // 1 unit = 5 cm; C horizon clamps below
        if (k) { const a = base + (k - 1) * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx); g.computeVertexNormals();
    scene.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ map: profileTex, side: THREE.DoubleSide })));
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
    g.userData.base = toWorld(row, col);
    g.position.copy(g.userData.base);
    pins.add(g);
    setDrop(g, drop);
    return g;
  }
  function setDrop(g, k) {                       // k: 0 = above the view, 1 = planted
    const e = 1 - (1 - Math.min(1, Math.max(0, k))) ** 3;
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

  return {
    ready, addPin, setDrop, clearPins, setOrbit,
    setPocket(on) { showPocket = on; paint(); },
    onPick(cb) { pickCb = cb; },
    render() { renderer.render(scene, camera); },
    setLooping(on) { looping = on; },
    isPocket: (row, col) => !!pocket[Math.max(0, Math.min(N - 1, row)) * N + Math.max(0, Math.min(N - 1, col))],
    size: N,
    // The pitch deck sets controls.autoRotate on these; the render loop already calls controls.update().
    camera, controls,
  };
}
