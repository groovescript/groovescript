// Module Web Worker that runs the real groovescript compiler (Python, via
// Pyodide) and the score engraver (Verovio) off the main thread.
//
// Messages in:
//   { type: 'init', local }                  start loading Pyodide
//   { type: 'build', id, source }            parse + compile + emit
//   { type: 'render', id, musicxml, width }  engrave MusicXML to SVG
// Messages out:
//   { type: 'status', state: 'loading' | 'ready' | 'failed', message }
//   { type: 'built', id, ok, diagnostics, musicxml, midi, title, barCount, ms }
//   { type: 'rendered', id, svgs, timemap, ms } | { type: 'render-failed', id, message }
//
// Builds are latest-wins: if several sources arrive while one is compiling,
// only the newest is compiled next.

import { depUrls } from './deps.js';

const BUNDLE_URL = new URL('py/groovescript-py.zip', import.meta.url).href;
const SITE_DIR = '/home/pyodide/groovescript-site';

let urls = null;
let pyReady = null; // Promise<build function>
let vrvReady = null; // Promise<VerovioToolkit>
let pendingBuild = null;
let building = false;
let pendingRender = null;
let rendering = false;

function post(msg, transfer) {
  self.postMessage(msg, transfer || []);
}

async function loadPython() {
  post({ type: 'status', state: 'loading', message: 'Loading compiler…' });
  const [{ loadPyodide }, bundle] = await Promise.all([
    import(`${urls.pyodide}pyodide.mjs`),
    fetch(BUNDLE_URL, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error(`could not fetch compiler bundle (HTTP ${r.status})`);
      return r.arrayBuffer();
    }),
  ]);
  const pyodide = await loadPyodide({ indexURL: urls.pyodide });
  pyodide.unpackArchive(bundle, 'zip', { extractDir: SITE_DIR });
  pyodide.runPython(`import sys; sys.path.insert(0, ${JSON.stringify(SITE_DIR)})`);
  const web = pyodide.pyimport('groovescript.web');
  // Warm up: parse the grammar and built-in libraries once now, so the first
  // real build is as fast as the rest.
  web.build('groove "warmup":\n  BD: 1\n').destroy?.();
  post({ type: 'status', state: 'ready', message: 'Compiler ready' });
  return web.build_js;
}

async function loadVerovio() {
  const [{ default: createVerovioModule }, { VerovioToolkit, enableLog, LOG_ERROR }] = await Promise.all([
    import(`${urls.verovio}verovio-module.mjs`),
    import(`${urls.verovio}verovio.mjs`),
  ]);
  const module = await createVerovioModule();
  enableLog(LOG_ERROR, module); // MusicXML import warnings are noise here
  return new VerovioToolkit(module);
}

async function pumpBuilds() {
  if (building) return;
  building = true;
  try {
    while (pendingBuild) {
      const { id, source } = pendingBuild;
      pendingBuild = null;
      let build;
      try {
        build = await pyReady;
      } catch {
        return; // status 'failed' already reported
      }
      const t0 = performance.now();
      let r;
      try {
        const pyResult = build(source);
        r = pyResult.toJs({ dict_converter: Object.fromEntries });
        pyResult.destroy();
      } catch (err) {
        r = { ok: false, diagnostics: [{
          severity: 'error', message: `compiler crashed: ${err && err.message || err}`,
          line: null, column: null, length: 1,
        }] };
      }
      const midi = r.midi ? new Uint8Array(r.midi) : null;
      post({
        type: 'built',
        id,
        ok: r.ok,
        diagnostics: r.diagnostics || [],
        musicxml: r.musicxml ?? null,
        midi,
        title: r.title ?? null,
        barCount: r.bar_count ?? 0,
        ms: Math.round(performance.now() - t0),
      }, midi ? [midi.buffer] : []);
    }
  } finally {
    building = false;
  }
}

async function pumpRenders() {
  if (rendering) return;
  rendering = true;
  try {
    while (pendingRender) {
      const { id, musicxml, width } = pendingRender;
      pendingRender = null;
      try {
        if (!vrvReady) vrvReady = loadVerovio();
        const tk = await vrvReady;
        const t0 = performance.now();
        const scale = width < 600 ? 32 : 40;
        tk.setOptions({
          pageWidth: Math.max(Math.round((width * 100) / scale), 1000),
          pageHeight: 60000,
          adjustPageHeight: true,
          scale,
          pageMarginLeft: 80,
          pageMarginRight: 40,
          pageMarginTop: 40,
          pageMarginBottom: 40,
          breaks: 'auto',
          header: 'auto',
          footer: 'none',
          svgViewBox: true,
          svgRemoveXlink: true,
        });
        if (!tk.loadData(musicxml)) throw new Error('the engraver could not read this score');
        const svgs = [];
        for (let p = 1; p <= tk.getPageCount(); p++) svgs.push(tk.renderToSVG(p));
        const timemap = tk.renderToTimemap({ includeMeasures: true });
        post({ type: 'rendered', id, svgs, timemap, ms: Math.round(performance.now() - t0) });
      } catch (err) {
        // Retry the engraver download next time if that is what failed.
        if (vrvReady) await vrvReady.catch(() => { vrvReady = null; });
        post({ type: 'render-failed', id, message: String(err && err.message || err) });
      }
    }
  } finally {
    rendering = false;
  }
}

self.onmessage = (e) => {
  const msg = e.data;
  switch (msg.type) {
    case 'init':
      if (pyReady) return;
      urls = depUrls({ local: !!msg.local });
      pyReady = loadPython();
      pyReady.catch((err) => {
        post({ type: 'status', state: 'failed', message: String(err && err.message || err) });
      });
      break;
    case 'build':
      pendingBuild = { id: msg.id, source: msg.source };
      pumpBuilds();
      break;
    case 'render':
      pendingRender = { id: msg.id, musicxml: msg.musicxml, width: msg.width };
      pumpRenders();
      break;
  }
};
