// Plays groovescript MIDI bytes through the synthesized drum kit, using a
// look-ahead scheduler so long charts never create thousands of audio nodes
// up front. Exposes the playback position in quarter notes so the score
// view can follow along.

import { parseMidi, makeSecondsToQuarters, makeTickToSeconds } from './midi-parse.js';
import { createDrumKit } from './drumkit.js';

const LOOKAHEAD = 0.15; // seconds of audio scheduled ahead of the clock
const TICK_MS = 25;
const LEAD_IN = 0.08; // small gap so the first hit is not clipped

// midi.py holds these pitches until the next strike (or a choke); every other
// note-off is just the fixed short gate, so only these honour note-off.
const RINGING = new Set([46, 49, 51, 52, 55, 57]);

export class Player {
  constructor() {
    this.ctx = null;
    this.song = null;
    this.timer = null;
    this.startAt = 0;
    this.offset = 0; // seconds into the song where playback started
    this.next = 0; // index of the next note to schedule
    this.chokes = []; // { time, voice }
    this.onEnd = null;
  }

  /** @param {Uint8Array} midiBytes */
  load(midiBytes) {
    const wasPlaying = this.playing;
    const pos = wasPlaying ? this.position : 0;
    if (wasPlaying) this.stop({ silent: true });
    const parsed = parseMidi(midiBytes);
    this.song = {
      ...parsed,
      toQuarters: makeSecondsToQuarters(parsed.division, parsed.tempos),
      toSeconds: makeTickToSeconds(parsed.division, parsed.tempos),
    };
    if (wasPlaying && pos < parsed.duration) this.play(pos);
  }

  get loaded() { return !!this.song; }
  get playing() { return this.timer !== null; }
  get duration() { return this.song ? this.song.duration : 0; }

  /** Current playback position in seconds. */
  get position() {
    if (!this.playing) return this.offset;
    return Math.max(0, this.ctx.currentTime - this.startAt) + this.offset;
  }

  /** Current playback position in quarter notes from the start. */
  get quarters() {
    return this.song ? this.song.toQuarters(this.position) : 0;
  }

  /** Song time in seconds at a position given in quarter notes. */
  secondsAtQuarter(q) {
    return this.song ? this.song.toSeconds(q * this.song.division) : 0;
  }

  async play(from = 0) {
    if (!this.song) return;
    if (!this.ctx) {
      // Must be created from a user gesture on iOS / Safari.
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this.ctx.state !== 'running') await this.ctx.resume();
    this.stop({ silent: true });

    this.master = this.ctx.createGain();
    this.master.gain.value = 0.8;
    const comp = this.ctx.createDynamicsCompressor();
    this.master.connect(comp).connect(this.ctx.destination);
    this.kit = createDrumKit(this.ctx, this.master);

    this.offset = from;
    this.startAt = this.ctx.currentTime + LEAD_IN;
    const notes = this.song.notes;
    this.next = notes.findIndex((n) => n.time >= from - 1e-6);
    if (this.next < 0) this.next = notes.length;
    this.chokes = [];
    this.timer = setInterval(() => this._tick(), TICK_MS);
    this._tick();
  }

  stop({ silent = false } = {}) {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
      this.offset = 0;
    }
    if (this.master) {
      const m = this.master;
      const t = this.ctx.currentTime;
      m.gain.cancelScheduledValues(t);
      m.gain.setValueAtTime(m.gain.value, t);
      m.gain.linearRampToValueAtTime(0, t + 0.03);
      setTimeout(() => m.disconnect(), 100);
      this.master = null;
    }
    if (!silent && this.onEnd) this.onEnd();
  }

  _tick() {
    const { notes } = this.song;
    const horizon = this.ctx.currentTime + LOOKAHEAD;
    const toCtx = (songTime) => this.startAt + (songTime - this.offset);

    while (this.next < notes.length && toCtx(notes[this.next].time) <= horizon) {
      const n = notes[this.next++];
      const t = Math.max(toCtx(n.time), this.ctx.currentTime);
      const voice = this.kit.play(n.note, n.velocity, t);
      if (n.offTime !== null && RINGING.has(n.note)) this.chokes.push({ time: toCtx(n.offTime), voice });
    }

    const keep = [];
    for (const c of this.chokes) {
      if (c.time <= horizon) c.voice.choke(Math.max(c.time, this.ctx.currentTime));
      else keep.push(c);
    }
    this.chokes = keep;

    // Let the last hits ring briefly before reporting the end.
    if (this.next >= notes.length && this.ctx.currentTime > toCtx(this.song.duration) + 0.3) {
      this.stop();
    }
  }
}
