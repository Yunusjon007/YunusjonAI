// Synthesizes the whole soundtrack from code — no samples, no downloads.
// Reads the cue sheet in ../beats.js so every sound lands on the frame it belongs to.
// Usage: node scripts/make-audio.mjs  → assets/reel-audio.wav (48 kHz, 16-bit stereo)
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(here, "..");
const ctx = { globalThis: {} };
vm.runInNewContext(fs.readFileSync(path.join(projectDir, "beats.js"), "utf8"), ctx);
const REEL = ctx.globalThis.REEL;

const SR = 48000;
const N = Math.ceil(REEL.DUR * SR);
const L = new Float32Array(N);
const R = new Float32Array(N);
const sendL = new Float32Array(N); // reverb send
const sendR = new Float32Array(N);

// Seeded PRNG — the soundtrack is bit-identical on every run.
let seed = 0x5eed26;
const rand = () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const noise = () => rand() * 2 - 1;
const TAU = Math.PI * 2;

function write(i, v, pan = 0, send = 0) {
  if (i < 0 || i >= N) return;
  const gl = Math.cos((pan + 1) * Math.PI / 4);
  const gr = Math.sin((pan + 1) * Math.PI / 4);
  L[i] += v * gl;
  R[i] += v * gr;
  sendL[i] += v * gl * send;
  sendR[i] += v * gr * send;
}

// State-variable filter (Chamberlin) — used for sweeps.
function svf() {
  let low = 0, band = 0;
  return (x, fc, q = 0.7) => {
    const f = 2 * Math.sin(Math.PI * Math.min(fc, SR / 6) / SR);
    low += f * band;
    const high = x - low - q * band;
    band += f * high;
    return { low, band, high };
  };
}

const env = (t, a, d) => (t < a ? t / a : Math.exp(-(t - a) / d));

const voices = {
  kick(t0, g) {
    const len = 0.45 * SR;
    let ph = 0;
    for (let n = 0; n < len; n++) {
      const t = n / SR;
      const f = 48 + 120 * Math.exp(-t / 0.035);
      ph += TAU * f / SR;
      const click = n < 90 ? noise() * (1 - n / 90) * 0.35 : 0;
      write(Math.round(t0 * SR) + n, g * (Math.tanh(1.6 * Math.sin(ph)) * env(t, 0.002, 0.16) + click));
    }
  },
  thump(t0, g) {
    let ph = 0;
    for (let n = 0; n < 0.6 * SR; n++) {
      const t = n / SR;
      ph += TAU * (38 + 90 * Math.exp(-t / 0.05)) / SR;
      write(Math.round(t0 * SR) + n, g * Math.tanh(2 * Math.sin(ph)) * env(t, 0.001, 0.2), 0, 0.2);
    }
  },
  hat(t0, g) {
    const hp = svf();
    for (let n = 0; n < 0.08 * SR; n++) {
      const t = n / SR;
      const y = hp(noise(), 9000, 0.5).high;
      write(Math.round(t0 * SR) + n, g * y * env(t, 0.0005, 0.018), 0.35);
    }
  },
  bass(t0, g, { freq, dur }) {
    const lp = svf();
    let ph = 0;
    for (let n = 0; n < dur * SR; n++) {
      const t = n / SR;
      ph = (ph + freq / SR) % 1;
      const saw = 2 * ph - 1;
      const y = lp(saw, 180 + 900 * Math.exp(-t / 0.06), 0.4).low;
      const e = Math.min(1, t / 0.004) * Math.min(1, (dur - t) / 0.03);
      write(Math.round(t0 * SR) + n, g * Math.tanh(1.8 * y) * e);
    }
  },
  whoosh(t0, g, { dur = 0.5 } = {}) {
    const bp = svf();
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      const fc = 300 + 5200 * Math.sin(Math.PI * p) ** 2;
      const y = bp(noise(), fc, 0.25).band;
      write(Math.round(t0 * SR) + n, g * y * Math.sin(Math.PI * p) ** 1.5, -0.7 + 1.4 * p, 0.35);
    }
  },
  whooshDown(t0, g) {
    const bp = svf();
    const dur = 0.4;
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      const y = bp(noise(), 6000 * Math.exp(-3 * p) + 300, 0.3).band;
      write(Math.round(t0 * SR) + n, g * y * p ** 1.2, 0, 0.3);
    }
  },
  whip(t0, g, { dur = 0.18 } = {}) {
    const bp = svf();
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      const y = bp(noise(), 7000 * Math.exp(-2.8 * p) + 350, 0.18).band;
      write(Math.round(t0 * SR) + n, g * 1.4 * y * Math.sin(Math.PI * p), 0.8 - 1.6 * p, 0.25);
    }
  },
  zip(t0, g) {
    let ph = 0;
    const dur = 0.22;
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      ph = (ph + (250 * Math.pow(14, p)) / SR) % 1;
      const sq = ph < 0.5 ? 1 : -1;
      write(Math.round(t0 * SR) + n, g * 0.35 * sq * Math.sin(Math.PI * p), -0.5 + p, 0.3);
    }
  },
  boom(t0, g) {
    const lp = svf();
    let ph = 0;
    for (let n = 0; n < 1.8 * SR; n++) {
      const t = n / SR;
      ph += TAU * (30 + 70 * Math.exp(-t / 0.08)) / SR;
      const sub = Math.tanh(2.2 * Math.sin(ph)) * env(t, 0.002, 0.55);
      const crunch = lp(noise(), 2400 * Math.exp(-t / 0.15) + 120, 0.6).low * env(t, 0.001, 0.12);
      write(Math.round(t0 * SR) + n, g * (sub * 0.9 + crunch * 1.2), 0, 0.45);
    }
  },
  slam(t0, g) {
    voices.kick(t0, g * 0.9);
    const bp = svf();
    for (let n = 0; n < 0.25 * SR; n++) {
      const t = n / SR;
      write(Math.round(t0 * SR) + n, g * 0.9 * bp(noise(), 1800, 0.5).band * env(t, 0.001, 0.05), 0, 0.4);
    }
  },
  stamp(t0, g) {
    voices.thump(t0, g * 0.7);
    for (let n = 0; n < 0.12 * SR; n++) {
      const t = n / SR;
      write(Math.round(t0 * SR) + n, g * 0.5 * noise() * env(t, 0.0005, 0.02), 0.2, 0.5);
    }
  },
  tick(t0, g, { freq = 3000 } = {}) {
    const bp = svf();
    for (let n = 0; n < 0.03 * SR; n++) {
      const t = n / SR;
      const y = bp(noise(), freq, 0.12).band + 0.3 * Math.sin(TAU * freq * t);
      write(Math.round(t0 * SR) + n, g * y * env(t, 0.0003, 0.006), 0.3 * (rand() - 0.5), 0.2);
    }
  },
  rattle(t0, g, { n = 5, gap = 0.06 }) {
    for (let k = 0; k < n; k++) voices.tick(t0 + k * gap, g * (1 - k * 0.08), { freq: 1800 + k * 450 });
  },
  type(t0, g, { n = 6, gap = 0.05 }) {
    for (let k = 0; k < n; k++) {
      voices.tick(t0 + k * gap + (rand() - 0.5) * 0.008, g, { freq: 2200 + rand() * 1600 });
      voices.tick(t0 + k * gap + 0.004, g * 0.5, { freq: 600 });
    }
  },
  decode(t0, g, { dur = 0.4 }) {
    const steps = Math.floor(dur / 0.025);
    for (let k = 0; k < steps; k++) {
      const f = 900 + Math.floor(rand() * 8) * 260;
      const s0 = Math.round((t0 + k * 0.025) * SR);
      for (let n = 0; n < 0.02 * SR; n++) {
        const t = n / SR;
        const sq = Math.sin(TAU * f * t) > 0 ? 1 : -1;
        write(s0 + n, g * 0.35 * sq * env(t, 0.0005, 0.006), (rand() - 0.5) * 0.8, 0.15);
      }
    }
  },
  glitch(t0, g, { dur = 0.2 }) {
    let held = 0, f = 400, ph = 0;
    for (let n = 0; n < dur * SR; n++) {
      if (n % 480 === 0) {
        f = 120 + rand() * 2400;
        held = rand() > 0.35 ? 1 : 0;
      }
      ph = (ph + f / SR) % 1;
      const crushed = Math.round((ph < 0.5 ? 1 : -1) * 0.8 * 4) / 4 + Math.round(noise() * 3) / 6;
      write(Math.round(t0 * SR) + n, g * 0.45 * crushed * held, (rand() - 0.5), 0.1);
    }
  },
  blip(t0, g, { freq }) {
    let ph = 0, mph = 0;
    for (let n = 0; n < 0.4 * SR; n++) {
      const t = n / SR;
      mph += TAU * freq * 2 / SR;
      ph += TAU * freq * (1 + 0.02 * Math.exp(-t / 0.02)) / SR + 1.2 * Math.exp(-t / 0.04) * Math.sin(mph) / 40;
      write(Math.round(t0 * SR) + n, g * 0.55 * Math.sin(ph) * env(t, 0.002, 0.09), (freq % 3) * 0.2 - 0.2, 0.5);
    }
  },
  shimmer(t0, g) {
    const parts = [2093, 3136, 4186, 5274];
    for (let n = 0; n < 0.7 * SR; n++) {
      const t = n / SR;
      let y = 0;
      parts.forEach((f, i) => (y += Math.sin(TAU * f * t + i) * (1 + Math.sin(TAU * (9 + i * 3) * t)) * 0.5));
      write(Math.round(t0 * SR) + n, g * 0.12 * y * env(t, 0.03, 0.18), Math.sin(TAU * 3 * t) * 0.6, 0.7);
    }
  },
  riser(t0, g, { dur = 0.75 }) {
    const bp = svf();
    let ph = 0;
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      ph = (ph + (90 * Math.pow(9, p)) / SR) % 1;
      const y = bp(noise(), 250 * Math.pow(32, p), 0.3).band * 0.9 + (2 * ph - 1) * 0.18;
      write(Math.round(t0 * SR) + n, g * y * p ** 2, 0, 0.4);
    }
  },
  swell(t0, g, { dur = 2 }) {
    const bp = svf();
    for (let n = 0; n < dur * SR; n++) {
      const p = n / (dur * SR);
      const t = n / SR;
      const y = bp(noise(), 700 + 500 * Math.sin(TAU * 0.8 * t), 0.2).band;
      const pad = (Math.sin(TAU * 110 * t) + 0.5 * Math.sin(TAU * 164.8 * t) + 0.35 * Math.sin(TAU * 220.5 * t)) * 0.12;
      write(Math.round(t0 * SR) + n, g * (y * 0.6 + pad) * Math.sin(Math.PI * p), Math.sin(TAU * 0.5 * t) * 0.7, 0.6);
    }
  },
  ping(t0, g) {
    for (let n = 0; n < 0.9 * SR; n++) {
      const t = n / SR;
      const y = Math.sin(TAU * 1760 * t) + 0.4 * Math.sin(TAU * 2637 * t);
      write(Math.round(t0 * SR) + n, g * 0.35 * y * env(t, 0.001, 0.14), 0.2, 0.6);
    }
  },
  chime(t0, g) {
    // FM bell: A5 with an inharmonic modulator; index decays like struck metal.
    const fc = 880, fm = fc * 3.5;
    for (let n = 0; n < 2.4 * SR; n++) {
      const t = n / SR;
      const idx = 4 * Math.exp(-t / 0.35);
      const y = Math.sin(TAU * fc * t + idx * Math.sin(TAU * fm * t)) + 0.4 * Math.sin(TAU * fc * 2.01 * t);
      write(Math.round(t0 * SR) + n, g * 0.3 * y * env(t, 0.002, 0.7), 0, 0.7);
    }
  },
};

for (const [t, voice, gain, extra] of REEL.cues) {
  if (!voices[voice]) throw new Error(`unknown voice ${voice}`);
  voices[voice](t, gain, extra || {});
}

// Schroeder reverb on the send bus.
function reverb(input, offset) {
  const out = new Float32Array(N);
  const combs = [1557, 1617, 1491, 1422].map((d) => ({ buf: new Float32Array(d + offset), i: 0, lp: 0 }));
  const aps = [225, 556].map((d) => ({ buf: new Float32Array(d + offset), i: 0 }));
  for (let n = 0; n < N; n++) {
    let acc = 0;
    for (const c of combs) {
      const y = c.buf[c.i];
      c.lp = y * 0.75 + c.lp * 0.25;
      c.buf[c.i] = input[n] + c.lp * 0.8;
      c.i = (c.i + 1) % c.buf.length;
      acc += y;
    }
    for (const a of aps) {
      const b = a.buf[a.i];
      const y = -acc + b;
      a.buf[a.i] = acc + b * 0.5;
      a.i = (a.i + 1) % a.buf.length;
      acc = y;
    }
    out[n] = acc * 0.25;
  }
  return out;
}
const wetL = reverb(sendL, 0);
const wetR = reverb(sendR, 23);

// Master: mix, gentle glue, soft clip, fade the last 150ms.
const pcm = Buffer.alloc(N * 4);
let peak = 0;
for (let n = 0; n < N; n++) {
  const fade = Math.min(1, (N - n) / (0.15 * SR));
  for (let ch = 0; ch < 2; ch++) {
    const dry = ch ? R[n] : L[n];
    const wet = ch ? wetR[n] : wetL[n];
    const v = Math.tanh(1.1 * (dry + wet * 0.6)) * 0.92 * fade;
    peak = Math.max(peak, Math.abs(v));
    pcm.writeInt16LE(Math.round(Math.max(-1, Math.min(1, v)) * 32767), (n * 2 + ch) * 2);
  }
}
const header = Buffer.alloc(44);
header.write("RIFF", 0);
header.writeUInt32LE(36 + pcm.length, 4);
header.write("WAVE", 8);
header.write("fmt ", 12);
header.writeUInt32LE(16, 16);
header.writeUInt16LE(1, 20);
header.writeUInt16LE(2, 22);
header.writeUInt32LE(SR, 24);
header.writeUInt32LE(SR * 4, 28);
header.writeUInt16LE(4, 32);
header.writeUInt16LE(16, 34);
header.write("data", 36);
header.writeUInt32LE(pcm.length, 40);
fs.mkdirSync(path.join(projectDir, "assets"), { recursive: true });
const out = path.join(projectDir, "assets", "reel-audio.wav");
fs.writeFileSync(out, Buffer.concat([header, pcm]));
console.log(`wrote ${path.relative(projectDir, out)} — ${REEL.cues.length} cues, ${REEL.DUR}s, peak ${peak.toFixed(3)}`);
