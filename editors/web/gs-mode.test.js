// Tests for the GrooveScript tokeniser (gs-mode.js token function).
// Run with: node --test gs-mode.test.js
//
// Uses a minimal mock stream that simulates CodeMirror's StringStream API.

import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { token } from './gs-mode.js';

// ── Mock stream ────────────────────────────────────────────────────────────────

class MockStream {
  constructor(text) {
    this._text = text;
    this._pos = 0;
    this._start = 0;
  }

  resetStart() { this._start = this._pos; }

  eatSpace() {
    const start = this._pos;
    while (this._pos < this._text.length && /[ \t]/.test(this._text[this._pos])) {
      this._pos++;
    }
    return this._pos > start;
  }

  eol() { return this._pos >= this._text.length; }

  peek() {
    return this._pos < this._text.length ? this._text[this._pos] : null;
  }

  next() {
    if (this._pos >= this._text.length) return null;
    return this._text[this._pos++];
  }

  match(pattern, consume = true) {
    if (typeof pattern === 'string') {
      if (this._text.slice(this._pos).startsWith(pattern)) {
        if (consume !== false) this._pos += pattern.length;
        return true;
      }
      return false;
    }
    // RegExp — test against substring from current position
    const m = this._text.slice(this._pos).match(pattern);
    if (m && m.index === 0) {
      if (consume !== false) this._pos += m[0].length;
      return m;
    }
    return null;
  }

  skipToEnd() { this._pos = this._text.length; }

  eatWhile(pattern) {
    const start = this._pos;
    while (this._pos < this._text.length) {
      const ch = this._text[this._pos];
      const ok = (pattern instanceof RegExp) ? pattern.test(ch) : false;
      if (!ok) break;
      this._pos++;
    }
    return this._pos > start;
  }

  current() { return this._text.slice(this._start, this._pos); }
}

// ── Tokenise a full line into [{type, text}] pairs ────────────────────────────

function tokenizeLine(line) {
  const stream = new MockStream(line);
  const tokens = [];
  while (!stream.eol()) {
    const beforePos = stream._pos;
    stream.resetStart();
    const type = token(stream, null);
    const text = stream.current().replace(/^\s+/, ''); // strip leading whitespace
    if (text.length > 0) {
      tokens.push({ type: type ?? null, text });
    }
    // Guard against infinite loop
    if (stream._pos === beforePos) { stream.next(); }
  }
  return tokens;
}

// ── Tests ──────────────────────────────────────────────────────────────────────

test('line comment //', () => {
  const toks = tokenizeLine('// this is a comment');
  assert.equal(toks[0].type, 'comment');
  assert.equal(toks[0].text, '// this is a comment');
});

test('line comment #', () => {
  const toks = tokenizeLine('# hash comment');
  assert.equal(toks[0].type, 'comment');
});

test('string token', () => {
  const toks = tokenizeLine('"money beat"');
  assert.equal(toks[0].type, 'string');
  assert.equal(toks[0].text, '"money beat"');
});

test('unterminated string stops at EOL', () => {
  const toks = tokenizeLine('"unterminated');
  assert.equal(toks[0].type, 'string');
  assert.equal(toks[0].text, '"unterminated');
});

test('time signature', () => {
  const toks = tokenizeLine('4/4');
  assert.equal(toks[0].type, 'number');
  assert.equal(toks[0].text, '4/4');
});

test('time signature 12/8', () => {
  const toks = tokenizeLine('12/8');
  assert.equal(toks[0].type, 'number');
  assert.equal(toks[0].text, '12/8');
});

test('plain number', () => {
  const toks = tokenizeLine('120');
  assert.equal(toks[0].type, 'number');
  assert.equal(toks[0].text, '120');
});

test('repeat count xN', () => {
  const toks = tokenizeLine('x4');
  assert.equal(toks[0].type, 'number');
  assert.equal(toks[0].text, 'x4');
});

test('repeat count x16', () => {
  const toks = tokenizeLine('x16');
  assert.equal(toks[0].type, 'number');
  assert.equal(toks[0].text, 'x16');
});

test('star operator bare', () => {
  const toks = tokenizeLine('*');
  assert.equal(toks[0].type, 'operator');
});

test('star operator *8', () => {
  const toks = tokenizeLine('*8');
  assert.equal(toks[0].type, 'operator');
  assert.equal(toks[0].text, '*8');
});

test('star operator *16t', () => {
  const toks = tokenizeLine('*16t');
  assert.equal(toks[0].type, 'operator');
  assert.equal(toks[0].text, '*16t');
});

test('definition keyword groove', () => {
  const toks = tokenizeLine('groove');
  assert.equal(toks[0].type, 'def');
});

test('definition keyword fill', () => {
  const toks = tokenizeLine('fill');
  assert.equal(toks[0].type, 'def');
});

test('definition keyword section', () => {
  const toks = tokenizeLine('section');
  assert.equal(toks[0].type, 'def');
});

test('metadata keyword', () => {
  const toks = tokenizeLine('metadata');
  assert.equal(toks[0].type, 'keyword');
});

test('metadata field keywords', () => {
  for (const kw of ['title', 'tempo', 'time_signature', 'dsl_version']) {
    const toks = tokenizeLine(kw);
    assert.equal(toks[0].type, 'keyword', `expected keyword for "${kw}"`);
  }
});

test('body keywords', () => {
  for (const kw of ['bars', 'count', 'notes', 'repeat', 'like', 'with', 'play', 'cue', 'variation', 'extend']) {
    const toks = tokenizeLine(kw);
    assert.equal(toks[0].type, 'keyword', `expected keyword for "${kw}"`);
  }
});

test('placement keywords', () => {
  for (const kw of ['at', 'bar', 'beat', 'placeholder', 'rest', 'from', 'to', 'except']) {
    const toks = tokenizeLine(kw);
    assert.equal(toks[0].type, 'keyword', `expected keyword for "${kw}"`);
  }
});

test('action keywords', () => {
  for (const kw of ['add', 'remove', 'replace', 'modify']) {
    const toks = tokenizeLine(kw);
    assert.equal(toks[0].type, 'keyword', `expected keyword for "${kw}"`);
  }
});

test('instrument abbreviations', () => {
  for (const inst of ['BD', 'SN', 'HH', 'OH', 'RD', 'CR', 'FT', 'HT', 'MT']) {
    const toks = tokenizeLine(inst);
    assert.equal(toks[0].type, 'typeName', `expected typeName for "${inst}"`);
  }
});

test('instrument names', () => {
  for (const inst of ['kick', 'snare', 'hihat', 'ride', 'crash', 'floortom']) {
    const toks = tokenizeLine(inst);
    assert.equal(toks[0].type, 'typeName', `expected typeName for "${inst}"`);
  }
});

test('hyphenated instrument cross-stick', () => {
  const toks = tokenizeLine('cross-stick');
  assert.equal(toks[0].type, 'typeName');
  assert.equal(toks[0].text, 'cross-stick');
});

test('hyphenated instrument hi-hat-foot', () => {
  const toks = tokenizeLine('hi-hat-foot');
  assert.equal(toks[0].type, 'typeName');
});

test('modifier ghost', () => {
  const toks = tokenizeLine('ghost');
  assert.equal(toks[0].type, 'modifier');
});

test('modifiers', () => {
  for (const mod of ['accent', 'flam', 'drag', 'double', 'buzz']) {
    const toks = tokenizeLine(mod);
    assert.equal(toks[0].type, 'modifier', `expected modifier for "${mod}"`);
  }
});

test('32nd modifier', () => {
  const toks = tokenizeLine('32nd');
  assert.equal(toks[0].type, 'modifier');
  assert.equal(toks[0].text, '32nd');
});

test('beat label single digit', () => {
  const toks = tokenizeLine('1');
  assert.equal(toks[0].type, 'constant');
});

test('beat label with &', () => {
  const toks = tokenizeLine('2&');
  assert.equal(toks[0].type, 'constant');
  assert.equal(toks[0].text, '2&');
});

test('beat label with e', () => {
  const toks = tokenizeLine('3e');
  assert.equal(toks[0].type, 'constant');
});

test('beat label with a', () => {
  const toks = tokenizeLine('4a');
  assert.equal(toks[0].type, 'constant');
});

test('beat label with trip suffix', () => {
  const toks = tokenizeLine('1trip');
  assert.equal(toks[0].type, 'constant');
  assert.equal(toks[0].text, '1trip');
});

test('beat label with let suffix', () => {
  const toks = tokenizeLine('2let');
  assert.equal(toks[0].type, 'constant');
});

test('two-digit beat label', () => {
  const toks = tokenizeLine('12');
  assert.equal(toks[0].type, 'constant');
  assert.equal(toks[0].text, '12');
});

test('bare trip word', () => {
  const toks = tokenizeLine('trip');
  assert.equal(toks[0].type, 'constant');
});

test('bare let word', () => {
  const toks = tokenizeLine('let');
  assert.equal(toks[0].type, 'constant');
});

test('bare and word', () => {
  const toks = tokenizeLine('and');
  assert.equal(toks[0].type, 'constant');
});

test('crash in keyword (two words)', () => {
  const toks = tokenizeLine('crash in');
  // Should produce a single keyword token covering both words
  assert.equal(toks.length, 1);
  assert.equal(toks[0].type, 'keyword');
  assert.match(toks[0].text, /crash/);
});

test('crash as instrument (no in)', () => {
  const toks = tokenizeLine('crash');
  assert.equal(toks[0].type, 'typeName');
  assert.equal(toks[0].text, 'crash');
});

test('crash followed by other word is instrument', () => {
  const toks = tokenizeLine('crash into');
  assert.equal(toks[0].type, 'typeName');
  assert.equal(toks[0].text, 'crash');
});

test('full groove line', () => {
  const toks = tokenizeLine('  BD: 1, 3');
  const types = toks.map(t => t.type);
  assert.ok(types.includes('typeName'), 'BD is typeName');
  assert.ok(types.includes('constant'), 'beat positions are constant');
});

test('groove definition line', () => {
  const toks = tokenizeLine('groove "main groove":');
  assert.equal(toks[0].type, 'def');
  assert.equal(toks[0].text, 'groove');
  assert.equal(toks[1].type, 'string');
});

test('section line', () => {
  const toks = tokenizeLine('section "verse":');
  assert.equal(toks[0].type, 'def');
  assert.equal(toks[0].text, 'section');
  assert.equal(toks[1].type, 'string');
});

test('HH *8 line', () => {
  const toks = tokenizeLine('  HH: *8');
  const hh = toks.find(t => t.text === 'HH');
  const star = toks.find(t => t.type === 'operator');
  assert.ok(hh, 'HH found');
  assert.equal(hh.type, 'typeName');
  assert.ok(star, 'operator found');
  assert.equal(star.text, '*8');
});

test('metadata block', () => {
  const toks = tokenizeLine('  tempo: 120');
  const tempo = toks.find(t => t.text === 'tempo');
  const num = toks.find(t => t.type === 'number');
  assert.ok(tempo);
  assert.equal(tempo.type, 'keyword');
  assert.ok(num);
  assert.equal(num.text, '120');
});

test('comment after code', () => {
  const toks = tokenizeLine('BD: 1 // bass drum on 1');
  const comment = toks.find(t => t.type === 'comment');
  assert.ok(comment, 'comment found');
  assert.ok(comment.text.startsWith('//'));
});
