# Vendored libraries

Copied unmodified from the npm registry so the app runs offline with no CDN.

| Directory | Package | Version | Files | Licence |
|---|---|---|---|---|
| `three/` | `three` | 0.187.0 | `build/three.module.js`, `build/three.core.js`, `examples/jsm/controls/OrbitControls.js` | MIT |
| `ort/` | `onnxruntime-web` | 1.31.1 | `dist/ort.wasm.min.mjs`, `dist/ort-wasm-simd-threaded.mjs`, `dist/ort-wasm-simd-threaded.wasm` | MIT |
| `fonts/` | `@fontsource/instrument-serif`, `@fontsource/inter` | 5.3.0 | latin 400 (both), Inter latin 600, `.woff2` | OFL-1.1 (`OFL-*.txt`) |

To update: `npm pack three@<v> onnxruntime-web@<v>`, extract, copy the same files, and change the
version here and in `web/sw.js` (`CACHE`).
