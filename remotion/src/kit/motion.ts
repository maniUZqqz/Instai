// How each InstAI animation style MOVES. The style library names ten approaches (see instai/styles/schema.py ANIMATIONS); each one becomes a small,
// deterministic "motion personality" that every composition uses, so a title in "stop-motion" really steps on fours with a little jitter,
// "rubber hose" bounces, "motion graphics" snaps with a crisp ease-out, and "live camera" pushes in slowly.
import { Easing, interpolate, spring } from 'remotion'

export type Motion = {
  id: string
  /** frames a pose is held: 1 = smooth; 2 = "on twos"; 4 = "on fours" (derived from the style's fps_feel) */
  step: number
  ease: (t: number) => number
  /** spring-like overshoot of entrances (0 = none) */
  overshoot: number
  /** paper / puppet wobble in degrees (0 = none) */
  wobbleDeg: number
  /** hand-made positional jitter in pixels per held pose (0 = none) */
  jitterPx: number
  /** slow camera push-in over the whole clip (0.06 = 6 %) */
  camera: number
  /** 3-D tilt of cards in degrees (0 = flat) */
  tilt3d: number
  /** frames between successive words / items entering */
  stagger: number
  /** frames an entrance takes */
  enterFrames: number
  /** the background drifts slowly (painted layers) */
  drift: boolean
}

type Base = Omit<Motion, 'id' | 'step'> & { stepped: boolean }

const BASE: Record<string, Base> = {
  live_camera: { ease: Easing.bezier(0.25, 0.1, 0.25, 1), overshoot: 0, wobbleDeg: 0, jitterPx: 0, camera: 0.07, tilt3d: 0, stagger: 7, enterFrames: 22, drift: false, stepped: false },
  limited_2d: { ease: Easing.out(Easing.quad), overshoot: 0.05, wobbleDeg: 0, jitterPx: 0, camera: 0, tilt3d: 0, stagger: 6, enterFrames: 14, drift: false, stepped: true },
  full_2d: { ease: Easing.inOut(Easing.cubic), overshoot: 0.08, wobbleDeg: 0, jitterPx: 0, camera: 0.02, tilt3d: 0, stagger: 6, enterFrames: 20, drift: false, stepped: false },
  rubber_hose: { ease: Easing.out(Easing.back(2.2)), overshoot: 0.28, wobbleDeg: 1.2, jitterPx: 0, camera: 0, tilt3d: 0, stagger: 5, enterFrames: 18, drift: false, stepped: false },
  cutout: { ease: Easing.out(Easing.quad), overshoot: 0.04, wobbleDeg: 1.6, jitterPx: 2, camera: 0, tilt3d: 0, stagger: 8, enterFrames: 12, drift: false, stepped: true },
  motion_graphics: { ease: Easing.bezier(0.16, 1, 0.3, 1), overshoot: 0, wobbleDeg: 0, jitterPx: 0, camera: 0, tilt3d: 0, stagger: 4, enterFrames: 16, drift: false, stepped: false },
  stop_motion: { ease: (t: number) => t, overshoot: 0, wobbleDeg: 1.1, jitterPx: 3, camera: 0, tilt3d: 0, stagger: 8, enterFrames: 16, drift: false, stepped: true },
  cg_3d: { ease: Easing.out(Easing.cubic), overshoot: 0.06, wobbleDeg: 0, jitterPx: 0, camera: 0.04, tilt3d: 9, stagger: 6, enterFrames: 22, drift: false, stepped: false },
  toon_3d: { ease: Easing.out(Easing.back(1.4)), overshoot: 0.14, wobbleDeg: 0.6, jitterPx: 0, camera: 0.03, tilt3d: 6, stagger: 6, enterFrames: 18, drift: false, stepped: true },
  painted_parallax: { ease: Easing.inOut(Easing.sin), overshoot: 0, wobbleDeg: 0, jitterPx: 0, camera: 0.05, tilt3d: 0, stagger: 9, enterFrames: 30, drift: true, stepped: false },
}

export const ANIMATION_IDS = Object.keys(BASE)

/** The motion personality of a style: `animation` is the style's key, `fpsFeel` its poses per second, `fps` the video's frame rate. */
export function motionFor(animation: string, fpsFeel: number, fps: number): Motion {
  const b = BASE[animation] ?? BASE.motion_graphics
  const step = b.stepped ? Math.max(1, Math.round(fps / Math.max(4, fpsFeel))) : 1
  const { stepped: _s, ...rest } = b
  return { id: BASE[animation] ? animation : 'motion_graphics', step, ...rest }
}

/** The frame whose pose is shown: frames are held `step` at a time ("on twos"). */
export function pose(frame: number, m: Motion): number {
  return m.step > 1 ? Math.floor(frame / m.step) * m.step : frame
}

/** Deterministic pseudo-random number in [0,1) for (a, b): the same frame always renders the same wobble. */
export function rand(a: number, b = 0): number {
  const s = Math.sin(a * 127.1 + b * 311.7 + 17.13) * 43758.5453
  return s - Math.floor(s)
}

/** 0..1 progress of an entrance that starts at `start` and takes `dur` frames (default: the style's own). May overshoot above 1 for bouncy styles. */
export function enter(frame: number, start: number, m: Motion, fps: number, dur?: number): number {
  const f = pose(frame, m)
  const d = dur ?? m.enterFrames
  if (m.overshoot > 0.1) {
    // bouncy styles: a real spring (low damping => visible overshoot)
    return spring({ frame: f - start, fps, config: { damping: Math.max(4, 16 - m.overshoot * 40), mass: 0.7, stiffness: 170 }, durationInFrames: Math.max(d, 8) })
  }
  const t = interpolate(f, [start, start + d], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: m.ease })
  return t + (t > 0 && t < 1 ? Math.sin(t * Math.PI) * m.overshoot : 0)
}

/** Exit progress 0..1 that starts at `start`. */
export function leave(frame: number, start: number, m: Motion, dur = 12): number {
  const f = pose(frame, m)
  return interpolate(f, [start, start + dur], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.quad) })
}

/** Hand-made unrest of one element: {rot, dx, dy} that changes once per held pose (paper cut-outs, stop-motion, toon). */
export function unrest(frame: number, m: Motion, seed: number): { rot: number; dx: number; dy: number } {
  if (!m.wobbleDeg && !m.jitterPx) return { rot: 0, dx: 0, dy: 0 }
  const f = pose(frame, m)
  const k = m.step > 1 ? f / m.step : f / 3
  return {
    rot: (rand(k, seed) - 0.5) * 2 * m.wobbleDeg,
    dx: (rand(k, seed + 7) - 0.5) * 2 * m.jitterPx,
    dy: (rand(k, seed + 13) - 0.5) * 2 * m.jitterPx,
  }
}

/** Camera push-in factor (1 .. 1+camera) at `frame` of `total`. */
export function push(frame: number, total: number, m: Motion): number {
  return 1 + m.camera * interpolate(frame, [0, Math.max(1, total)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
}
