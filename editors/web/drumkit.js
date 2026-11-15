// A small synthesized drum kit for previewing charts in the browser.
//
// Every voice is built from oscillators and a shared noise buffer, so there
// are no samples to download. Notes are the General MIDI drum numbers that
// groovescript's midi.py emits. Voices return a `choke(time)` so a MIDI
// note-off can cut ringing cymbals (choke modifier, open hat closing).

const TOM_PITCH = { 41: 90, 45: 125, 50: 165 }; // floor, mid, high

export function createDrumKit(ctx, destination) {
  const noise = makeNoiseBuffer(ctx);

  function env(gainNode, t, peak, attack, decay) {
    const g = gainNode.gain;
    g.setValueAtTime(0.0001, t);
    g.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + attack);
    g.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  }

  function noiseSource(t, dur) {
    const src = ctx.createBufferSource();
    src.buffer = noise;
    src.loop = true;
    src.start(t);
    src.stop(t + dur + 0.05);
    return src;
  }

  function out(node, level) {
    const g = ctx.createGain();
    g.gain.value = level;
    node.connect(g).connect(destination);
    return g;
  }

  function chokeable(gainNode, stopAt) {
    return {
      choke(t) {
        if (t >= stopAt) return;
        const g = gainNode.gain;
        g.cancelScheduledValues(t);
        g.setValueAtTime(g.value || 0.3, t);
        g.exponentialRampToValueAtTime(0.0001, t + 0.04);
      },
    };
  }

  const NONE = { choke() {} };

  function kick(t, v) {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.setValueAtTime(150, t);
    o.frequency.exponentialRampToValueAtTime(45, t + 0.12);
    env(g, t, v, 0.002, 0.35);
    o.connect(g);
    out(g, 1.0);
    o.start(t);
    o.stop(t + 0.45);
    // beater click
    const c = noiseSource(t, 0.02);
    const cg = ctx.createGain();
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 2500;
    env(cg, t, v * 0.25, 0.001, 0.015);
    c.connect(hp).connect(cg);
    out(cg, 1.0);
    return NONE;
  }

  function snare(t, v) {
    const o = ctx.createOscillator();
    o.type = 'triangle';
    const og = ctx.createGain();
    o.frequency.setValueAtTime(240, t);
    o.frequency.exponentialRampToValueAtTime(160, t + 0.08);
    env(og, t, v * 0.6, 0.001, 0.1);
    o.connect(og);
    out(og, 1.0);
    o.start(t);
    o.stop(t + 0.2);
    const n = noiseSource(t, 0.25);
    const bp = ctx.createBiquadFilter();
    bp.type = 'highpass';
    bp.frequency.value = 1500;
    const ng = ctx.createGain();
    env(ng, t, v * 0.7, 0.001, 0.18);
    n.connect(bp).connect(ng);
    out(ng, 1.0);
    return NONE;
  }

  function sideStick(t, v) {
    const o = ctx.createOscillator();
    o.type = 'square';
    o.frequency.value = 1700;
    const g = ctx.createGain();
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 1800;
    bp.Q.value = 3;
    env(g, t, v * 0.6, 0.001, 0.04);
    o.connect(bp).connect(g);
    out(g, 1.0);
    o.start(t);
    o.stop(t + 0.08);
    return NONE;
  }

  function tom(t, v, pitch) {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.setValueAtTime(pitch * 1.6, t);
    o.frequency.exponentialRampToValueAtTime(pitch, t + 0.08);
    env(g, t, v * 0.9, 0.002, 0.4);
    o.connect(g);
    out(g, 1.0);
    o.start(t);
    o.stop(t + 0.5);
    return NONE;
  }

  // Metallic voices: filtered noise plus a cluster of square partials.
  function metal(t, v, { hp = 7000, decay = 0.08, partials = null, level = 0.5, ring = 0 }) {
    const total = decay + ring;
    const g = ctx.createGain();
    env(g, t, v * level, 0.001, total);
    const filt = ctx.createBiquadFilter();
    filt.type = 'highpass';
    filt.frequency.value = hp;
    filt.connect(g);
    out(g, 1.0);
    const n = noiseSource(t, total);
    n.connect(filt);
    if (partials) {
      for (const f of partials) {
        const o = ctx.createOscillator();
        o.type = 'square';
        o.frequency.value = f;
        const pg = ctx.createGain();
        pg.gain.value = 0.12;
        o.connect(pg).connect(filt);
        o.start(t);
        o.stop(t + total + 0.05);
      }
    }
    return chokeable(g, t + total);
  }

  const BELL = [587, 845, 1243];
  const CYMBAL = [3200, 4100, 5300, 6700];

  const voices = {
    35: kick, 36: kick,
    37: sideStick,
    38: snare, 40: snare,
    41: (t, v) => tom(t, v, TOM_PITCH[41]),
    45: (t, v) => tom(t, v, TOM_PITCH[45]),
    50: (t, v) => tom(t, v, TOM_PITCH[50]),
    42: (t, v) => metal(t, v, { hp: 7000, decay: 0.05, level: 0.45 }),
    44: (t, v) => metal(t, v, { hp: 6000, decay: 0.04, level: 0.35 }),
    46: (t, v) => metal(t, v, { hp: 6000, decay: 0.12, ring: 0.35, level: 0.4 }),
    49: (t, v) => metal(t, v, { hp: 4000, decay: 0.3, ring: 1.4, level: 0.5, partials: CYMBAL }),
    57: (t, v) => metal(t, v, { hp: 3800, decay: 0.3, ring: 1.3, level: 0.5, partials: CYMBAL }),
    55: (t, v) => metal(t, v, { hp: 5000, decay: 0.15, ring: 0.5, level: 0.45, partials: CYMBAL }),
    52: (t, v) => metal(t, v, { hp: 2500, decay: 0.25, ring: 0.9, level: 0.55, partials: [2100, 2900, 3700] }),
    51: (t, v) => metal(t, v, { hp: 5500, decay: 0.12, ring: 0.5, level: 0.3, partials: [4500, 5900] }),
    53: (t, v) => metal(t, v, { hp: 1500, decay: 0.25, ring: 0.5, level: 0.35, partials: BELL }),
    56: (t, v) => metal(t, v, { hp: 700, decay: 0.12, level: 0.35, partials: [540, 800] }),
    80: (t, v) => metal(t, v, { hp: 3000, decay: 0.07, level: 0.5, partials: [2500, 3400, 4700] }),
  };

  return {
    /** Schedule a hit. Returns `{ choke(time) }`. */
    play(note, velocity, time) {
      const voice = voices[note] || snare;
      const v = Math.pow(Math.min(Math.max(velocity, 1), 127) / 127, 1.3);
      return voice(time, v);
    },
  };
}

function makeNoiseBuffer(ctx) {
  const len = Math.floor(ctx.sampleRate * 1.0);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const data = buf.getChannelData(0);
  let seed = 22222;
  for (let i = 0; i < len; i++) {
    // Deterministic LCG noise: identical playback run to run.
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    data[i] = (seed / 0x3fffffff) - 1;
  }
  return buf;
}
