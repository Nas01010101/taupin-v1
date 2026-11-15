// Runs model/taupin.onnx with onnxruntime-web on the wasm backend (Node) and compares logits
// with model/reference_outputs.json, given the Python-preprocessed inputs dumped by make_samples.py.
//   node train/check_ortweb.mjs <ort-web dir with node_modules> model/taupin.onnx inputs.bin model/reference_outputs.json
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const [ortDir, modelPath, inputsPath, refPath] = process.argv.slice(2);
const require = createRequire(path.join(path.resolve(ortDir), "package.json"));
const ort = require("onnxruntime-web");
ort.env.wasm.numThreads = 1;

const ref = JSON.parse(readFileSync(refPath, "utf8"));
const S = ref.input_size;
const buf = readFileSync(inputsPath);
const all = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
const session = await ort.InferenceSession.create(readFileSync(modelPath), { executionProviders: ["wasm"] });
let maxDiff = 0;
for (let i = 0; i < ref.samples.length; i++) {
  const x = all.slice(i * 3 * S * S, (i + 1) * 3 * S * S);
  const out = await session.run({ image: new ort.Tensor("float32", x, [1, 3, S, S]) });
  const z = out.logits.data;
  const d = Math.max(...ref.samples[i].logits.map((v, k) => Math.abs(v - z[k])));
  maxDiff = Math.max(maxDiff, d);
  const top = ref.classes[z.indexOf(Math.max(...z))];
  console.log(JSON.stringify({ file: ref.samples[i].file, top1_wasm: top, top1_ref: ref.samples[i].top1, max_abs_diff: d }));
}
console.log(JSON.stringify({ ort_web: ort.env.versions?.web ?? "unknown", backend: "wasm", max_abs_diff: maxDiff }));
