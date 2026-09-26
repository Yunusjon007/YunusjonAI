// Single source of truth for timing. index.html reads it for motion;
// scripts/make-audio.mjs reads the same file to synthesize every sound on its frame.
(function (root) {
  const BEAT = 0.5; // 120 BPM
  const REEL = {
    BPM: 120,
    BEAT,
    DUR: 15,
    FPS: 30,
    scenes: {
      s1: [0, 2.0],
      s2: [2.0, 5.0],
      s3: [5.0, 8.0],
      s4: [8.0, 11.0],
      s5: [11.0, 12.8],
      s6: [12.8, 15.0],
    },
    // Scene 1 — the drop
    s1: { fall: 0.0, impact: 0.38, bounce: 0.62, stretch: 0.72, flood: 1.0, letters: 1.04, stamp: 1.45, glitch: 1.6 },
    // Scene 2 — one word per hit
    s2: { words: [2.0, 2.5, 2.75, 3.0, 3.5], stack: 4.0, underline: 4.35, blinds: 4.72 },
    // Scene 3 — morphs on the beat
    s3: { grid: 5.05, pop: 5.25, morphs: [5.75, 6.25, 6.75, 7.25], flood: 7.5, iris: 7.82 },
    // Scene 4 — orbiting type
    s4: { rings: 8.0, push: 8.5, whip: 10.72 },
    // Scene 5 — ease race
    s5: { lanes: 11.0, race: 11.35, raceDur: 1.0, cut: 12.72 },
    // Scene 6 — lockup
    s6: { line1: 12.8, line2: 13.1, line3: 13.4, dot: 13.88, land: 14.15 },
  };

  // Sound cue sheet: [time, voice, gain, extra]
  const s = REEL;
  const cues = [
    [s.s1.fall, "whooshDown", 0.55],
    [s.s1.impact, "thump", 1.0],
    [s.s1.bounce, "tick", 0.5, { freq: 2400 }],
    [s.s1.stretch, "zip", 0.55],
    [s.s1.flood, "boom", 1.0],
    [s.s1.stamp, "stamp", 0.9],
    [s.s1.glitch, "glitch", 0.55, { dur: 0.22 }],

    [s.s2.words[0], "slam", 0.9],
    [s.s2.words[1], "whip", 0.5, { dur: 0.14 }],
    [s.s2.words[2], "slam", 0.7],
    [s.s2.words[3], "decode", 0.45, { dur: 0.4 }],
    [s.s2.words[4], "slam", 0.9],
    [s.s2.stack, "rattle", 0.45, { n: 5, gap: 0.06 }],
    [s.s2.underline, "zip", 0.35],
    [s.s2.blinds, "whoosh", 0.6, { dur: 0.45 }],

    [s.s3.grid, "shimmer", 0.45],
    [s.s3.pop, "blip", 0.6, { freq: 440 }],
    [s.s3.morphs[0], "blip", 0.6, { freq: 554 }],
    [s.s3.morphs[1], "blip", 0.6, { freq: 659 }],
    [s.s3.morphs[2], "blip", 0.6, { freq: 830 }],
    [s.s3.morphs[3], "blip", 0.6, { freq: 880 }],
    [s.s3.morphs[0] + 0.02, "shimmer", 0.25],
    [s.s3.morphs[1] + 0.02, "shimmer", 0.25],
    [s.s3.morphs[2] + 0.02, "shimmer", 0.25],
    [s.s3.morphs[3], "riser", 0.55, { dur: 0.75 }],
    [8.0, "boom", 0.9],

    [s.s4.rings, "whoosh", 0.45, { dur: 0.6 }],
    [s.s4.push, "swell", 0.35, { dur: 2.0 }],
    [s.s4.whip, "whip", 0.75, { dur: 0.2 }],

    [s.s5.lanes, "rattle", 0.4, { n: 5, gap: 0.05 }],
    [s.s5.race, "zip", 0.3],
    [s.s5.race + s.s5.raceDur, "ping", 0.55],
    [s.s5.cut, "glitch", 0.5, { dur: 0.12 }],

    [s.s6.line1, "slam", 0.9],
    [s.s6.line2, "slam", 0.8],
    [s.s6.line3, "type", 0.45, { n: 13, gap: 0.035 }],
    [s.s6.dot, "whooshDown", 0.45],
    [s.s6.land, "boom", 0.85],
    [s.s6.land, "chime", 0.5],
  ];

  // Music bed, also on the grid: kicks, hats, bass.
  const bed = [];
  const kickRange = (a, b, step) => {
    for (let t = a; t < b - 1e-6; t += step) bed.push([t, "kick", 0.55]);
  };
  const hatRange = (a, b, step, g) => {
    for (let t = a; t < b - 1e-6; t += step) bed.push([t, "hat", g]);
  };
  kickRange(2.0, 7.25, BEAT);
  hatRange(2.25, 7.25, BEAT, 0.22);
  kickRange(8.0, 10.75, BEAT * 2);
  hatRange(8.25, 10.75, BEAT / 2, 0.14);
  kickRange(11.0, 12.75, BEAT);
  hatRange(11.0, 12.75, BEAT / 4, 0.12);
  // bass line: root notes (Hz), one per beat
  const notes = [55, 55, 65.4, 49, 55, 55, 73.4, 65.4];
  for (let i = 0, t = 2.0; t < 7.25 - 1e-6; t += BEAT, i++) bed.push([t, "bass", 0.32, { freq: notes[i % 8], dur: 0.42 }]);
  for (let i = 0, t = 11.0; t < 12.75 - 1e-6; t += BEAT, i++) bed.push([t, "bass", 0.3, { freq: notes[(i + 4) % 8], dur: 0.42 }]);

  REEL.cues = cues.concat(bed);
  root.REEL = REEL;
})(typeof window !== "undefined" ? window : globalThis);
