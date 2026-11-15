// Editor assistance: what to suggest at the cursor, and what a hover shows.
//
// Pure functions over plain text so `node --test` can cover them; the
// CodeMirror glue lives in app.js. Names and vocabulary come from the real
// compiler (groovescript.web): `symbols` from each build (the chart's own
// grooves, fills, variations and sections with their line ranges) and
// `vocab` once at start-up (instruments with every alias the grammar
// accepts, modifiers, and the built-in library definitions).

const TUPLET_KINDS = ['triplet', 'quintuplet', 'sextuplet', 'septuplet', 'nonuplet'];

// Line-start completions per enclosing block. `snippet` uses CodeMirror's
// ${placeholder} syntax; `label` is what the user types and sees.
const TOP_LEVEL = [
  { label: 'groove', snippet: 'groove "${name}":\n  ${}', detail: 'define a groove' },
  { label: 'fill', snippet: 'fill "${name}":\n  ${}', detail: 'define a fill' },
  { label: 'section', snippet: 'section "${name}":\n  bars: ${8}\n  groove: "${}"', detail: 'add a section' },
  { label: 'variation', snippet: 'variation "${name}":\n  ${}', detail: 'define a reusable variation' },
  { label: 'title', snippet: 'title: "${}"', detail: 'metadata' },
  { label: 'tempo', snippet: 'tempo: ${120}', detail: 'metadata: BPM' },
  { label: 'time_signature', snippet: 'time_signature: ${4/4}', detail: 'metadata' },
  { label: 'feel', snippet: 'feel: swing', detail: 'metadata: swing eighths' },
  { label: 'default_groove', snippet: 'default_groove: "${}"', detail: 'metadata' },
  { label: 'default_bars', snippet: 'default_bars: ${8}', detail: 'metadata' },
  { label: 'lyrics_style', snippet: 'lyrics_style: ${staff}', detail: 'metadata: staff | line' },
  { label: 'crash in', snippet: 'crash in', detail: 'crash on bar 1 of every later section' },
];

const PATTERN_BODY = [
  { label: 'bar', snippet: 'bar ${1}:\n  ${}', detail: 'start a bar of a multi-bar groove/fill' },
  { label: 'count', snippet: 'count "${}":\n  ${}', detail: 'count-labelled block' },
  { label: 'extend', snippet: 'extend: "${}"', detail: 'build on another groove/fill' },
  { label: 'like', snippet: 'like: bar ${1}', detail: 'copy an earlier bar' },
  { label: 'text', snippet: 'text: "${}"', detail: 'bar text' },
  { label: 'cresc', snippet: 'cresc from bar ${1} to bar ${2}', detail: 'crescendo hairpin' },
  { label: 'decresc', snippet: 'decresc from bar ${1} to bar ${2}', detail: 'decrescendo hairpin' },
];

const VARIATION_ACTIONS = [
  { label: 'add', snippet: 'add ${CR} at ${1}', detail: 'add hits' },
  { label: 'remove', snippet: 'remove ${HH} at ${1}', detail: 'remove hits' },
  { label: 'replace', snippet: 'replace ${HH} with ${RD} at ${*}', detail: 'swap instruments' },
  { label: 'modify', snippet: 'modify add ${accent} to ${SN} at ${2}', detail: 'add/remove a modifier on hits' },
];

const SECTION_BODY = [
  { label: 'bars', snippet: 'bars: ${8}', detail: 'section length' },
  { label: 'groove', snippet: 'groove: "${}"', detail: 'groove for the section' },
  { label: 'repeat', snippet: 'repeat: ${2}', detail: 'repeat the groove phrase' },
  { label: 'like', snippet: 'like "${}"', detail: 'inherit from another section' },
  { label: 'play', snippet: 'play:\n  groove "${}" x${4}', detail: 'arrange grooves/bars in order' },
  { label: 'fill', snippet: 'fill "${}" at bar ${4}', detail: 'place a fill' },
  { label: 'fill at', snippet: 'fill at bar ${4}:\n  ${}', detail: 'one-off inline fill' },
  { label: 'variation', snippet: 'variation at bar ${4}:\n  ${}', detail: 'change bars of the groove' },
  { label: 'variation "…"', snippet: 'variation "${}" at bar ${4}', detail: 'apply a named variation' },
  { label: 'cue', snippet: 'cue "${}" at bar ${1}', detail: 'text cue above the staff' },
  { label: 'tempo', snippet: 'tempo: ${120}', detail: 'section tempo' },
  { label: 'time_signature', snippet: 'time_signature: ${4/4}', detail: 'section meter' },
  { label: 'cresc', snippet: 'cresc from bar ${1} to bar ${2}', detail: 'crescendo hairpin' },
  { label: 'decresc', snippet: 'decresc from bar ${1} to bar ${2}', detail: 'decrescendo hairpin' },
  { label: 'rit', snippet: 'rit from bar ${7} to bar ${8}', detail: 'gradually slow down' },
  { label: 'accel', snippet: 'accel from bar ${1} to bar ${2}', detail: 'gradually speed up' },
  { label: 'a tempo', snippet: 'a tempo at bar ${1}', detail: 'back to the section tempo' },
  { label: 'crash in', snippet: 'crash in', detail: 'crash on the first beat' },
  { label: 'no crash in', snippet: 'no crash in', detail: 'opt out of a top-level crash in' },
  { label: 'break', snippet: 'break on bar ${4}', detail: 'silence bars/beats' },
  { label: 'lyrics', snippet: 'lyrics:\n  bar ${1}: "${1 2 3 4}" "${words}"', detail: 'timed lyrics' },
];

/** Hover help for keywords (instruments and modifiers come from vocab). */
export const KEYWORD_DOCS = {
  rit: 'rit from bar N [beat X] to bar M [beat Y] [to tempo T] — slow down gradually (default: to 80%).',
  ritardando: 'Same as rit.',
  accel: 'accel from bar N [beat X] to bar M [beat Y] [to tempo T] — speed up gradually (default: to 120%).',
  accelerando: 'Same as accel.',
  cresc: 'cresc from bar N [beat X] to bar M [beat Y] — crescendo hairpin.',
  decresc: 'decresc from bar N [beat X] to bar M [beat Y] — decrescendo hairpin.',
  extend: 'extend: "name" — start from another groove/fill and override or add lines.',
  like: 'like "section" — inherit a section (add `with fills, variations, cues, lyrics` for more); like: bar N copies a bar.',
  play: 'play: — list grooves (groove "x" x4), one-off bars (bar "x":) and rests (rest x2) in order.',
  repeat: 'repeat: N — play the groove phrase N times.',
  break: 'break on bar N [beat X] [through|until bar M [beat Y]] — silence a range.',
};

// ── Context analysis ─────────────────────────────────────────────────────────

// ``key: value`` lines that are settings, not instrument pattern lines.
const SETTING_KEYS = new Set([
  'title', 'tempo', 'time_signature', 'dsl_version', 'default_groove', 'default_bars',
  'feel', 'lyrics_style', 'bars', 'groove', 'repeat', 'extend', 'count', 'notes',
  'text', 'like', 'play', 'metadata', 'lyrics', 'bar',
]);

/**
 * What kind of completion fits at `pos` in `text`.
 * @returns {{ kind: string, from: number, block?: string, quoted?: boolean } | null}
 *   kinds: 'names' (with `names`: grooves|fills|sections|variations),
 *   'line-start' (with `block`), 'modifiers', 'instruments',
 *   'instruments+modifiers', 'tuplet-kinds'
 */
export function analyze(text, pos) {
  const lineStart = text.lastIndexOf('\n', pos - 1) + 1;
  const before = text.slice(lineStart, pos);
  if (inComment(before)) return null;

  const quote = openQuote(before);
  if (quote !== null) {
    const head = before.slice(0, quote);
    const from = lineStart + quote + 1;
    const block = enclosingBlock(text, lineStart);
    let names = null;
    if (/\b(?:default_groove\s*:|groove\s*:?)\s*$/.test(head)) names = 'grooves';
    else if (/\bextend\s*:\s*$/.test(head)) names = block === 'fill' ? 'fills' : 'grooves';
    else if (/\blike\s+$/.test(head)) names = 'sections';
    else if (/\bfill\s+$/.test(head) && block === 'section') names = 'fills';
    else if (/\bvariation\s+$/.test(head) && block === 'section') names = 'variations';
    return names ? { kind: 'names', names, from } : null;
  }

  const word = /[\w&-]*$/.exec(before)[0];
  const from = pos - word.length;
  const lead = before.slice(0, before.length - word.length);

  if (/\{[^}]*$/.test(lead) && /\{\s*$/.test(lead)) return { kind: 'tuplet-kinds', from };
  if (/^\s*$/.test(lead)) {
    const block = lead.length === 0 ? 'top' : enclosingBlock(text, lineStart);
    return { kind: 'line-start', block, from };
  }
  if (/^\d/.test(word)) return null; // typing a beat number
  if (!/\bat\b/.test(lead)) {
    if (/^\s*add\s+$/.test(lead)) return { kind: 'instruments', from };
    if (/^\s*add\b/.test(lead)) return { kind: 'instruments+modifiers', from };
    if (/^\s*(?:remove|replace)\b/.test(lead)) return { kind: 'instruments', from };
  }
  if (/^\s*modify\s+(?:add|remove)\s+$/.test(lead)) return { kind: 'modifiers', from };
  if (/^\s*modify\s+(?:add|remove)\b.*\b(?:to|from)\s+$/.test(lead)) return { kind: 'instruments', from };
  if (/^\s*\d[\w&]*\s*:/.test(lead)) return { kind: 'instruments+modifiers', from };
  const key = /^\s*([A-Za-z][\w-]*)\s*:/.exec(lead);
  if (key && !SETTING_KEYS.has(key[1]) && /\d[\w&]*(?:\s+[a-z][\w:]*)*\s+$/.test(lead)) {
    return { kind: 'modifiers', from };
  }
  return null;
}

function inComment(before) {
  let inString = false;
  for (let i = 0; i < before.length; i++) {
    const ch = before[i];
    if (inString) {
      if (ch === '\\') i++;
      else if (ch === '"') inString = false;
    } else if (ch === '"') inString = true;
    else if (ch === '#' || before.startsWith('//', i)) return true;
  }
  return false;
}

/** Index of an unclosed `"` in `before`, or null. */
function openQuote(before) {
  let open = null;
  for (let i = 0; i < before.length; i++) {
    const ch = before[i];
    if (open !== null) {
      if (ch === '\\') i++;
      else if (ch === '"') open = null;
    } else if (ch === '"') open = i;
  }
  return open;
}

const HEADER_RES = [
  ['section', /^\s*section\s+"[^"]*"\s*:/],
  ['groove', /^\s*groove\s+"[^"]*"\s*:/],
  ['fill', /^\s*fill\s+"[^"]*"\s*:/],
  ['variation', /^\s*variation\s+"[^"]*"\s*:/],
  ['metadata', /^\s*metadata\s*:/],
];

/** Block kind enclosing the line that starts at `lineStart`: the nearest
 *  top-level header above it (indentation is not significant in .gs). */
export function enclosingBlock(text, lineStart) {
  const lines = text.slice(0, lineStart).split('\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    for (const [kind, re] of HEADER_RES) {
      if (re.test(lines[i])) {
        // An inline named groove inside play: belongs to its section.
        if (kind === 'groove' && /^\s+/.test(lines[i]) && insideSection(lines, i)) return 'section';
        return kind;
      }
    }
  }
  return 'top';
}

function insideSection(lines, index) {
  for (let i = index - 1; i >= 0; i--) {
    if (/^\S/.test(lines[i])) return /^section\b/.test(lines[i]);
  }
  return false;
}

// ── Options ──────────────────────────────────────────────────────────────────

/**
 * Completion options for an `analyze` result.
 * @returns {Array<{ label: string, detail?: string, info?: string,
 *                   snippet?: string, apply?: string, type: string, boost?: number }>}
 */
export function options(ctx, { symbols, vocab }) {
  if (!ctx) return [];
  switch (ctx.kind) {
    case 'names': return nameOptions(ctx.names, symbols, vocab);
    case 'line-start': return lineStartOptions(ctx.block, vocab);
    case 'modifiers': return modifierOptions(vocab);
    case 'instruments': return instrumentOptions(vocab, '');
    case 'instruments+modifiers': return [...instrumentOptions(vocab, ''), ...modifierOptions(vocab)];
    case 'tuplet-kinds': return TUPLET_KINDS.map((k) => ({ label: k, type: 'type', detail: 'tuplet' }));
    default: return [];
  }
}

function nameOptions(kind, symbols, vocab) {
  const seen = new Set();
  const out = [];
  for (const s of (symbols && symbols[kind]) || []) {
    if (seen.has(s.name)) continue;
    seen.add(s.name);
    out.push({ label: s.name, type: 'variable', detail: `line ${s.line}`, boost: 2 });
  }
  const library = (vocab && vocab.library && vocab.library[kind]) || [];
  for (const entry of library) {
    if (seen.has(entry.name)) continue; // a chart definition overrides the library
    seen.add(entry.name);
    out.push({ label: entry.name, type: 'constant', detail: 'built-in', info: entry.text });
  }
  return out;
}

function lineStartOptions(block, vocab) {
  const snippets = {
    top: TOP_LEVEL,
    metadata: TOP_LEVEL.filter((s) => /metadata|swing|BPM/.test(s.detail) && s.label !== 'crash in'),
    groove: PATTERN_BODY,
    fill: PATTERN_BODY,
    variation: VARIATION_ACTIONS,
    section: [...SECTION_BODY, ...VARIATION_ACTIONS],
  }[block] || [];
  const out = snippets.map((s) => ({ ...s, type: 'keyword' }));
  if (block === 'groove' || block === 'fill' || block === 'section') {
    out.push(...instrumentOptions(vocab, ': ', -1));
  }
  return out;
}

function instrumentOptions(vocab, suffix, boost = 0) {
  const out = [];
  for (const inst of (vocab && vocab.instruments) || []) {
    for (const alias of inst.aliases) {
      out.push({
        label: alias,
        apply: alias + suffix,
        type: 'type',
        detail: alias === inst.code ? inst.name : `${inst.code} · ${inst.name}`,
        boost: alias === inst.code ? boost : boost - 1,
      });
    }
  }
  return out;
}

function modifierOptions(vocab) {
  return ((vocab && vocab.modifiers) || []).map((m) => ({
    label: m.name, type: 'property', detail: 'modifier', info: m.doc,
  }));
}

// ── Hover ────────────────────────────────────────────────────────────────────

/**
 * What a hover at `pos` should explain.
 * @returns {{ from: number, to: number, title: string, body?: string,
 *             definitionLine?: number } | null}
 */
export function hoverInfo(text, pos, { symbols, vocab }) {
  const lineStart = text.lastIndexOf('\n', pos - 1) + 1;
  let lineEnd = text.indexOf('\n', pos);
  if (lineEnd < 0) lineEnd = text.length;
  const line = text.slice(lineStart, lineEnd);
  const col = pos - lineStart;
  if (inComment(line.slice(0, col))) return null;

  // A quoted name?
  for (const m of line.matchAll(/"((?:[^"\\]|\\.)*)"/g)) {
    const start = m.index;
    const end = start + m[0].length;
    if (col < start || col > end) continue;
    const head = line.slice(0, start);
    const kinds = /\bextend\s*:\s*$/.test(head) ? ['grooves', 'fills']
      : /\b(?:default_groove\s*:|groove\s*:?)\s*$/.test(head) ? ['grooves']
      : /\blike\s+$/.test(head) ? ['sections']
      : /\bfill\s+$/.test(head) ? ['fills']
      : /\bvariation\s+$/.test(head) ? ['variations']
      : null;
    if (!kinds) return null;
    const name = m[1];
    for (const kind of kinds) {
      const def = ((symbols && symbols[kind]) || []).find((s) => s.name === name);
      if (def) {
        const defLines = text.split('\n').slice(def.line - 1, Math.min(def.end_line, def.line + 11));
        const more = def.end_line - def.line + 1 > 12 ? '\n  …' : '';
        return {
          from: lineStart + start, to: lineStart + end,
          title: `${singular(kind)} "${name}" — line ${def.line}`,
          body: defLines.join('\n') + more,
          definitionLine: def.line,
        };
      }
      const lib = ((vocab && vocab.library && vocab.library[kind]) || []).find((e) => e.name === name);
      if (lib) {
        return {
          from: lineStart + start, to: lineStart + end,
          title: `built-in ${singular(kind)} "${name}"`,
          body: lib.text,
        };
      }
    }
    return {
      from: lineStart + start, to: lineStart + end,
      title: `no ${kinds.map(singular).join(' or ')} named "${name}"`,
    };
  }

  // A word: instrument, modifier or keyword.
  const re = /[A-Za-z][\w-]*(?::[\w-]+)?/g;
  let m;
  while ((m = re.exec(line))) {
    const start = m.index;
    const end = start + m[0].length;
    if (col < start || col > end) continue;
    const word = m[0];
    const base = word.split(':')[0];
    const inst = ((vocab && vocab.instruments) || []).find((i) => i.aliases.includes(word));
    if (inst) {
      const others = inst.aliases.filter((a) => a !== word);
      return {
        from: lineStart + start, to: lineStart + end,
        title: `${inst.code} — ${inst.name}`,
        body: others.length ? `Also written: ${others.join(', ')}` : undefined,
      };
    }
    const mod = ((vocab && vocab.modifiers) || []).find((x) => x.name === base);
    if (mod) return { from: lineStart + start, to: lineStart + end, title: base, body: mod.doc };
    const doc = KEYWORD_DOCS[word];
    if (doc) return { from: lineStart + start, to: lineStart + end, title: word, body: doc };
    if (word === 'a' && /^a\s+tempo/.test(line.slice(start))) {
      return { from: lineStart + start, to: lineStart + start + 7, title: 'a tempo', body: 'a tempo at bar N [beat X] — return to the section tempo after a rit/accel.' };
    }
    return null;
  }
  return null;
}

function singular(kind) {
  return { grooves: 'groove', fills: 'fill', sections: 'section', variations: 'variation' }[kind] || kind;
}
