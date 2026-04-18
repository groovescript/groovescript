import {
  EditorView, keymap, drawSelection, highlightActiveLine,
  EditorState, Compartment,
  defaultKeymap, history, historyKeymap,
} from './vendor/codemirror.bundle.js';

import {
  grooveScriptLanguage,
  gsHighlightLight,
  gsHighlightDark,
} from './gs-mode.js';

// ── Constants ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'groovescript_editor_v1';

const SEED = `\
// New GrooveScript chart — edit below, then tap Copy or Share

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

document.addEventListener('DOMContentLoaded', () => {
  const docContent = loadDoc();

  const state = EditorState.create({
    doc: docContent,
    extensions: [
      grooveScriptLanguage,
      themeCompartment.of(activeHighlight()),
      EditorView.lineWrapping,
      history(),
      keymap.of([...defaultKeymap, ...historyKeymap]),
      highlightActiveLine(),
      drawSelection(),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          scheduleSave(update.state.doc.toString());
        }
      }),
    ],
  });

  const view = new EditorView({
    state,
    parent: document.getElementById('editor'),
  });

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
