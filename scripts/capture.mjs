// Drive a local headless Chrome over the DevTools protocol (Node 22+, no npm packages):
//   node scripts/capture.mjs <url> --shot out.png [--width 1280 --height 720]
//   node scripts/capture.mjs <url>?demo=1&pause=1 --frames <dir> [--fps 10]
//   node scripts/capture.mjs <url> --eval "document.title"
// Prints console errors and exceptions. --frames seeks window.taupinDemo frame by frame, so the
// frames are the same on every run; then `python scripts/make_gif.py <dir>` builds the GIF.
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2), url = args[0];
const opt = (k, d) => { const i = args.indexOf(`--${k}`); return i > 0 ? args[i + 1] : d; };
const W = Number(opt('width', 1280)), H = Number(opt('height', 720)), FPS = Number(opt('fps', 10));
const CHROME = process.env.CHROME ?? {
  darwin: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', win32: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
}[process.platform] ?? 'google-chrome';
if (!url) { console.error('usage: node scripts/capture.mjs <url> --shot out.png | --frames dir'); process.exit(2); }

const profile = mkdtempSync(join(process.env.CAPTURE_TMP ?? tmpdir(), 'taupin-chrome-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--hide-scrollbars',
  '--use-angle=swiftshader', '--enable-unsafe-swiftshader', `--window-size=${W},${H}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((ok, bad) => {
  let buf = '';
  chrome.stderr.on('data', d => { buf += d; const m = buf.match(/ws:\/\/[^\s]+/); if (m) ok(m[0]); });
  chrome.on('exit', c => bad(new Error(`chrome exited ${c}`)));
  setTimeout(() => bad(new Error('chrome did not start')), 15000);
});
const port = new URL(wsUrl).port;
const page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pending = new Map(), errors = [];
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push(`exception: ${m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text}`);
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) errors.push(`console.${m.params.type}: ${m.params.args.map(a => a.value ?? a.description).join(' ')}`);
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(`log: ${m.params.entry.text} ${m.params.entry.url ?? ''}`);
});
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async expr => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const shot = async file => writeFileSync(file, Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).result.data, 'base64'));

try {
  await Promise.all(['Runtime.enable', 'Log.enable', 'Page.enable'].map(m => send(m)));
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: W < 500 });
  if (args.includes('--dark')) await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'dark' }] });
  await send('Page.navigate', { url });
  const t0 = Date.now();
  while (!(await evaluate('!!window.taupinReady')) && Date.now() - t0 < 30000) await new Promise(r => setTimeout(r, 200));
  console.log(`ready after ${Date.now() - t0} ms; model: ${await evaluate("document.querySelector('#model-status')?.textContent")}`);
  if (opt('eval')) console.log('eval:', JSON.stringify(await evaluate(opt('eval'))));
  const frames = opt('frames');
  if (frames) {
    mkdirSync(frames, { recursive: true });
    const len = await evaluate('window.taupinDemo?.length');
    if (!len) throw new Error('window.taupinDemo is missing: open the URL with ?demo=1');
    const n = Math.round(len * FPS);
    for (let i = 0; i <= n; i++) {
      await evaluate(`window.taupinDemo.seek(${i / FPS})`);
      await new Promise(r => setTimeout(r, i ? 60 : 1500));   // first frame: let textures settle
      await shot(join(frames, `f${String(i).padStart(4, '0')}.png`));
    }
    console.log(`${n + 1} frames at ${FPS} fps (${len} s) in ${frames}`);
  }
  if (opt('shot')) { await new Promise(r => setTimeout(r, Number(opt('wait', 1500)))); await shot(opt('shot')); console.log('screenshot', opt('shot')); }
} finally {
  console.log(errors.length ? errors.join('\n') : 'no console errors');
  ws.close(); chrome.kill();
  await new Promise(r => setTimeout(r, 300));
  rmSync(profile, { recursive: true, force: true });
}
