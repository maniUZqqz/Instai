// The "style kit": what a composition needs to know about one InstAI art style + theme.
// The kit is built by the backend (instai/remotion/kit.py) from the style library; compositions only read it.
// Nothing here imports Remotion, so the same file is used by the Remotion bundle (render) and by the InstAI page (preview).

export type Palette = {
  background: string
  primary: string
  secondary: string
  accent: string
  shadow: string
  highlight: string
}

export type Typography = {
  title_weight: 'regular' | 'bold' | 'black'
  title_case: 'normal' | 'upper' | 'lower'
  title_animation: 'none' | 'fade' | 'pop' | 'slide' | 'typewriter'
  subtitle_color: string
}

export type StyleKit = {
  key: string
  name: string
  /** how the style MOVES: live_camera | limited_2d | full_2d | rubber_hose | cutout | motion_graphics | stop_motion | cg_3d | toon_3d | painted_parallax */
  animation: string
  /** live_like | illustration | anime | western_2d | cg_3d | stop_motion | graphic | handmade */
  family: string
  realism: string
  /** how many different poses per second the style shows (12 = "on twos"); 24 and more = smooth */
  fps_feel: number
  palette: Palette
  typography: Typography
  mood: string
}

export const DEFAULT_PALETTE: Palette = {
  background: '#14181F',
  primary: '#3B4A5C',
  secondary: '#B9824B',
  accent: '#E8C98F',
  shadow: '#05070A',
  highlight: '#F3E9D8',
}

export const DEFAULT_KIT: StyleKit = {
  key: 'default',
  name: 'InstAI',
  animation: 'motion_graphics',
  family: 'graphic',
  realism: 'graphic',
  fps_feel: 30,
  palette: DEFAULT_PALETTE,
  typography: { title_weight: 'bold', title_case: 'normal', title_animation: 'pop', subtitle_color: '#FFFFFF' },
  mood: '',
}

const HEX = /^#[0-9a-fA-F]{6}$/

function hex(v: unknown, fallback: string): string {
  return typeof v === 'string' && HEX.test(v) ? v : fallback
}

/** A kit from whatever arrives (an API answer, a saved prop): every missing or invalid value falls back to the default. */
export function normalizeKit(raw?: Partial<StyleKit> | null): StyleKit {
  const r = (raw ?? {}) as Partial<StyleKit>
  const p = (r.palette ?? {}) as Partial<Palette>
  const t = (r.typography ?? {}) as Partial<Typography>
  const d = DEFAULT_KIT
  const pick = <T extends string>(v: unknown, allowed: readonly T[], fb: T): T => (allowed.includes(v as T) ? (v as T) : fb)
  return {
    key: String(r.key || d.key),
    name: String(r.name || d.name),
    animation: String(r.animation || d.animation),
    family: String(r.family || d.family),
    realism: String(r.realism || d.realism),
    fps_feel: Math.max(4, Math.min(60, Number(r.fps_feel) || d.fps_feel)),
    palette: {
      background: hex(p.background, d.palette.background),
      primary: hex(p.primary, d.palette.primary),
      secondary: hex(p.secondary, d.palette.secondary),
      accent: hex(p.accent, d.palette.accent),
      shadow: hex(p.shadow, d.palette.shadow),
      highlight: hex(p.highlight, d.palette.highlight),
    },
    typography: {
      title_weight: pick(t.title_weight, ['regular', 'bold', 'black'] as const, d.typography.title_weight),
      title_case: pick(t.title_case, ['normal', 'upper', 'lower'] as const, d.typography.title_case),
      title_animation: pick(t.title_animation, ['none', 'fade', 'pop', 'slide', 'typewriter'] as const, d.typography.title_animation),
      subtitle_color: hex(t.subtitle_color, d.typography.subtitle_color),
    },
    mood: String(r.mood || ''),
  }
}

function channels(c: string): [number, number, number] {
  return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]
}

/** Relative luminance (WCAG) of a #RRGGBB colour, 0 (black) .. 1 (white). */
export function luminance(c: string): number {
  const f = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  const [r, g, b] = channels(c).map(f)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m)
  return (x + 0.05) / (y + 0.05)
}

/** The text colour that reads on `bg`: the style's highlight / accent when it has enough contrast, else black or white. */
export function readableOn(bg: string, preferred: string[] = []): string {
  for (const c of preferred) if (contrast(c, bg) >= 4.5) return c
  return contrast('#FFFFFF', bg) >= contrast('#000000', bg) ? '#FFFFFF' : '#000000'
}

/** The accent colour as it is when it reads on `bg` (contrast >= 3 for large text), else the accent pulled toward the readable text colour until it does. */
export function accentOn(bg: string, accent: string): string {
  if (contrast(accent, bg) >= 3) return accent
  const text = contrast('#FFFFFF', bg) >= contrast('#000000', bg) ? '#FFFFFF' : '#000000'
  for (const t of [0.35, 0.5, 0.65, 0.8, 1]) {
    const c = mix(accent, text, t)
    if (contrast(c, bg) >= 3) return c
  }
  return text
}

export function mix(a: string, b: string, t: number): string {
  const [r1, g1, b1] = channels(a)
  const [r2, g2, b2] = channels(b)
  const m = (x: number, y: number) => Math.round(x + (y - x) * t).toString(16).padStart(2, '0')
  return `#${m(r1, r2)}${m(g1, g2)}${m(b1, b2)}`
}

/** Persian / Arabic script is drawn right to left. */
export function isRtlText(s: string): boolean {
  return /[֐-ࣿיִ-﷿ﹰ-﻿]/.test(s)
}

export function applyCase(s: string, mode: Typography['title_case']): string {
  if (mode === 'upper') return s.toUpperCase()
  if (mode === 'lower') return s.toLowerCase()
  return s
}

export const WEIGHT: Record<Typography['title_weight'], number> = { regular: 400, bold: 700, black: 700 }
