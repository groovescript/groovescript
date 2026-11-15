import {
  EditorView, keymap, drawSelection, highlightActiveLine,
  EditorState, Compartment,
  defaultKeymap, history, historyKeymap,
  lintGutter, setDiagnostics, nextDiagnostic,
  autocompletion, snippetCompletion, hoverTooltip,
} from './vendor/codemirror.bundle.js';

import {
  grooveScriptLanguage,
  gsHighlightLight,
  gsHighlightDark,
} from './gs-mode.js';

import { createPreview } from './preview.js';
import { minimalChange } from './textchange.js';
import { analyze, options as assistOptions, hoverInfo } from './assist.js';

// ── Constants ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'groovescript_editor_v1';

const SEED = `\
// New GrooveScript chart — edit below. Preview shows the score; Play plays it.

metadata:
  title: "My Chart"
  tempo: 120
  time_signature: 4/4

groove "main groove":
  BD: 1, 3
  SN: 2, 4
  HH: *8

section "verse":
  bars: 8
  groove: "main groove"
`;

const SYMBOL_BUTTONS = [
  { label: '"',       insert: '"' },
  { label: ':',       insert: ':' },
  { label: ',',       insert: ', ' },
  { label: '*',       insert: '*' },
  { label: '#',       insert: '# ' },
  { label: '//',      insert: '// ' },
  { label: '1', insert: '1' },
  { label: '2', insert: '2' },
  { label: '3', insert: '3' },
  { label: '4', insert: '4' },
  { label: '&', insert: '&' },
  { label: 'e', insert: 'e' },
  { label: 'a', insert: 'a' },
  { label: 'groove',  insert: 'groove ' },
  { label: 'section', insert: 'section ' },
  { label: 'fill',    insert: 'fill ' },
  { label: 'at bar',  insert: 'at bar ' },
];

// ── Theme compartment ─────────────────────────────────────────────────────────

const themeCompartment = new Compartment();

function activeHighlight() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? gsHighlightDark()
    : gsHighlightLight();
}

// ── localStorage ──────────────────────────────────────────────────────────────

function loadDoc() {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? SEED;
  } catch {
    return SEED;
  }
}

let saveTimer = null;
function scheduleSave(doc) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(STORAGE_KEY, doc); } catch { /* quota exceeded */ }
  }, 500);
}

// ── Copy / Share ──────────────────────────────────────────────────────────────

function showFeedback(btn, text, ariaLabel) {
  const orig = btn.textContent;
  const origAria = btn.getAttribute('aria-label');
  btn.textContent = text;
  btn.setAttribute('aria-label', ariaLabel);
  btn.classList.add('feedback');
  setTimeout(() => {
    btn.textContent = orig;
    btn.setAttribute('aria-label', origAria);
    btn.classList.remove('feedback');
  }, 1500);
}

async function copyAll(view, btn) {
  const text = view.state.doc.toString();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  showFeedback(btn, 'Copied ✓', 'Copied to clipboard');
}

async function shareAll(view, btn) {
  const text = view.state.doc.toString();
  const payload = { text };
  if (!navigator.canShare || !navigator.canShare(payload)) return;
  try {
    await navigator.share(payload);
    showFeedback(btn, 'Shared ✓', 'Shared');
  } catch (e) {
    if (e.name !== 'AbortError') console.error(e);
  }
}

// ── Symbol accessory bar ──────────────────────────────────────────────────────

function buildSymbolBar(view) {
  const bar = document.getElementById('symbol-bar');
  for (const { label, insert } of SYMBOL_BUTTONS) {
    const btn = document.createElement('button');
    btn.className = 'sym-btn';
    btn.textContent = label;
    btn.setAttribute('aria-label', `Insert ${label}`);
    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault(); // keep focus in editor
      view.dispatch(view.state.replaceSelection(insert));
      view.focus();
    });
    bar.appendChild(btn);
  }
}

function updateSymbolBarPosition() {
  const bar = document.getElementById('symbol-bar');
  const vv = window.visualViewport;
  if (!vv) return;

  const keyboardUp = vv.height < window.innerHeight - 50;
  bar.style.display = keyboardUp ? 'flex' : 'none';

  if (keyboardUp) {
    const top = vv.offsetTop + vv.height;
    bar.style.top = `${top}px`;
    bar.style.position = 'fixed';
  }
}

// ── Editor setup ──────────────────────────────────────────────────────────────

let preview = null;

// ── Completion, hover, go to definition ───────────────────────────────────────

// Filled from the worker: the chart's names (each build) and the static
// vocabulary (once). See assist.js.
const assist = { symbols: null, vocab: null };

const WORD_KINDS = new Set(['line-start', 'modifiers', 'instruments', 'instruments+modifiers']);

function completionSource(context) {
  const text = context.state.doc.toString();
  const ctx = analyze(text, context.pos);
  if (!ctx) return null;
  // Word lists wait for a typed letter (or Ctrl-Space), so typing beats and
  // pressing Enter never pops a menu. Names open as soon as the quote does.
  if (WORD_KINDS.has(ctx.kind) && ctx.from === context.pos && !context.explicit) return null;
  const opts = assistOptions(ctx, assist);
  if (!opts.length) return null;
  const quoted = ctx.kind === 'names';
  return {
    from: ctx.from,
    validFor: quoted ? /^[^"]*$/ : /^[\w&-]*$/,
    options: opts.map((o) => {
      const base = { label: o.label, detail: o.detail, info: o.info, type: o.type, boost: o.boost };
      if (o.snippet) return snippetCompletion(o.snippet, base);
      if (quoted) {
        return {
          ...base,
          apply: (view, completion, from, to) => {
            const closes = view.state.sliceDoc(to, to + 1) === '"';
            const insert = completion.label + (closes ? '' : '"');
            view.dispatch({
              changes: { from, to, insert },
              selection: { anchor: from + completion.label.length + 1 },
              userEvent: 'input.complete',
            });
          },
        };
      }
      return { ...base, apply: o.apply ?? o.label };
    }),
  };
}

const hover = hoverTooltip((view, pos) => {
  const info = hoverInfo(view.state.doc.toString(), pos, assist);
  if (!info) return null;
  return {
    pos: info.from,
    end: info.to,
    above: true,
    create() {
      const dom = document.createElement('div');
      dom.className = 'gs-hover';
      const title = document.createElement('div');
      title.className = 'gs-hover-title';
      title.textContent = info.title;
      dom.appendChild(title);
      if (info.body) {
        const body = document.createElement('pre');
        body.className = 'gs-hover-body';
        body.textContent = info.body;
        dom.appendChild(body);
      }
      if (info.definitionLine) {
        const hint = document.createElement('div');
        hint.className = 'gs-hover-hint';
        hint.textContent = 'Ctrl/⌘-click or F12 to go to definition';
        dom.appendChild(hint);
      }
      return { dom };
    },
  };
}, { hoverTime: 350 });

function goToDefinition(view, pos = view.state.selection.main.head) {
  const info = hoverInfo(view.state.doc.toString(), pos, assist);
  if (!info || !info.definitionLine) return false;
  const line = view.state.doc.line(info.definitionLine);
  view.dispatch({
    selection: { anchor: line.from },
    effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
  });
  view.focus();
  return true;
}

const definitionClicks = EditorView.domEventHandlers({
  mousedown(event, view) {
    if (!(event.metaKey || event.ctrlKey) || event.button !== 0) return false;
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
    if (pos == null) return false;
    if (goToDefinition(view, pos)) {
      event.preventDefault();
      return true;
    }
    return false;
  },
});

async function formatDoc(view, btn = null) {
  const before = view.state.doc.toString();
  const result = await preview.format(before);
  if (view.state.doc.toString() !== before) return; // edited meanwhile; skip
  if (!result.ok) {
    if (result.unavailable) return;
    preview.flash('error', 'Fix the errors before formatting');
    return;
  }
  const change = minimalChange(before, result.text);
  if (change) view.dispatch({ changes: change, userEvent: 'input.format' });
  if (btn) showFeedback(btn, 'Done ✓', change ? 'Formatted' : 'Already formatted');
}

// Offline support / installable app (see sw.js). Served over https in
// production; localhost counts as secure for development.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch((err) => {
      console.warn('Offline support unavailable:', err);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const docContent = loadDoc();

  const state = EditorState.create({
    doc: docContent,
    extensions: [
      grooveScriptLanguage,
      themeCompartment.of(activeHighlight()),
      EditorView.lineWrapping,
      history(),
      // Before the default keymap, which binds Mod-Enter to insertBlankLine.
      keymap.of([
        { key: 'Mod-Enter', run: () => { preview.togglePlay(); return true; } },
        { key: 'Shift-Alt-f', run: (v) => { formatDoc(v); return true; } },
        { key: 'F12', run: (v) => goToDefinition(v) },
      ]),
      autocompletion({ override: [completionSource], icons: false }),
      hover,
      definitionClicks,
      keymap.of([...defaultKeymap, ...historyKeymap]),
      highlightActiveLine(),
      drawSelection(),
      lintGutter(),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          const text = update.state.doc.toString();
          scheduleSave(text);
          preview.sourceChanged(text);
        }
      }),
    ],
  });

  const view = new EditorView({
    state,
    parent: document.getElementById('editor'),
  });

  // Live compile, diagnostics, score preview and playback
  preview = createPreview({
    showDiagnostics: (diags) => view.dispatch(setDiagnostics(view.state, diags)),
    getDoc: () => view.state.doc,
    jumpToProblem: () => { view.focus(); nextDiagnostic(view); },
    onSymbols: (symbols) => { assist.symbols = symbols; },
    onVocabulary: (vocab) => { assist.vocab = vocab; },
  });
  preview.sourceChanged(view.state.doc.toString(), { immediate: true });

  // Format button (groovescript fmt, run by the in-browser compiler)
  const formatBtn = document.getElementById('btn-format');
  formatBtn.addEventListener('click', () => formatDoc(view, formatBtn));

  // Copy button
  const copyBtn = document.getElementById('btn-copy');
  copyBtn.addEventListener('click', () => copyAll(view, copyBtn));

  // Share button
  const shareBtn = document.getElementById('btn-share');
  if (!('share' in navigator)) {
    shareBtn.style.display = 'none';
  } else {
    shareBtn.addEventListener('click', () => shareAll(view, shareBtn));
  }

  // Symbol bar
  buildSymbolBar(view);

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', updateSymbolBarPosition);
    window.visualViewport.addEventListener('scroll', updateSymbolBarPosition);
  }

  // Light/dark theme switching
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', () => {
    view.dispatch({ effects: themeCompartment.reconfigure(activeHighlight()) });
  });

  view.focus();
});
