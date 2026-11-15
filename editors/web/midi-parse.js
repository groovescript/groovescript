// Minimal Standard MIDI File reader for the editor's playback.
//
// Handles exactly what groovescript's midi.py writes (format 0/1, PPQ
// division, running status, tempo meta events) and ignores everything else.
// Pure functions only: no Web Audio here, so `node --test` can cover it.

/**
 * @typedef {{ tick: number, time: number, note: number, velocity: number,
 *             channel: number, offTime: number | null }} MidiNote
 * @typedef {{ tick: number, usPerQuarter: number }} TempoChange
 * @typedef {{ division: number, notes: MidiNote[], tempos: TempoChange[],
 *             duration: number, totalTicks: number }} ParsedMidi
 */

class Reader {
  constructor(bytes) {
    this.b = bytes;
    this.i = 0;
  }
  u8() {
    if (this.i >= this.b.length) throw new Error('MIDI: unexpected end of data');
    return this.b[this.i++];
  }
  u16() { return (this.u8() << 8) | this.u8(); }
  u32() { return ((this.u8() << 24) >>> 0) + (this.u8() << 16) + (this.u8() << 8) + this.u8(); }
  str(n) {
    let s = '';
    for (let k = 0; k < n; k++) s += String.fromCharCode(this.u8());
    return s;
  }
  vlq() {
    let v = 0;
    for (let k = 0; k < 4; k++) {
      const c = this.u8();
      v = (v << 7) | (c & 0x7f);
      if (!(c & 0x80)) return v;
    }
    throw new Error('MIDI: variable-length quantity too long');
  }
}

/**
 * Parse SMF bytes into absolute-time notes.
 * @param {Uint8Array} bytes
 * @returns {ParsedMidi}
 */
export function parseMidi(bytes) {
  const r = new Reader(bytes);
  if (r.str(4) !== 'MThd') throw new Error('MIDI: missing MThd header');
  const hdrLen = r.u32();
  const hdrEnd = r.i + hdrLen;
  r.u16(); // format
  const ntracks = r.u16();
  const division = r.u16();
  if (division & 0x8000) throw new Error('MIDI: SMPTE time division is not supported');
  r.i = hdrEnd;

  const tempos = [];
  const raw = []; // { tick, on: bool, note, velocity, channel }
  let totalTicks = 0;

  for (let t = 0; t < ntracks; t++) {
    if (r.str(4) !== 'MTrk') throw new Error('MIDI: missing MTrk chunk');
    const len = r.u32();
    const end = r.i + len;
    let tick = 0;
    let status = 0;
    while (r.i < end) {
      tick += r.vlq();
      let b = r.u8();
      if (b === 0xff) {
        const type = r.u8();
        const l = r.vlq();
        if (type === 0x51 && l === 3) {
          tempos.push({ tick, usPerQuarter: (r.u8() << 16) | (r.u8() << 8) | r.u8() });
        } else {
          r.i += l;
        }
        continue;
      }
      if (b === 0xf0 || b === 0xf7) {
        r.i += r.vlq();
        continue;
      }
      let d1;
      if (b & 0x80) {
        status = b;
        d1 = r.u8();
      } else {
        if (!status) throw new Error('MIDI: running status without a status byte');
        d1 = b;
      }
      const kind = status & 0xf0;
      const channel = status & 0x0f;
      if (kind === 0xc0 || kind === 0xd0) continue; // one data byte
      const d2 = r.u8();
      if (kind === 0x90 && d2 > 0) raw.push({ tick, on: true, note: d1, velocity: d2, channel });
      else if (kind === 0x80 || kind === 0x90) raw.push({ tick, on: false, note: d1, velocity: 0, channel });
    }
    r.i = end;
    totalTicks = Math.max(totalTicks, tick);
  }

  tempos.sort((a, b) => a.tick - b.tick);
  const toSeconds = makeTickToSeconds(division, tempos);

  // Stable sort keeps note-off before note-on at equal ticks when the file
  // wrote them that way (midi.py does), so re-strikes pair correctly.
  raw.sort((a, b) => a.tick - b.tick);
  const notes = [];
  const open = new Map(); // `${channel}:${note}` -> MidiNote
  for (const ev of raw) {
    const key = `${ev.channel}:${ev.note}`;
    if (ev.on) {
      const n = { tick: ev.tick, time: toSeconds(ev.tick), note: ev.note,
                  velocity: ev.velocity, channel: ev.channel, offTime: null };
      notes.push(n);
      open.set(key, n);
    } else {
      const n = open.get(key);
      if (n) {
        n.offTime = toSeconds(ev.tick);
        open.delete(key);
      }
    }
  }

  return { division, notes, tempos, totalTicks, duration: toSeconds(totalTicks) };
}

/**
 * Build a tick -> seconds converter honouring a sorted tempo map.
 * @param {number} division ticks per quarter note
 * @param {TempoChange[]} tempos
 */
export function makeTickToSeconds(division, tempos) {
  const segs = [];
  let secs = 0;
  let lastTick = 0;
  let us = 500000; // 120 BPM until the first tempo event
  for (const t of tempos) {
    secs += ((t.tick - lastTick) * us) / division / 1e6;
    lastTick = t.tick;
    us = t.usPerQuarter;
    segs.push({ tick: t.tick, secs, us });
  }
  return (tick) => {
    let base = { tick: 0, secs: 0, us: 500000 };
    for (const s of segs) {
      if (s.tick <= tick) base = s;
      else break;
    }
    return base.secs + ((tick - base.tick) * base.us) / division / 1e6;
  };
}

/**
 * Inverse of makeTickToSeconds, returning a position in quarter notes.
 * Used to follow playback in the rendered score.
 * @param {number} division
 * @param {TempoChange[]} tempos
 */
export function makeSecondsToQuarters(division, tempos) {
  const toSecs = makeTickToSeconds(division, tempos);
  const segs = [{ tick: 0, secs: 0, us: 500000 }];
  for (const t of tempos) {
    const s = { tick: t.tick, secs: toSecs(t.tick), us: t.usPerQuarter };
    if (t.tick === 0) segs[0] = s;
    else segs.push(s);
  }
  return (secs) => {
    let base = segs[0];
    for (const s of segs) {
      if (s.secs <= secs) base = s;
      else break;
    }
    const ticks = base.tick + ((secs - base.secs) * 1e6 * division) / base.us;
    return ticks / division;
  };
}
