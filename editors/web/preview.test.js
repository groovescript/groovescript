import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { parseMidi, makeTickToSeconds, makeSecondsToQuarters } from './midi-parse.js';
import { toEditorDiagnostics, summarize } from './diagnostics.js';
import { PYODIDE_VERSION, VEROVIO_VERSION, depUrls } from './deps.js';

// ── Helpers ─────────────────────────────────────────────────────────────────

const vlq = (n) => {
  const out = [n & 0x7f];
  while ((n >>= 7)) out.unshift((n & 0x7f) | 0x80);
  return out;
};
const u32 = (n) => [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
const chunk = (id, body) => [...id].map((c) => c.charCodeAt(0)).concat(u32(body.length), body);
const tempo = (bpm) => {
  const us = Math.round(60e6 / bpm);
  return [0xff, 0x51, 3, (us >> 16) & 255, (us >> 8) & 255, us & 255];
};
const EOT = [0xff, 0x2f, 0];

/** Build a format-1 SMF from per-track [delta, ...eventBytes] lists. */
function smf(division, tracks) {
  const header = chunk('MThd', [0, 1, 0, tracks.length, (division >> 8) & 255, division & 255]);
  const body = tracks.flatMap((evs) => chunk('MTrk', evs.flatMap(([d, ...b]) => [...vlq(d), ...b])));
  return new Uint8Array([...header, ...body]);
}

/** Minimal stand-in for a CodeMirror Text. */
function fakeDoc(text) {
  const lines = text.split('\n');
  const starts = [];
  let pos = 0;
  for (const l of lines) { starts.push(pos); pos += l.length + 1; }
  return {
    lines: lines.length,
    line: (n) => ({ from: starts[n - 1], to: starts[n - 1] + lines[n - 1].length }),
  };
}

// ── MIDI parsing ────────────────────────────────────────────────────────────

test('parseMidi reads notes, velocities and tempo across tracks', () => {
  const bytes = smf(480, [
    [[0, ...tempo(120)], [0, ...EOT]],
    [
      [0, 0x99, 36, 100], [30, 0x89, 36, 0],
      [450, 0x99, 38, 110], [30, 0x99, 38, 0], // note-on vel 0 = note-off
      [0, ...EOT],
    ],
  ]);
  const m = parseMidi(bytes);
  assert.equal(m.division, 480);
  assert.deepEqual(m.notes.map((n) => [n.note, n.velocity, n.tick]), [[36, 100, 0], [38, 110, 480]]);
  assert.equal(m.notes[1].time, 0.5);
  assert.ok(Math.abs(m.notes[0].offTime - 30 / 960) < 1e-9);
  assert.equal(m.notes[0].channel, 9);
});

test('parseMidi honours running status', () => {
  const bytes = smf(480, [[
    [0, 0x99, 42, 80], [0, 46, 90], [240, 0x89, 42, 0], [0, 46, 0], [0, ...EOT],
  ]]);
  const m = parseMidi(bytes);
  assert.deepEqual(m.notes.map((n) => n.note), [42, 46]);
  assert.ok(m.notes.every((n) => n.offTime !== null));
});

test('tempo changes shift absolute time and invert cleanly', () => {
  const tempos = [{ tick: 0, usPerQuarter: 500000 }, { tick: 960, usPerQuarter: 1000000 }];
  const toSecs = makeTickToSeconds(480, tempos);
  assert.equal(toSecs(960), 1.0); // two quarters at 120 BPM
  assert.equal(toSecs(1440), 2.0); // then one quarter at 60 BPM
  const toQ = makeSecondsToQuarters(480, tempos);
  for (const q of [0, 1, 2, 2.5, 3, 7]) {
    assert.ok(Math.abs(toQ(toSecs(q * 480)) - q) < 1e-9, `round-trip at q=${q}`);
  }
});

test('parseMidi rejects non-MIDI input', () => {
  assert.throws(() => parseMidi(new Uint8Array([1, 2, 3, 4])), /MThd/);
});

// ── Diagnostics ─────────────────────────────────────────────────────────────

test('diagnostics map 1-indexed line/column/length to offsets', () => {
  const doc = fakeDoc('title: "x"\ngroove "a":\n  snars: 1\n');
  const [d] = toEditorDiagnostics(doc, [{
    severity: 'error', message: "unexpected token 'snars'", hint: "did you mean 'snare'?",
    line: 3, column: 3, length: 5,
  }]);
  const text = 'title: "x"\ngroove "a":\n  snars: 1\n';
  assert.equal(text.slice(d.from, d.to), 'snars');
  assert.equal(d.severity, 'error');
  assert.match(d.message, /hint: did you mean 'snare'\?/);
});

test('diagnostics without a location or past the end stay in range', () => {
  const doc = fakeDoc('a\nbc');
  const [noLoc, noCol, pastEnd, badLine] = toEditorDiagnostics(doc, [
    { severity: 'warning', message: 'unused groove' },
    { severity: 'info', message: 'x', line: 2, column: null },
    { severity: 'error', message: 'y', line: 2, column: 40, length: 3 },
    { severity: 'bogus', message: 'z', line: 99, column: 1 },
  ]);
  assert.deepEqual([noLoc.from, noLoc.to], [0, 0]);
  assert.deepEqual([noCol.from, noCol.to], [2, 4]);
  assert.deepEqual([pastEnd.from, pastEnd.to], [3, 4]);
  assert.equal(badLine.severity, 'error');
  assert.ok(badLine.from >= 2 && badLine.to <= 4);
});

test('summarize reports the most severe problem first', () => {
  assert.equal(summarize([]).level, 'ok');
  const s = summarize([
    { severity: 'info', message: 'style', line: 1 },
    { severity: 'error', message: 'bad', hint: 'fix it', line: 4 },
    { severity: 'error', message: 'worse', line: 9 },
  ]);
  assert.equal(s.level, 'error');
  assert.equal(s.text, 'line 4: bad — fix it (+1 more)');
});

// ── Dependency pinning ──────────────────────────────────────────────────────

test('runtime versions match package.json and the lockfile', () => {
  const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url)));
  const lock = JSON.parse(readFileSync(new URL('./package-lock.json', import.meta.url)));
  assert.equal(pkg.devDependencies.pyodide, PYODIDE_VERSION);
  assert.equal(pkg.devDependencies.verovio, VEROVIO_VERSION);
  assert.equal(lock.packages['node_modules/pyodide'].version, PYODIDE_VERSION);
  assert.equal(lock.packages['node_modules/verovio'].version, VEROVIO_VERSION);
});

test('depUrls points at pinned CDN builds, or node_modules with local', () => {
  const cdn = depUrls();
  assert.equal(cdn.pyodide, `https://cdn.jsdelivr.net/npm/pyodide@${PYODIDE_VERSION}/`);
  assert.equal(cdn.verovio, `https://cdn.jsdelivr.net/npm/verovio@${VEROVIO_VERSION}/dist/`);
  const local = depUrls({ local: true, baseUrl: 'https://example.test/editor/deps.js' });
  assert.equal(local.pyodide, 'https://example.test/editor/node_modules/pyodide/');
  assert.equal(local.verovio, 'https://example.test/editor/node_modules/verovio/dist/');
});
