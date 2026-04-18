import {
  StreamLanguage, HighlightStyle, syntaxHighlighting,
} from './vendor/codemirror.bundle.js';
import { tags } from './vendor/codemirror.bundle.js';

// ── Keyword sets ──────────────────────────────────────────────────────────────

const INSTRUMENTS = new Set([
  'BD','SN','HH','OH','RD','CR','FT','HT','MT','SCS','HF',
  'bd','sn','hh','oh','rd','cr','ft','ht','mt','hf',
  'bass','kick','snare','click','hihat','openhat','hat','open',
  'ride','crash','lowtom','floortom','hightom','hitom','midtom',
  'hihatfoot','footchick',
  'cross-stick','hi-hat-foot','foot-chick',
]);

const MODIFIERS = new Set([
  'ghost','accent','flam','drag','double','buzz',
]);

const DEFINITIONS = new Set(['groove','fill','section']);

const META_KWS = new Set([
  'metadata','title','tempo','time_signature','dsl_version',
  'default_groove','default_bars',
]);

const BODY_KWS = new Set([
  'bars','count','notes','repeat','like','with',
  'play','cue','variation','text','extend',
  'cresc','decresc','crescendo','decrescendo',
]);

const PLACEMENT_KWS = new Set([
  'at','bar','bars','beat','placeholder','rest','from','to','except',
]);

const ACTION_KWS = new Set(['add','remove','replace','modify']);

const BARE_BEAT_WORDS = new Set(['trip','let','and']);

// Negative lookahead (?!\d) prevents matching 3-digit numbers like 120 as beat labels.
const BEAT_LABEL_RE = /^[1-9][0-9]?(?:trip|let|and|[e&atl])?(?!\d)/;

// ── Tokeniser ─────────────────────────────────────────────────────────────────

export function token(stream, _state) {
  // Follow CM convention: return null for whitespace so the machinery resets
  // stream.start before the next token call (otherwise current() includes spaces).
  if (stream.eatSpace()) return null;
  if (stream.eol()) return null;

  const ch = stream.peek();

  // Comments
  if (ch === '/' && stream.match('//')) {
    stream.skipToEnd();
    return 'comment';
  }
  if (ch === '#') {
    stream.skipToEnd();
    return 'comment';
  }

  // Strings (single-line only; unterminated strings stop at EOL)
  if (ch === '"') {
    stream.next(); // consume opening quote
    while (!stream.eol()) {
      const c = stream.next();
      if (c === '\\') { stream.next(); continue; } // skip escaped char
      if (c === '"') break;
    }
    return 'string';
  }

  // Star operator: *, *8, *16t, etc.
  if (ch === '*') {
    stream.next();
    stream.match(/^(2|4|8|16|32)(t)?/);
    return 'operator';
  }

  // 'crash in' special case — must precede generic word read
  if (stream.match(/^crash(?=\s+in\b)/, false)) {
    stream.match('crash');
    stream.eatSpace();
    stream.match('in');
    return 'keyword';
  }

  // 'x' followed by digits → repeat count (xN)
  if (ch === 'x' && stream.match(/^x\d+/, false)) {
    stream.match(/^x\d+/);
    return 'number';
  }

  // Digits
  if (/\d/.test(ch)) {
    // Time signature: digits/digits
    if (stream.match(/^\d+\/\d+/)) return 'number';
    // 32nd modifier
    if (stream.match(/^32nd/)) return 'modifier';
    // Beat label: [1-9][0-9]?(trip|let|and|[e&atl])?
    if (stream.match(BEAT_LABEL_RE)) return 'constant';
    // Plain number
    stream.match(/^\d+/);
    return 'number';
  }

  // Word tokens (including hyphenated: cross-stick, hi-hat-foot)
  if (/\w/.test(ch)) {
    stream.eatWhile(/[\w-]/);
    const word = stream.current();

    // Bare beat label words
    if (BARE_BEAT_WORDS.has(word)) return 'constant';

    if (INSTRUMENTS.has(word)) return 'typeName';
    if (MODIFIERS.has(word)) return 'modifier';
    if (DEFINITIONS.has(word)) return 'def';
    if (META_KWS.has(word)) return 'keyword';
    if (BODY_KWS.has(word)) return 'keyword';
    if (PLACEMENT_KWS.has(word)) return 'keyword';
    if (ACTION_KWS.has(word)) return 'keyword';

    return null;
  }

  // No match — advance one char
  stream.next();
  return null;
}

// ── StreamLanguage export ──────────────────────────────────────────────────────

export const grooveScriptLanguage = StreamLanguage.define({
  startState: () => null,
  token,
  tokenTable: {
    def: tags.definitionKeyword,
  },
});

// ── Highlight styles ──────────────────────────────────────────────────────────

export const gsHighlightStyleLight = HighlightStyle.define([
  { tag: tags.comment,            color: '#7c8c9a' },
  { tag: tags.string,             color: '#2e7d32' },
  { tag: tags.number,             color: '#e65100' },
  { tag: tags.definitionKeyword,  color: '#6a1b9a', fontWeight: 'bold' },
  { tag: tags.keyword,            color: '#1565c0' },
  { tag: tags.typeName,           color: '#ad1457' },
  { tag: tags.modifier,           color: '#00695c' },
  { tag: tags.constant,           color: '#c62828' },
  { tag: tags.operator,           color: '#f57f17' },
]);

export const gsHighlightStyleDark = HighlightStyle.define([
  { tag: tags.comment,            color: '#637381' },
  { tag: tags.string,             color: '#98c379' },
  { tag: tags.number,             color: '#d19a66' },
  { tag: tags.definitionKeyword,  color: '#c678dd', fontWeight: 'bold' },
  { tag: tags.keyword,            color: '#61afef' },
  { tag: tags.typeName,           color: '#e06c75' },
  { tag: tags.modifier,           color: '#56b6c2' },
  { tag: tags.constant,           color: '#e5c07b' },
  { tag: tags.operator,           color: '#56b6c2' },
]);

export function gsHighlightLight() {
  return syntaxHighlighting(gsHighlightStyleLight);
}

export function gsHighlightDark() {
  return syntaxHighlighting(gsHighlightStyleDark);
}
