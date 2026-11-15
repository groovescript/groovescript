import { test } from 'node:test';
import assert from 'node:assert/strict';

import { analyze, options, hoverInfo, enclosingBlock } from './assist.js';

// Shaped like groovescript.web.vocabulary() / chart_symbols().
const vocab = {
  instruments: [
    { code: 'BD', name: 'bass drum', aliases: ['BD', 'bass', 'kick', 'bd'] },
    { code: 'SN', name: 'snare', aliases: ['SN', 'snare', 'sn'] },
    { code: 'HH', name: 'closed hi-hat', aliases: ['HH', 'hat', 'hihat', 'hh'] },
  ],
  modifiers: [
    { name: 'ghost', doc: 'Ghost note.' },
    { name: 'accent', doc: 'Accent.' },
    { name: 'flam', doc: 'Flam.' },
  ],
  library: {
    grooves: [{ name: 'rock', text: 'groove "rock":\n  HH: *8' }],
    fills: [{ name: 'tom-roll', text: 'fill "tom-roll":\n  ...' }],
    variations: [{ name: 'crash-1', text: 'variation "crash-1":\n  add CR at 1' }],
  },
};

const DOC = `title: "Song"
groove "verse beat":
  BD: 1, 3
  SN: 2, 4
fill "drop":
  SN: 4
section "verse":
  bars: 8
  groove: "verse beat"
section "chorus":
  like "verse"
`;
const symbols = {
  grooves: [{ name: 'verse beat', line: 2, end_line: 4 }],
  fills: [{ name: 'drop', line: 5, end_line: 6 }],
  variations: [],
  sections: [{ name: 'verse', line: 7, end_line: 9 }, { name: 'chorus', line: 10, end_line: 11 }],
};
const env = { symbols, vocab };

/** Insert `text` at the end of DOC and analyze at the end (| marks the cursor). */
function at(snippet) {
  const text = DOC + snippet.replace('|', '');
  return { text, pos: DOC.length + snippet.indexOf('|') };
}

function labels(snippet) {
  const { text, pos } = at(snippet);
  return options(analyze(text, pos), env).map((o) => o.label);
}

test('enclosing block comes from the nearest header above', () => {
  assert.equal(enclosingBlock(DOC, DOC.indexOf('  BD:')), 'groove');
  assert.equal(enclosingBlock(DOC, DOC.indexOf('  bars:')), 'section');
  assert.equal(enclosingBlock(DOC, 0), 'top');
});

test('names inside quotes come from the chart first, then the library', () => {
  assert.deepEqual(labels('  groove: "|'), ['verse beat', 'rock']);
  assert.deepEqual(labels('  like "|'), ['verse', 'chorus']);
  assert.deepEqual(labels('  fill "|'), ['drop', 'tom-roll']);
  assert.deepEqual(labels('  variation "|'), ['crash-1']);
  const { text, pos } = at('  groove: "ve|');
  assert.equal(analyze(text, pos).from, pos - 2); // replaces the typed prefix
});

test('a chart definition hides the library entry of the same name', () => {
  const shadow = { ...symbols, grooves: [...symbols.grooves, { name: 'rock', line: 1, end_line: 1 }] };
  const { text, pos } = at('  groove: "|');
  const opts = options(analyze(text, pos), { symbols: shadow, vocab });
  assert.equal(opts.filter((o) => o.label === 'rock').length, 1);
  assert.equal(opts.find((o) => o.label === 'rock').detail, 'line 1');
});

test('defining a top-level fill name offers nothing', () => {
  const text = 'fill "';
  assert.equal(analyze(text, text.length), null);
});

test('line starts offer keywords for the enclosing block', () => {
  const top = labels('|');
  assert.ok(top.includes('groove') && top.includes('section') && top.includes('tempo'));
  const section = labels('  |');
  assert.ok(section.includes('rit') && section.includes('fill') && section.includes('bars'));
  const groove = labels('groove "x":\n  |');
  assert.ok(groove.includes('BD') && groove.includes('kick') && groove.includes('bar'));
  const { text, pos } = at('groove "x":\n  |');
  const bd = options(analyze(text, pos), env).find((o) => o.label === 'BD');
  assert.equal(bd.apply, 'BD: ');
});

test('pattern values offer modifiers after a beat, nothing while typing a beat', () => {
  assert.deepEqual(labels('groove "x":\n  SN: 2 |'), ['ghost', 'accent', 'flam']);
  assert.deepEqual(labels('groove "x":\n  SN: 2 ghost |'), ['ghost', 'accent', 'flam']);
  const { text, pos } = at('groove "x":\n  SN: 2|');
  assert.equal(analyze(text, pos), null);
  // Settings lines are not pattern lines.
  assert.deepEqual(labels('  bars: 8 |'), []);
});

test('position lines and variation actions offer instruments', () => {
  assert.ok(labels('fill "y":\n  3: |').includes('SN'));
  assert.ok(labels('fill "y":\n  3: |').includes('ghost'));
  assert.deepEqual(labels('  add |').slice(0, 2), ['BD', 'bass']);
  assert.ok(labels('  add CR |').includes('accent'));
  assert.ok(labels('  replace HH with |').includes('SN'));
  assert.deepEqual(labels('  add CR at |'), []);
  assert.deepEqual(labels('  modify add |'), ['ghost', 'accent', 'flam']);
  assert.ok(labels('  modify add accent to |').includes('SN'));
});

test('tuplet braces offer tuplet kinds', () => {
  assert.deepEqual(labels('groove "x":\n  HH: 2{|'), ['triplet', 'quintuplet', 'sextuplet', 'septuplet', 'nonuplet']);
});

test('comments get no completions', () => {
  assert.deepEqual(labels('# groove: "|'), []);
});

test('hover over a chart name shows its definition and line', () => {
  const pos = DOC.indexOf('"verse beat"', DOC.indexOf('section')) + 3;
  const info = hoverInfo(DOC, pos, env);
  assert.equal(info.title, 'groove "verse beat" — line 2');
  assert.equal(info.definitionLine, 2);
  assert.match(info.body, /BD: 1, 3/);
});

test('hover over a library name, an unknown name, an instrument, a modifier', () => {
  const text = 'section "s":\n  groove: "rock"\n  like "nowhere"\n  variation at bar 1:\n    add kick ghost at 1\n  rit from bar 1 to bar 2\n';
  const rock = hoverInfo(text, text.indexOf('rock') + 1, env);
  assert.equal(rock.title, 'built-in groove "rock"');
  const missing = hoverInfo(text, text.indexOf('nowhere') + 1, env);
  assert.equal(missing.title, 'no section named "nowhere"');
  const kick = hoverInfo(text, text.indexOf('kick') + 1, env);
  assert.equal(kick.title, 'BD — bass drum');
  assert.match(kick.body, /BD, bass, bd/);
  const ghost = hoverInfo(text, text.indexOf('ghost') + 1, env);
  assert.equal(ghost.body, 'Ghost note.');
  const rit = hoverInfo(text, text.indexOf('rit') + 1, env);
  assert.match(rit.body, /slow down/);
  assert.equal(hoverInfo(text, text.indexOf('bar 1:') + 1, env), null);
});
