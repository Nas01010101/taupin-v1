// Loads model/labels.json + model/taupin.onnx with onnxruntime-web (vendored wasm, one thread so
// no cross-origin isolation is needed) and classifies RGBA pixels. When the model is not
// installed the app keeps working and says so; see README "Obtaining the model".
import { checkLabels, preprocess, softmax, decide } from './classify.js';

export async function loadModel({ ort, base = 'model/', wasmPaths = 'vendor/ort/', fetchFn = fetch, modelBytes = null }) {
  let labels;
  try {
    const r = await fetchFn(`${base}labels.json`, { cache: 'no-cache' });
    if (!r.ok) return { status: 'missing', reason: `model/labels.json: HTTP ${r.status}` };
    labels = checkLabels(await r.json());
  } catch (e) {
    return { status: 'missing', reason: e.message };
  }
  try {
    let bytes = modelBytes;
    if (!bytes) {
      const r = await fetchFn(`${base}taupin.onnx`);
      if (!r.ok) return { status: 'missing', reason: `model/taupin.onnx: HTTP ${r.status}`, labels };
      bytes = new Uint8Array(await r.arrayBuffer());
    }
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.wasmPaths = wasmPaths;
    const session = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] });
    return { status: 'ready', labels, session, ort };
  } catch (e) {
    return { status: 'error', reason: e.message, labels };
  }
}

export async function classifyPixels(model, data, w, h) {
  const { ort, session, labels } = model, s = labels.input_size;
  const x = new ort.Tensor('float32', preprocess(data, w, h, labels), [1, 3, s, s]);
  const out = await session.run({ [session.inputNames[0]]: x });
  const logits = out[session.outputNames[0]].data;
  return decide(softmax(logits, Number(labels.temperature ?? 1)), labels);
}
