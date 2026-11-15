// Live preview controller: talks to worker.js, pushes diagnostics into the
// editor, shows the engraved score, and drives playback.

import { toEditorDiagnostics, summarize } from './diagnostics.js';
import { Player } from './player.js';

const BUILD_DEBOUNCE_MS = 300;
const WIDE_QUERY = '(min-width: 900px)';
const PREF_KEY = 'groovescript_preview_wide_v1';

/**
 * @param {{ showDiagnostics(diags: object[]): void,
 *           getDoc(): import('@codemirror/state').Text,
 *           jumpToProblem(): void,
 *           onSymbols?(symbols: object): void,
 *           onVocabulary?(vocab: object): void }} editor
 */
export function createPreview(editor) {
  const $ = (id) => document.getElementById(id);
  const els = {
    toggle: $('btn-preview'),
    pane: $('preview'),
    score: $('score'),
    note: $('preview-note'),
    problems: $('problems'),
    problemsText: document.querySelector('#problems .problems-text'),
    play: $('btn-play'),
    pos: $('play-pos'),
    midi: $('btn-midi'),
    xml: $('btn-xml'),
  };

  const params = new URLSearchParams(location.search);
  const worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  const player = new Player();

  let compilerState = 'loading';
  let buildSeq = 0;
  let renderSeq = 0;
  let debounce = null;
  let lastGood = null; // { musicxml, midi, title }
  let renderedXml = null; // MusicXML currently on screen
  let renderedWidth = 0;
  let timemap = []; // Verovio timemap entries for the score on screen
  let measures = []; // [{ id, qstamp }] from the timemap, for tap-to-play
  let highlighted = [];
  let raf = null;

  // ── Layout: side-by-side on wide screens, full-screen toggle on phones ──

  const wide = window.matchMedia(WIDE_QUERY);
  let wideOpen = readPref() !== 'off';
  let narrowOpen = false;

  function isOpen() { return wide.matches ? wideOpen : narrowOpen; }

  function applyLayout() {
    const open = isOpen();
    document.body.dataset.preview = open ? 'on' : 'off';
    els.toggle.setAttribute('aria-pressed', String(open));
    els.toggle.textContent = !wide.matches && open ? 'Edit' : 'Preview';
    if (open) renderIfStale();
  }

  els.toggle.addEventListener('click', () => {
    if (wide.matches) {
      wideOpen = !wideOpen;
      writePref(wideOpen ? 'on' : 'off');
    } else {
      narrowOpen = !narrowOpen;
    }
    applyLayout();
  });
  wide.addEventListener('change', applyLayout);
  applyLayout();

  let resizeTimer = null;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (isOpen() && Math.abs(scoreWidth() - renderedWidth) > 40) {
        renderedXml = null;
        renderIfStale();
      }
    }, 200);
  }).observe(els.score);

  // ── Worker protocol ──

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'status') onStatus(msg);
    else if (msg.type === 'vocabulary') editor.onVocabulary?.(msg.vocab);
    else if (msg.type === 'built') onBuilt(msg);
    else if (msg.type === 'rendered') onRendered(msg);
    else if (msg.type === 'render-failed') onRenderFailed(msg);
    else if (msg.type === 'formatted') onFormatted(msg);
  };
  worker.onerror = (e) => {
    onStatus({ state: 'failed', message: e.message || 'the preview worker could not start' });
  };
  worker.postMessage({ type: 'init', local: params.has('local-deps') });

  function onStatus({ state, message }) {
    compilerState = state;
    if (state === 'failed') {
      setProblems('unavailable', `Live preview unavailable: ${message}`);
      setNote('The compiler could not be loaded (are you offline?). Editing still works.');
    }
  }

  function onBuilt(msg) {
    if (msg.id !== buildSeq) return; // a newer edit is already queued
    editor.showDiagnostics(toEditorDiagnostics(editor.getDoc(), msg.diagnostics));
    if (msg.symbols) editor.onSymbols?.(msg.symbols);
    const summary = summarize(msg.diagnostics);
    if (summary.level === 'ok') {
      const bars = msg.barCount ? `${msg.barCount} bar${msg.barCount === 1 ? '' : 's'} · ` : '';
      setProblems('ok', `${bars}No problems`);
    } else {
      setProblems(summary.level, summary.text);
    }

    if (msg.ok && msg.musicxml && msg.midi) {
      lastGood = { musicxml: msg.musicxml, midi: msg.midi, title: msg.title };
      player.load(msg.midi);
      setNote(null);
      renderIfStale();
    } else if (msg.ok) {
      // Valid, but nothing to show yet (no grooves or sections).
      lastGood = null;
      player.stop({ silent: true });
      renderSeq++; // drop any render still in flight for the old score
      renderedXml = null;
      timemap = [];
      measures = [];
      els.score.innerHTML = '<p class="score-empty">Add a groove or a section to see the score.</p>';
      setNote(null);
    } else if (lastGood) {
      setNote('Showing the last version that compiled. Fix the errors to update the score.');
    }
    updateControls();
  }

  function onRendered(msg) {
    if (msg.id !== renderSeq) return;
    const keepScroll = els.score.scrollTop;
    els.score.innerHTML = msg.svgs.join('');
    els.score.scrollTop = keepScroll;
    timemap = msg.timemap || [];
    measures = timemap.filter((t) => t.measureOn).map((t) => ({ id: t.measureOn, qstamp: t.qstamp }));
    highlighted = [];
    els.score.classList.toggle('can-seek', measures.length > 0);
  }

  function onRenderFailed(msg) {
    if (msg.id !== renderSeq) return;
    renderedXml = null;
    setNote(`Could not draw the score: ${msg.message}`);
  }

  // ── Builds and renders ──

  function sourceChanged(text, { immediate = false } = {}) {
    clearTimeout(debounce);
    // Claim the id now, not when the debounce fires: a result for an older
    // build that arrives during the debounce window describes text that has
    // since changed, and its line numbers no longer match the document.
    const id = ++buildSeq;
    const send = () => worker.postMessage({ type: 'build', id, source: text });
    if (immediate) send();
    else debounce = setTimeout(send, BUILD_DEBOUNCE_MS);
  }

  function scoreWidth() {
    return els.score.clientWidth || els.pane.clientWidth || window.innerWidth;
  }

  function renderIfStale() {
    if (!isOpen() || !lastGood || lastGood.musicxml === renderedXml) return;
    renderedXml = lastGood.musicxml;
    renderedWidth = scoreWidth();
    worker.postMessage({ type: 'render', id: ++renderSeq, musicxml: renderedXml, width: renderedWidth });
  }

  // ── Problems bar and notes ──

  function setProblems(level, text) {
    els.problems.dataset.level = level;
    els.problemsText.textContent = text;
  }

  els.problems.addEventListener('click', () => {
    const level = els.problems.dataset.level;
    if (level === 'error' || level === 'warning' || level === 'info') editor.jumpToProblem();
  });

  function setNote(text) {
    els.note.hidden = !text;
    els.note.textContent = text || '';
    els.score.classList.toggle('stale', !!text && !!lastGood);
  }

  // ── Playback ──

  function updateControls() {
    const ready = !!lastGood;
    els.play.disabled = !ready;
    els.midi.disabled = !ready;
    els.xml.disabled = !ready;
    els.play.textContent = player.playing ? '■ Stop' : '▶ Play';
    els.play.setAttribute('aria-label', player.playing ? 'Stop' : 'Play');
    els.play.classList.toggle('playing', player.playing);
  }

  async function togglePlay(fromSeconds = null) {
    if (!lastGood) return;
    if (player.playing && fromSeconds === null) {
      player.stop();
      return;
    }
    await player.play(fromSeconds ?? 0);
    updateControls();
    follow();
  }

  player.onEnd = () => {
    cancelAnimationFrame(raf);
    clearHighlight();
    els.pos.textContent = '';
    updateControls();
  };

  els.play.addEventListener('click', () => togglePlay());

  // Tap a bar in the score to play from there. Hit-test by bounding box so
  // a tap on the white space between notes still lands in its bar.
  els.score.addEventListener('click', (e) => {
    if (!lastGood || !measures.length) return;
    const hit = measureAt(e.clientX, e.clientY);
    if (hit) togglePlay(player.secondsAtQuarter(hit.qstamp));
  });

  function measureAt(x, y) {
    for (const m of measures) {
      const el = document.getElementById(m.id);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      // Pad vertically: staves are thin targets for a finger.
      if (x >= r.left && x <= r.right && y >= r.top - 24 && y <= r.bottom + 24) return m;
    }
    return null;
  }

  function follow() {
    cancelAnimationFrame(raf);
    const step = () => {
      if (!player.playing) return;
      els.pos.textContent = `${fmtTime(player.position)} / ${fmtTime(player.duration)}`;
      highlightAt(player.quarters);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  function highlightAt(q) {
    if (!timemap.length) return;
    // Latest timemap entry at or before q that starts notes.
    let lo = 0;
    let hi = timemap.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (timemap[mid].qstamp <= q + 1e-6) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    while (found >= 0 && !(timemap[found].on && timemap[found].on.length)) found--;
    const ids = found >= 0 ? timemap[found].on : [];
    if (ids === highlighted) return;
    clearHighlight();
    highlighted = ids;
    let first = null;
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add('playing');
        first = first || el;
      }
    }
    if (first) keepInView(first);
  }

  function clearHighlight() {
    for (const id of highlighted) {
      const el = document.getElementById(id);
      if (el) el.classList.remove('playing');
    }
    highlighted = [];
  }

  function keepInView(el) {
    const box = el.getBoundingClientRect();
    const view = els.score.getBoundingClientRect();
    if (box.top < view.top + 20 || box.bottom > view.bottom - 20) {
      els.score.scrollBy({ top: box.top - view.top - view.height / 3, behavior: 'smooth' });
    }
  }

  // ── Downloads ──

  function download(bytes, type, ext) {
    if (!lastGood) return;
    const blob = new Blob([bytes], { type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${slug(lastGood.title)}.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  els.midi.addEventListener('click', () => lastGood && download(lastGood.midi, 'audio/midi', 'mid'));
  els.xml.addEventListener('click', () =>
    lastGood && download(lastGood.musicxml, 'application/vnd.recordare.musicxml+xml', 'musicxml'));

  // ── Formatting (groovescript fmt) ──

  let formatSeq = 0;
  const pendingFormats = new Map(); // id -> resolve

  /** Format ``source``; resolves to { ok, text, diagnostics }. */
  function format(source) {
    if (compilerState === 'failed') {
      return Promise.resolve({ ok: false, text: null, diagnostics: [], unavailable: true });
    }
    const id = ++formatSeq;
    worker.postMessage({ type: 'format', id, source });
    return new Promise((resolve) => pendingFormats.set(id, resolve));
  }

  function onFormatted(msg) {
    const resolve = pendingFormats.get(msg.id);
    pendingFormats.delete(msg.id);
    if (resolve) resolve(msg);
  }

  /** Show a transient message in the problems bar (until the next build). */
  function flash(level, text) {
    setProblems(level, text);
  }

  return { sourceChanged, togglePlay: () => togglePlay(), format, flash };
}

function fmtTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function slug(title) {
  const s = String(title || 'chart')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return s || 'chart';
}

function readPref() {
  try { return localStorage.getItem(PREF_KEY); } catch { return null; }
}

function writePref(v) {
  try { localStorage.setItem(PREF_KEY, v); } catch { /* storage unavailable */ }
}
