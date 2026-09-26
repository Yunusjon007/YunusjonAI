---
message: "Every frame and every sound of this reel is written in code"
mode: autonomous
canvas: 1080x1920
duration: 15
tempo: 120 BPM (beat = 0.5s) — one grid drives picture AND sound (`beats.js`)
palette: { bg: "#0D0C0B", fg: "#F3EEE7", accent: "#FF4B1F", muted: "#9A918A" }
type: { display: "Archivo Black", condensed: "League Gothic", data: "JetBrains Mono" }
---

Concept: a reel whose own tooling is the flex — timecode HUD, eases racing, a
dot that opens the film and returns as the final full stop. Monolithic
`index.html` (one paused timeline) so cross-scene transitions can straddle cuts.

Persistent chrome 0–15s: SMPTE timecode, REEL/26 tag, scene index, progress bar,
crop marks, film grain (`grain-overlay` registry component).

## Frame 1 — The Drop (0.0–2.0s)
status: outline · src: index.html#s1 · rules: spring-pop-entrance, waterfall-entry, chromatic-glitch (slice form)
An accent dot DROPS, squashes on impact, STRETCHES into a line that FLOODS the
frame orange. "SHOW / REEL" in 560px League Gothic RISES letter by letter out of
masks; "’26" STAMPS. Slice-glitch on 1.5s. SFX: whoosh-down, thump, zip, boom, glitch.

## Frame 2 — Native Language (2.0–5.0s)
status: outline · src: index.html#s2 · blueprint: kinetic-type-beats · rules: kinetic-beat-slam, hacker-flip-3d, waterfall-entry
Hard cut. MOTION / IS / MY / NATIVE / LANGUAGE hit one per beat, each a distinct
entrance (scale-blur slam, side snap, rise-rotate, 3D decode flip, stretch).
4.0s: the full sentence WATERFALLS into a stack, MOTION in accent, underline sweep.
Metronome ticks on the grid. Exit: staggered accent blinds (css-cover). SFX: kick
per word, decode chatter, whoosh on blinds.

## Frame 3 — Form (5.0–8.0s)
status: outline · rules: center-outward-expansion, sine-wave-loop, scale-swap-transition
A 6×10 tile grid RIPPLES from center; a hero shape MORPHS circle → triangle →
square → star (64-point clip-path polygons) on beats, each morph sending a ripple
through the grid. Shape then EXPANDS to flood the frame; circle iris opens to Frame 4.
SFX: pitched blips per morph, shimmer ripples, riser into boom.

## Frame 4 — Depth (8.0–11.0s)
status: outline · rules: orbit-3d-entry, 3d-camera-flight, depth-of-field-blur
Three cylinders of type (DESIGN · RHYTHM · TIMING · MOTION ·) ORBIT in true CSS
3D, counter-rotating, middle ring in accent; camera pushes in and tilts.
Exit: whip-pan with blur. SFX: airy swells, whip.

## Frame 5 — Timing (11.0–12.8s)
status: outline · rules: svg-path-draw, stat-bars-and-fills (lanes)
The motion designer's graph editor: five ease lanes (linear, power2, expo,
back, elastic) — dots RACE across, each label typed in mono, curve of the
winner DRAWS itself. SFX: ticks per lane, ping at finish.

## Frame 6 — Written In Code (12.8–15.0s)
status: outline · blueprint: logo-assemble-lockup · rules: kinetic-beat-slam, spring-pop-entrance
"EVERY FRAME." / "EVERY SOUND." / "WRITTEN IN CODE" — then the opening dot flies
back in and LANDS as the full stop. Hold. SFX: typed clicks, final hit + chime tail.
