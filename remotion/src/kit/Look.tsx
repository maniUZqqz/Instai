import React from 'react'
import { AbsoluteFill } from 'remotion'
import { rand } from './motion'
import { mix, type Palette, type StyleKit } from './theme'

// The "look" of a style: the drawn surface that makes a named style recognisable beyond its palette and its family backdrop - a pixel skyline for Pixel Art, a
// chalk-dusted board in a wooden frame for the Chalkboard, a lead-lined glass window for Stained Glass, a frosted card for Glassmorphism ...
// Everything is plain CSS / SVG (no pictures, no downloads) and deterministic: the same frame always renders the same. The look is chosen by the style's
// `motif` (instai/styles: the same word that picks its drawn swatch). A motif that is not listed here keeps the family backdrop of Stage.tsx.
// Looks only paint decoration around the text, in tones close to the style's own background, so the text colours chosen by the compositions (readableOn /
// accentOn against `palette.background`) stay readable; the few looks that paint a plate under the text (glass, brutalist) do it translucent.

export type LookCtx = { kit: StyleKit; p: Palette; u: number; w: number; h: number; frame: number; f: number }
export type Look = {
  layers: React.ReactNode[]
  /** default true: the family backdrop of Stage.tsx is not drawn (the look is the whole surface); false = the look is drawn over it */
  replace?: boolean
  /** a soft veil of the style's own background colour behind the text, for looks whose pattern covers the whole frame (keeps the text readable) */
  veil?: boolean
  /** a CSS filter for everything drawn on top (the text): the pixel mosaic of Pixel Art, the colour split of Glitch */
  filter?: string
  /** SVG markup that the filter needs (rendered once, invisible) */
  defs?: React.ReactNode
}
type Maker = (c: LookCtx) => Look

const F = AbsoluteFill
const px = (c: LookCtx, v: number): number => c.u * v

/** `n` deterministic points in the frame: {x, y, r, k} with x, y in pixels, r and k in [0,1). */
function scatter(c: LookCtx, n: number, seed: number, clear = false): { x: number; y: number; r: number; k: number }[] {
  const salt = styleSalt(c.kit.key)         // two styles with the same look do not get the same scattering
  return Array.from({ length: n }, (_, i) => {
    const x = rand(i, seed + salt) * c.w
    let y = rand(i, seed + salt + 5) * c.h
    if (clear && Math.abs(x / c.w - 0.5) < 0.3 && Math.abs(y / c.h - 0.5) < 0.2) y = y < c.h / 2 ? y * 0.35 : c.h - (c.h - y) * 0.35     // keep the middle (the title) free
    return { x, y, r: rand(i, seed + salt + 9), k: rand(i, seed + salt + 13) }
  })
}

function styleSalt(key: string): number {
  let h = 0
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 997
  return h % 53
}

const wood = (p: Palette) => mix('#6b4423', p.accent, 0.18)

// ----------------------------------------------------------------------------------------------------------------- the looks

const pixel: Maker = (c) => {
  const cell = Math.max(6, Math.round(c.u / 96))
  const col = cell * 7
  const n = Math.ceil(c.w / col)
  const towers = Array.from({ length: n }, (_, i) => {
    const hgt = (6 + Math.floor(rand(i, 3) * 17)) * cell
    const tone = mix(c.p.background, c.p.primary, 0.35 + rand(i, 8) * 0.35)
    const windows: React.ReactNode[] = []
    for (let r = 1; r * cell * 2 < hgt - cell; r++) {
      for (let k = 0; k < 2; k++) {
        if (rand(i * 17 + r, k + 21) > 0.55) windows.push(<div key={r + '-' + k} style={{ position: 'absolute', left: cell * (1 + k * 3), bottom: r * cell * 2, width: cell * 2, height: cell, background: c.p.accent, opacity: 0.8 }} />)
      }
    }
    return <div key={i} style={{ position: 'absolute', left: i * col, bottom: 0, width: col - cell, height: hgt, background: tone, boxShadow: `inset ${cell}px 0 0 ${mix(tone, '#000000', 0.2)}` }}>{windows}</div>
  })
  const stars = scatter(c, 26, 31).map((s, i) => {
    const on = (Math.floor(c.f / 14) + i) % 3 !== 0
    return <div key={i} style={{ position: 'absolute', left: Math.round(s.x / cell) * cell, top: Math.round((s.y * 0.6) / cell) * cell, width: cell * (s.r > 0.8 ? 2 : 1), height: cell * (s.r > 0.8 ? 2 : 1), background: c.p.highlight, opacity: on ? 0.85 : 0.25 }} />
  })
  const moon = <div key="moon" style={{ position: 'absolute', right: cell * 8, top: cell * 7, width: cell * 8, height: cell * 8, background: c.p.highlight, opacity: 0.9, clipPath: 'polygon(25% 0, 75% 0, 75% 12%, 100% 12%, 100% 25%, 100% 75%, 88% 75%, 88% 88%, 75% 88%, 75% 100%, 25% 100%, 25% 88%, 12% 88%, 12% 75%, 0 75%, 0 25%, 12% 25%, 12% 12%, 25% 12%)' }} />
  const mesh = <F key="mesh" style={{ backgroundImage: `linear-gradient(${c.p.shadow}33 1px, transparent 1px), linear-gradient(90deg, ${c.p.shadow}33 1px, transparent 1px)`, backgroundSize: `${cell}px ${cell}px` }} />
  const cellN = Math.max(6, Math.round(c.u / 110))
  return {
    layers: [<F key="sky" style={{ background: `linear-gradient(${c.p.background} 0%, ${mix(c.p.background, c.p.secondary, 0.3)} 100%)` }} />, ...stars, moon, <div key="city" style={{ position: 'absolute', inset: 0 }}>{towers}</div>, mesh],
    replace: true,
    // the mosaic filter turns the title and every letter into blocks of one pixel size
    filter: 'url(#instai-pixel)',
    defs: (
      <filter id="instai-pixel" x="0" y="0" width="100%" height="100%">
        <feFlood x={cellN * 0.3} y={cellN * 0.3} height={cellN * 0.4} width={cellN * 0.4} />
        <feComposite width={cellN} height={cellN} />
        <feTile result="a" />
        <feComposite in="SourceGraphic" in2="a" operator="in" />
        <feMorphology operator="dilate" radius={cellN * 0.3} />
      </filter>
    ),
  }
}

const chalk: Maker = (c) => {
  const board = mix(c.p.background, c.p.primary, 0.12)
  const smudges = scatter(c, 9, 41).map((s, i) => (
    <div key={'s' + i} style={{ position: 'absolute', left: s.x - px(c, 0.3), top: s.y - px(c, 0.06), width: px(c, 0.3 + s.r * 0.4), height: px(c, 0.08 + s.k * 0.1), borderRadius: '50%', background: c.p.highlight, opacity: 0.045 + s.k * 0.04, filter: `blur(${px(c, 0.014)}px)`, transform: `rotate(${s.r * 40 - 20}deg)` }} />
  ))
  const dust = scatter(c, 90, 51).map((s, i) => <div key={'d' + i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.003 + s.r * 0.004), height: px(c, 0.003 + s.r * 0.004), borderRadius: '50%', background: c.p.highlight, opacity: 0.1 + s.k * 0.18 }} />)
  const frame = px(c, 0.032)
  const w = wood(c.p)
  const woodGrain = `repeating-linear-gradient(90deg, ${w} 0, ${mix(w, '#000000', 0.18)} ${px(c, 0.006)}px, ${w} ${px(c, 0.014)}px)`
  const tray = px(c, 0.03)
  const pieces = [0.18, 0.5, 0.66].map((x, i) => <div key={'p' + i} style={{ position: 'absolute', left: c.w * x, bottom: tray, width: px(c, 0.07 + i * 0.015), height: px(c, 0.012), borderRadius: px(c, 0.006), background: i === 1 ? c.p.accent : c.p.highlight, opacity: 0.9 }} />)
  return {
    layers: [
      <F key="board" style={{ background: `radial-gradient(ellipse at 50% 40%, ${mix(board, c.p.highlight, 0.07)}, ${board} 70%)` }} />,
      ...smudges,
      ...dust,
      <div key="underline" style={{ position: 'absolute', left: c.w * 0.1, right: c.w * 0.1, bottom: tray + px(c, 0.04), height: px(c, 0.004), background: c.p.highlight, opacity: 0.2, borderRadius: px(c, 0.004) }} />,
      ...pieces,
      <div key="tray" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: tray, background: woodGrain, boxShadow: `0 -${px(c, 0.004)}px 0 ${mix(w, '#000000', 0.35)}` }} />,
      <div key="ft" style={{ position: 'absolute', left: 0, right: 0, top: 0, height: frame, background: woodGrain }} />,
      <div key="fl" style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: frame, background: woodGrain }} />,
      <div key="fr" style={{ position: 'absolute', top: 0, bottom: 0, right: 0, width: frame, background: woodGrain }} />,
    ],
    replace: true,
  }
}

const whiteboard: Maker = (c) => {
  const lines = Array.from({ length: 5 }, (_, i) => (
    <div key={i} style={{ position: 'absolute', left: c.w * (0.06 + rand(i, 2) * 0.1), top: c.h * (0.12 + i * 0.19), width: c.w * (0.18 + rand(i, 4) * 0.22), height: px(c, 0.006), background: [c.p.accent, c.p.secondary, c.p.primary][i % 3], opacity: 0.22, borderRadius: px(c, 0.006), transform: `rotate(${(rand(i, 6) - 0.5) * 2}deg)` }} />
  ))
  const tray = px(c, 0.028)
  return {
    layers: [
      <F key="grid" style={{ backgroundImage: `radial-gradient(${c.p.shadow}30 ${px(c, 0.0016)}px, transparent ${px(c, 0.0026)}px)`, backgroundSize: `${px(c, 0.04)}px ${px(c, 0.04)}px` }} />,
      ...lines,
      <div key="ghost" style={{ position: 'absolute', right: c.w * 0.09, top: c.h * 0.16, width: px(c, 0.16), height: px(c, 0.16), borderRadius: '50%', border: `${px(c, 0.006)}px solid ${c.p.accent}`, opacity: 0.2 }} />,
      <div key="frame" style={{ position: 'absolute', inset: 0, boxShadow: `inset 0 0 0 ${px(c, 0.014)}px ${mix(c.p.background, c.p.shadow, 0.25)}, inset 0 0 ${px(c, 0.05)}px ${c.p.shadow}33` }} />,
      <div key="tray" style={{ position: 'absolute', left: c.w * 0.12, right: c.w * 0.12, bottom: 0, height: tray, background: mix(c.p.background, c.p.shadow, 0.35), borderRadius: `${px(c, 0.01)}px ${px(c, 0.01)}px 0 0` }} />,
      <div key="m1" style={{ position: 'absolute', left: c.w * 0.3, bottom: tray, width: px(c, 0.07), height: px(c, 0.016), background: c.p.accent, borderRadius: px(c, 0.004) }} />,
      <div key="m2" style={{ position: 'absolute', left: c.w * 0.42, bottom: tray, width: px(c, 0.07), height: px(c, 0.016), background: c.p.secondary, borderRadius: px(c, 0.004) }} />,
    ],
  }
}

const blueprint: Maker = (c) => {
  const ink = mix(c.p.background, c.p.highlight, 0.55)
  const minor = px(c, 0.025)
  const ticks = Array.from({ length: 11 }, (_, i) => <div key={i} style={{ position: 'absolute', left: c.w * (0.06 + i * 0.088), top: px(c, 0.04), width: 1, height: i % 5 === 0 ? px(c, 0.026) : px(c, 0.014), background: ink, opacity: 0.7 }} />)
  const mark = (k: string, st: React.CSSProperties) => <div key={k} style={{ position: 'absolute', width: px(c, 0.05), height: px(c, 0.05), borderColor: ink, borderStyle: 'solid', borderWidth: 0, ...st }} />
  return {
    layers: [
      <F key="minor" style={{ backgroundImage: `linear-gradient(${ink}40 1px, transparent 1px), linear-gradient(90deg, ${ink}40 1px, transparent 1px)`, backgroundSize: `${minor}px ${minor}px` }} />,
      <F key="major" style={{ backgroundImage: `linear-gradient(${ink}88 2px, transparent 2px), linear-gradient(90deg, ${ink}88 2px, transparent 2px)`, backgroundSize: `${minor * 5}px ${minor * 5}px` }} />,
      ...ticks,
      mark('tl', { left: px(c, 0.03), top: px(c, 0.09), borderLeftWidth: 2, borderTopWidth: 2 }),
      mark('tr', { right: px(c, 0.03), top: px(c, 0.09), borderRightWidth: 2, borderTopWidth: 2 }),
      mark('bl', { left: px(c, 0.03), bottom: px(c, 0.04), borderLeftWidth: 2, borderBottomWidth: 2 }),
      mark('br', { right: px(c, 0.03), bottom: px(c, 0.04), borderRightWidth: 2, borderBottomWidth: 2 }),
      <div key="circ" style={{ position: 'absolute', right: c.w * 0.07, bottom: c.h * 0.12, width: px(c, 0.2), height: px(c, 0.2), borderRadius: '50%', border: `2px dashed ${ink}`, opacity: 0.5 }} />,
      <div key="dim" style={{ position: 'absolute', left: c.w * 0.08, bottom: c.h * 0.1, width: c.w * 0.3, height: 0, borderTop: `2px solid ${ink}`, opacity: 0.55 }} />,
    ],
  }
}

const stained: Maker = (c) => {
  const cell = px(c, 0.17)
  const cols = Math.ceil(c.w / cell) + 1
  const rows = Math.ceil(c.h / cell) + 1
  const tones = [c.p.primary, c.p.secondary, c.p.accent, mix(c.p.primary, c.p.accent, 0.5), mix(c.p.secondary, c.p.shadow, 0.35)]
  const panes: React.ReactNode[] = []
  for (let r = 0; r < rows; r++) {
    for (let k = 0; k < cols; k++) {
      const x = k * cell + (r % 2 ? cell / 2 : 0) - cell / 2
      const y = r * cell
      const tone = mix(tones[Math.floor(rand(k, r + 3) * tones.length)], c.p.background, 0.38 + rand(k, r + 9) * 0.2)
      panes.push(<div key={r + '-' + k} style={{ position: 'absolute', left: x, top: y, width: cell, height: cell, background: `radial-gradient(circle at 50% 40%, ${mix(tone, '#ffffff', 0.22)}, ${tone})`, clipPath: 'polygon(50% 0, 100% 50%, 50% 100%, 0 50%)' }} />)
    }
  }
  return {
    layers: [
      <F key="lead0" style={{ background: mix(c.p.shadow, c.p.background, 0.3) }} />,
      ...panes,
      <F key="glow" style={{ background: `radial-gradient(ellipse at 50% 45%, ${c.p.highlight}33, transparent 55%)` }} />,
      <F key="bevel" style={{ boxShadow: `inset 0 0 0 ${px(c, 0.03)}px ${mix(c.p.shadow, c.p.background, 0.2)}, inset 0 0 ${px(c, 0.08)}px ${c.p.shadow}` }} />,
    ],
    replace: true,
  }
}

const mosaic: Maker = (c) => {
  const cell = px(c, 0.06)
  const tiles: React.ReactNode[] = []
  const cols = Math.ceil(c.w / cell)
  const rows = Math.ceil(c.h / cell)
  const tones = [c.p.primary, c.p.secondary, c.p.accent, mix(c.p.primary, c.p.highlight, 0.4)]
  for (let r = 0; r < rows; r++) {
    for (let k = 0; k < cols; k++) {
      const tone = mix(tones[Math.floor(rand(k, r + 1) * tones.length)], c.p.background, 0.55 + rand(k, r + 6) * 0.25)
      tiles.push(<div key={r + '-' + k} style={{ position: 'absolute', left: k * cell, top: r * cell, width: cell - px(c, 0.004), height: cell - px(c, 0.004), background: tone, borderRadius: px(c, 0.004), transform: `rotate(${(rand(k, r + 2) - 0.5) * 4}deg)` }} />)
    }
  }
  return { layers: [<F key="grout" style={{ background: mix(c.p.shadow, c.p.background, 0.45) }} />, ...tiles, <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 40%, ${c.p.shadow}99 100%)` }} />], replace: true }
}

const glass: Maker = (c) => {
  const orbs = [
    { x: 0.22, y: 0.3, r: 0.46, tone: c.p.primary },
    { x: 0.78, y: 0.7, r: 0.5, tone: c.p.accent },
    { x: 0.6, y: 0.2, r: 0.34, tone: c.p.secondary },
  ].map((o, i) => <div key={i} style={{ position: 'absolute', left: c.w * o.x - px(c, o.r) / 2 + Math.sin((c.frame + i * 40) / 60) * px(c, 0.02), top: c.h * o.y - px(c, o.r) / 2, width: px(c, o.r), height: px(c, o.r), borderRadius: '50%', background: o.tone, opacity: 0.8, filter: `blur(${px(c, 0.03)}px)` }} />)
  const card = (
    <div key="card" style={{ position: 'absolute', left: '8%', right: '8%', top: '22%', bottom: '22%', borderRadius: px(c, 0.05), background: 'rgba(255,255,255,0.13)', border: '1.5px solid rgba(255,255,255,0.42)', backdropFilter: `blur(${px(c, 0.028)}px) saturate(1.3)`, WebkitBackdropFilter: `blur(${px(c, 0.028)}px) saturate(1.3)`, boxShadow: `0 ${px(c, 0.02)}px ${px(c, 0.07)}px ${c.p.shadow}66, inset 0 1px 0 rgba(255,255,255,0.5)` }} />
  )
  return { layers: [...orbs, card], replace: true }
}

const brutal: Maker = (c) => {
  const b = px(c, 0.006)
  const blocks = [
    { x: 0.03, y: 0.34, w: 0.15, h: 0.2, tone: c.p.accent, rot: -3 },
    { x: 0.83, y: 0.3, w: 0.14, h: 0.17, tone: c.p.primary, rot: 4 },
    { x: 0.62, y: 0.68, w: 0.34, h: 0.22, tone: c.p.secondary, rot: 2.5 },
    { x: 0.05, y: 0.72, w: 0.26, h: 0.15, tone: c.p.highlight, rot: -2 },
  ].map((o, i) => <div key={i} style={{ position: 'absolute', left: c.w * o.x, top: c.h * o.y, width: c.w * o.w, height: c.h * o.h, background: o.tone, border: `${b}px solid #000000`, boxShadow: `${px(c, 0.014)}px ${px(c, 0.014)}px 0 #000000`, transform: `rotate(${o.rot}deg)`, opacity: 0.92 }} />)
  return { layers: [<F key="bg" style={{ background: mix(c.p.background, c.p.highlight, 0.12) }} />, ...blocks, <div key="frame" style={{ position: 'absolute', inset: px(c, 0.02), border: `${b}px solid #000000` }} />], replace: true }
}

const shapes: Maker = (c) => {
  // memphis / bauhaus / geometric / constructivist: scattered flat shapes in the palette
  const tones = [c.p.primary, c.p.secondary, c.p.accent, c.p.highlight]
  const items = scatter(c, 16, 61, true).map((s, i) => {
    const size = px(c, 0.05 + s.r * 0.12)
    const tone = tones[i % tones.length]
    const base: React.CSSProperties = { position: 'absolute', left: s.x, top: s.y, width: size, height: size, background: tone, opacity: 0.55, transform: `rotate(${s.k * 360 + c.f * 0.3 * (i % 2 ? 1 : -1)}deg)` }
    if (i % 4 === 0) return <div key={i} style={{ ...base, borderRadius: '50%' }} />
    if (i % 4 === 1) return <div key={i} style={{ ...base, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />
    if (i % 4 === 2) return <div key={i} style={{ ...base, height: size * 0.22, borderRadius: size }} />
    return <div key={i} style={{ ...base, background: 'transparent', border: `${px(c, 0.008)}px solid ${tone}` }} />
  })
  return { layers: [<F key="bg" style={{ backgroundImage: `radial-gradient(${c.p.shadow}22 ${px(c, 0.003)}px, transparent ${px(c, 0.004)}px)`, backgroundSize: `${px(c, 0.03)}px ${px(c, 0.03)}px` }} />, ...items] }
}

const SLITS = 'linear-gradient(to bottom, #000 0%, #000 50%, transparent 50% 54%, #000 54% 61%, transparent 61% 66%, #000 66% 74%, transparent 74% 80%, #000 80% 88%, transparent 88% 100%)'

const vapor: Maker = (c) => {
  const wide = c.w > c.h
  const sun = px(c, wide ? 0.46 : 0.42)
  const horizon = c.h * (wide ? 0.66 : 0.8)
  const gridStep = px(c, 0.07)
  return {
    layers: [
      <F key="sky" style={{ background: `linear-gradient(${c.p.background} 0%, ${mix(c.p.background, c.p.primary, 0.55)} 55%, ${mix(c.p.primary, c.p.secondary, 0.5)} 100%)` }} />,
      <div key="sun" style={{ position: 'absolute', left: c.w * (wide ? 0.82 : 0.5) - sun / 2, top: horizon - sun * 0.9, width: sun, height: sun, borderRadius: '50%', background: `linear-gradient(${c.p.accent}, ${c.p.secondary})`, WebkitMaskImage: SLITS, maskImage: SLITS, opacity: 0.92 }} />,
      <div key="floor" style={{ position: 'absolute', left: 0, right: 0, top: horizon, bottom: 0, background: `linear-gradient(${mix(c.p.background, c.p.primary, 0.4)}, ${c.p.background})`, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: '-50%', right: '-50%', top: 0, bottom: 0, transform: 'perspective(500px) rotateX(58deg)', transformOrigin: 'top', backgroundImage: `linear-gradient(${c.p.accent}aa 2px, transparent 2px), linear-gradient(90deg, ${c.p.accent}aa 2px, transparent 2px)`, backgroundSize: `${gridStep}px ${gridStep}px`, backgroundPosition: `0 ${(c.f * 1.5) % gridStep}px` }} />
      </div>,
      <div key="line" style={{ position: 'absolute', left: 0, right: 0, top: horizon - 1, height: 3, background: c.p.accent, boxShadow: `0 0 ${px(c, 0.02)}px ${c.p.accent}` }} />,
    ],
    replace: true,
  }
}

const glitch: Maker = (c) => {
  const slices = Array.from({ length: 9 }, (_, i) => {
    const on = Math.floor(c.f / 3 + i * 5) % 7 < 2
    const y = rand(i, Math.floor(c.f / 6)) * c.h
    const hgt = px(c, 0.012 + rand(i, 5) * 0.05)
    return <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: y, height: hgt, background: [c.p.accent, c.p.secondary, c.p.highlight][i % 3], opacity: on ? 0.42 : 0.1, transform: `translateX(${(rand(i, Math.floor(c.f / 3)) - 0.5) * px(c, 0.2)}px)`, mixBlendMode: 'screen' }} />
  })
  return {
    layers: [
      <F key="scan" style={{ backgroundImage: `repeating-linear-gradient(to bottom, transparent 0, transparent ${px(c, 0.004)}px, ${c.p.shadow}55 ${px(c, 0.004)}px, ${c.p.shadow}55 ${px(c, 0.007)}px)` }} />,
      ...slices,
      <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 50%, ${c.p.shadow}AA 100%)` }} />,
    ],
    // a red / cyan split of everything on top (the text)
    filter: `drop-shadow(${px(c, 0.006)}px 0 0 #ff2d55aa) drop-shadow(${-px(c, 0.006)}px 0 0 #00e5ffaa)`,
  }
}

const vhs: Maker = (c) => {
  const bar = ((c.f * 4) % (c.h + 200)) - 100
  return {
    layers: [
      <F key="scan" style={{ backgroundImage: `repeating-linear-gradient(to bottom, transparent 0, transparent ${px(c, 0.003)}px, ${c.p.shadow}44 ${px(c, 0.003)}px, ${c.p.shadow}44 ${px(c, 0.006)}px)` }} />,
      <div key="track" style={{ position: 'absolute', left: 0, right: 0, top: bar, height: px(c, 0.05), background: `linear-gradient(transparent, ${c.p.highlight}33, transparent)` }} />,
      <div key="noise" style={{ position: 'absolute', left: 0, right: 0, bottom: px(c, 0.03), height: px(c, 0.02), backgroundImage: `repeating-linear-gradient(90deg, ${c.p.highlight}66 0, ${c.p.highlight}66 ${px(c, 0.004)}px, transparent ${px(c, 0.004)}px, transparent ${px(c, 0.011)}px)`, opacity: 0.5, transform: `translateX(${(rand(Math.floor(c.f / 2), 1) - 0.5) * px(c, 0.05)}px)` }} />,
      <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 55%, ${c.p.shadow}88 100%)` }} />,
    ],
    filter: `drop-shadow(${px(c, 0.003)}px 0 0 #ff3b3b88) drop-shadow(${-px(c, 0.003)}px 0 0 #3bd8ff88)`,
  }
}

const noir: Maker = (c) => {
  const blindsTone = `${c.p.shadow}`
  return {
    layers: [
      <F key="blinds" style={{ backgroundImage: `repeating-linear-gradient(115deg, transparent 0, transparent ${px(c, 0.07)}px, ${blindsTone}66 ${px(c, 0.07)}px, ${blindsTone}66 ${px(c, 0.13)}px)`, backgroundPosition: `${Math.sin(c.f / 120) * px(c, 0.03)}px 0` }} />,
      <F key="spot" style={{ background: `radial-gradient(ellipse at 28% 30%, ${c.p.highlight}33, transparent 45%)` }} />,
      <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 35%, ${c.p.shadow}DD 100%)` }} />,
    ],
    replace: false,
  }
}

const halftone: Maker = (c) => {
  const cell = px(c, 0.028)
  return {
    layers: [
      <F key="dots" style={{ backgroundImage: `radial-gradient(${c.p.primary}88 ${cell * 0.3}px, transparent ${cell * 0.34}px)`, backgroundSize: `${cell}px ${cell}px`, WebkitMaskImage: 'linear-gradient(115deg, #000 0%, transparent 62%)', maskImage: 'linear-gradient(115deg, #000 0%, transparent 62%)' }} />,
      <F key="dots2" style={{ backgroundImage: `radial-gradient(${c.p.secondary}77 ${cell * 0.22}px, transparent ${cell * 0.26}px)`, backgroundSize: `${cell}px ${cell}px`, backgroundPosition: `${cell / 2}px ${cell / 2}px`, WebkitMaskImage: 'linear-gradient(295deg, #000 0%, transparent 55%)', maskImage: 'linear-gradient(295deg, #000 0%, transparent 55%)' }} />,
      <F key="rays" style={{ background: `repeating-conic-gradient(from 0deg at 50% 50%, ${c.p.accent}1c 0deg 3deg, transparent 3deg 12deg)`, opacity: 0.8 }} />,
      <div key="burst" style={{ position: 'absolute', right: c.w * 0.06, top: c.h * 0.08, width: px(c, 0.22), height: px(c, 0.22), background: c.p.accent, opacity: 0.55, clipPath: 'polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)', transform: `rotate(${c.f * 0.4}deg)` }} />,
    ],
  }
}

const riso: Maker = (c) => {
  const grain = px(c, 0.006)
  return {
    layers: [
      <div key="b1" style={{ position: 'absolute', left: c.w * 0.04, top: c.h * 0.1, width: c.w * 0.55, height: c.h * 0.6, background: c.p.primary, opacity: 0.45, mixBlendMode: 'multiply', borderRadius: '8% 22% 12% 30%' }} />,
      <div key="b2" style={{ position: 'absolute', left: c.w * 0.1, top: c.h * 0.16, width: c.w * 0.55, height: c.h * 0.6, background: c.p.accent, opacity: 0.4, mixBlendMode: 'multiply', borderRadius: '8% 22% 12% 30%' }} />,
      <F key="grain" style={{ backgroundImage: `radial-gradient(${c.p.shadow}55 ${grain * 0.35}px, transparent ${grain * 0.4}px)`, backgroundSize: `${grain}px ${grain}px` }} />,
    ],
  }
}

const paper: Maker = (c) => {
  const tones = [c.p.primary, c.p.secondary, c.p.accent, mix(c.p.primary, c.p.highlight, 0.3)]
  const strips = scatter(c, 7, 71).map((s, i) => (
    <div key={i} style={{ position: 'absolute', left: s.x - px(c, 0.2), top: s.y - px(c, 0.05), width: px(c, 0.34 + s.r * 0.3), height: px(c, 0.08 + s.k * 0.12), background: mix(tones[i % tones.length], c.p.background, 0.35), transform: `rotate(${(s.r - 0.5) * 36}deg)`, boxShadow: `${px(c, 0.004)}px ${px(c, 0.008)}px ${px(c, 0.014)}px ${c.p.shadow}66`, clipPath: i % 2 ? 'polygon(0 6%, 100% 0, 97% 100%, 3% 94%)' : 'polygon(2% 0, 100% 8%, 98% 92%, 0 100%)' }} />
  ))
  const tape = scatter(c, 4, 83).map((s, i) => <div key={'t' + i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.1), height: px(c, 0.03), background: `${c.p.highlight}66`, transform: `rotate(${(s.r - 0.5) * 70}deg)` }} />)
  return { layers: [<F key="sheet" style={{ background: `linear-gradient(160deg, ${mix(c.p.background, c.p.highlight, 0.08)}, ${c.p.background})` }} />, ...strips, ...tape], replace: true }
}

const origami: Maker = (c) => {
  const tones = [c.p.primary, c.p.secondary, c.p.accent, mix(c.p.primary, c.p.highlight, 0.4)]
  const t = px(c, 0.3)
  const tris: React.ReactNode[] = []
  for (let r = 0; r * t * 0.86 < c.h + t; r++) {
    for (let k = -1; k * t < c.w + t; k++) {
      const x = k * t + (r % 2 ? t / 2 : 0)
      const y = r * t * 0.86
      const a = mix(tones[Math.floor(rand(k + 5, r) * tones.length)], c.p.background, 0.5)
      const b = mix(a, '#000000', 0.16)
      tris.push(<div key={'u' + r + '-' + k} style={{ position: 'absolute', left: x, top: y, width: t, height: t * 0.86, background: a, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />)
      tris.push(<div key={'d' + r + '-' + k} style={{ position: 'absolute', left: x + t / 2, top: y, width: t, height: t * 0.86, background: b, clipPath: 'polygon(0 0, 100% 0, 50% 100%)' }} />)
    }
  }
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, ...tris, <F key="light" style={{ background: `linear-gradient(135deg, ${c.p.highlight}2e, transparent 50%, ${c.p.shadow}55)` }} />], replace: true }
}

const lowpoly: Maker = (c) => {
  const t = px(c, 0.22)
  const out: React.ReactNode[] = []
  for (let r = 0; r * t * 0.8 < c.h + t; r++) {
    for (let k = -1; k * t < c.w + t; k++) {
      const jx = (rand(k, r) - 0.5) * t * 0.25
      const jy = (rand(k, r + 3) - 0.5) * t * 0.2
      const x = k * t + (r % 2 ? t / 2 : 0) + jx
      const y = r * t * 0.8 + jy
      const shade = 0.2 + rand(k + 7, r) * 0.5
      const tone = mix(c.p.primary, c.p.secondary, rand(k, r + 9))
      const g = mix(mix(c.p.background, tone, 0.5), c.p.highlight, shade * 0.25)
      out.push(<div key={'a' + r + '-' + k} style={{ position: 'absolute', left: x, top: y, width: t, height: t * 0.8, background: g, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />)
      out.push(<div key={'b' + r + '-' + k} style={{ position: 'absolute', left: x + t / 2, top: y, width: t, height: t * 0.8, background: mix(g, c.p.shadow, 0.3), clipPath: 'polygon(0 0, 100% 0, 50% 100%)' }} />)
    }
  }
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, ...out, <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 45%, ${c.p.shadow}99 100%)` }} />], replace: true }
}

const voxel: Maker = (c) => {
  const s = px(c, 0.09)
  const cubes: React.ReactNode[] = []
  const cols = Math.ceil(c.w / (s * 1.73)) + 1
  const rows = Math.ceil(c.h / (s * 1.5)) + 1
  for (let r = 0; r < rows; r++) {
    for (let k = 0; k < cols; k++) {
      const h = Math.floor(rand(k, r) * 3)
      if (h === 0 && rand(k, r + 4) > 0.3) continue
      const x = k * s * 1.73 + (r % 2 ? s * 0.865 : 0)
      const y = r * s * 1.5 - h * s * 0.5
      const top = mix(c.p.accent, c.p.background, 0.45)
      cubes.push(
        <div key={r + '-' + k} style={{ position: 'absolute', left: x, top: y, width: s * 1.73, height: s * 2 }}>
          <div style={{ position: 'absolute', inset: 0, background: top, clipPath: 'polygon(50% 0, 100% 25%, 50% 50%, 0 25%)' }} />
          <div style={{ position: 'absolute', inset: 0, background: mix(c.p.primary, c.p.background, 0.45), clipPath: 'polygon(0 25%, 50% 50%, 50% 100%, 0 75%)' }} />
          <div style={{ position: 'absolute', inset: 0, background: mix(c.p.primary, c.p.shadow, 0.45), clipPath: 'polygon(50% 50%, 100% 25%, 100% 75%, 50% 100%)' }} />
        </div>,
      )
    }
  }
  return { layers: [<F key="bg" style={{ background: `linear-gradient(${c.p.background}, ${mix(c.p.background, c.p.primary, 0.3)})` }} />, ...cubes, <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 40%, ${c.p.shadow}99 100%)` }} />], replace: true }
}

const bricks: Maker = (c) => {
  const s = px(c, 0.07)
  const out: React.ReactNode[] = []
  const cols = Math.ceil(c.w / (s * 1.2)) + 1
  const rows = Math.ceil(c.h / s) + 1
  const tones = [c.p.primary, c.p.secondary, c.p.accent]
  for (let r = 0; r < rows; r++) {
    for (let k = 0; k < cols; k++) {
      const tone = mix(tones[Math.floor(rand(k, r) * tones.length)], c.p.background, 0.7)
      out.push(
        <div key={r + '-' + k} style={{ position: 'absolute', left: k * s * 1.2 + (r % 2 ? s * 0.6 : 0) - s * 0.6, top: r * s, width: s * 1.2 - px(c, 0.004), height: s - px(c, 0.004), background: tone, borderRadius: px(c, 0.006), boxShadow: `inset 0 -${px(c, 0.006)}px 0 ${mix(tone, '#000000', 0.22)}` }}>
          <div style={{ position: 'absolute', left: '50%', top: '-6%', width: s * 0.5, height: s * 0.2, marginLeft: -s * 0.25, borderRadius: px(c, 0.008), background: mix(tone, '#ffffff', 0.18) }} />
        </div>,
      )
    }
  }
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, ...out, <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 40%, ${c.p.shadow}88 100%)` }} />], replace: true }
}

const watercolor: Maker = (c) => {
  const tones = [c.p.primary, c.p.secondary, c.p.accent]
  const blots = scatter(c, 7, 91).map((s, i) => (
    <div key={i} style={{ position: 'absolute', left: s.x - px(c, 0.25), top: s.y - px(c, 0.2), width: px(c, 0.4 + s.r * 0.4), height: px(c, 0.32 + s.k * 0.3), borderRadius: `${40 + s.r * 20}% ${60 - s.k * 20}% ${50 + s.k * 20}% ${50 - s.r * 15}%`, background: tones[i % tones.length], opacity: 0.3, filter: `blur(${px(c, 0.022)}px)`, transform: `translate(${Math.sin((c.frame + i * 50) / 80) * px(c, 0.012)}px, 0)` }} />
  ))
  const fibres = scatter(c, 40, 97).map((s, i) => <div key={'f' + i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.02 + s.r * 0.03), height: 1, background: c.p.shadow, opacity: 0.1, transform: `rotate(${s.k * 180}deg)` }} />)
  return { layers: [<F key="paper" style={{ background: mix(c.p.background, c.p.highlight, 0.1) }} />, ...blots, ...fibres, <F key="edge" style={{ boxShadow: `inset 0 0 ${px(c, 0.07)}px ${c.p.shadow}55` }} />], replace: true }
}

const stitch: Maker = (c) => {
  const weave = px(c, 0.012)
  const thread = c.p.accent
  return {
    layers: [
      <F key="cloth" style={{ background: mix(c.p.background, c.p.primary, 0.22) }} />,
      <F key="w1" style={{ backgroundImage: `repeating-linear-gradient(0deg, ${c.p.shadow}1f 0, ${c.p.shadow}1f 1px, transparent 1px, transparent ${weave}px), repeating-linear-gradient(90deg, ${c.p.shadow}1f 0, ${c.p.shadow}1f 1px, transparent 1px, transparent ${weave}px)` }} />,
      <div key="seam" style={{ position: 'absolute', inset: px(c, 0.035), border: `${px(c, 0.006)}px dashed ${thread}`, borderRadius: px(c, 0.02), opacity: 0.85 }} />,
      <div key="seam2" style={{ position: 'absolute', inset: px(c, 0.055), border: `${px(c, 0.004)}px dotted ${c.p.secondary}`, borderRadius: px(c, 0.012), opacity: 0.7 }} />,
    ],
    replace: true,
  }
}

const sketch: Maker = (c) => {
  // hand-drawn scribbles: wobbly lines that are re-drawn "on twos"
  const n = 9
  const lines = Array.from({ length: n }, (_, i) => {
    const y = c.h * (0.08 + (i / n) * 0.9)
    const seed = Math.floor(c.f / 6) * 3 + i
    const d = Array.from({ length: 9 }, (_, k) => `${k === 0 ? 'M' : 'L'} ${(k / 8) * c.w} ${y + (rand(seed, k) - 0.5) * px(c, 0.012)}`).join(' ')
    return <path key={i} d={d} stroke={c.p.shadow} strokeWidth={px(c, 0.003)} fill="none" opacity={0.3} strokeLinecap="round" />
  })
  const loops = scatter(c, 4, 101).map((s, i) => <circle key={'c' + i} cx={s.x} cy={s.y} r={px(c, 0.05 + s.r * 0.08) + Math.sin(c.f / 7 + i) * 1.2} stroke={c.p.accent} strokeWidth={px(c, 0.004)} fill="none" opacity={0.5} />)
  return { layers: [<F key="paper" style={{ background: mix(c.p.background, c.p.highlight, 0.1) }} />, <svg key="svg" width={c.w} height={c.h} style={{ position: 'absolute', inset: 0 }}>{lines}{loops}</svg>], replace: true }
}

const terminal: Maker = (c) => {
  const on = Math.floor(c.frame / 15) % 2 === 0
  const rows = Array.from({ length: 12 }, (_, i) => <div key={i} style={{ position: 'absolute', left: px(c, 0.04), top: c.h * (0.06 + i * 0.075), width: c.w * (0.1 + rand(i, 3) * 0.3), height: px(c, 0.012), background: c.p.accent, opacity: 0.18 }} />)
  return {
    layers: [
      <F key="bg" style={{ background: `radial-gradient(ellipse at 50% 50%, ${mix(c.p.background, c.p.primary, 0.2)}, ${c.p.background})` }} />,
      ...rows,
      <F key="scan" style={{ backgroundImage: `repeating-linear-gradient(to bottom, transparent 0, transparent ${px(c, 0.004)}px, ${c.p.shadow}55 ${px(c, 0.004)}px, ${c.p.shadow}55 ${px(c, 0.007)}px)` }} />,
      <div key="cur" style={{ position: 'absolute', left: px(c, 0.04), bottom: px(c, 0.05), width: px(c, 0.03), height: px(c, 0.05), background: c.p.accent, opacity: on ? 0.9 : 0 }} />,
    ],
    replace: true,
  }
}

const wire: Maker = (c) => {
  const ink = c.p.accent
  const r = px(c, 0.34)
  const corner = (k: string, st: React.CSSProperties) => <div key={k} style={{ position: 'absolute', width: px(c, 0.07), height: px(c, 0.07), borderStyle: 'solid', borderColor: ink, borderWidth: 0, ...st }} />
  return {
    layers: [
      <F key="grid" style={{ backgroundImage: `linear-gradient(${ink}22 1px, transparent 1px), linear-gradient(90deg, ${ink}22 1px, transparent 1px)`, backgroundSize: `${px(c, 0.05)}px ${px(c, 0.05)}px` }} />,
      <div key="ring" style={{ position: 'absolute', left: c.w / 2 - r, top: c.h / 2 - r, width: r * 2, height: r * 2, borderRadius: '50%', border: `2px solid ${ink}66`, transform: `rotate(${c.f * 0.6}deg)`, backgroundImage: `conic-gradient(${ink}66 0deg 10deg, transparent 10deg 90deg, ${ink}66 90deg 100deg, transparent 100deg 180deg, ${ink}66 180deg 190deg, transparent 190deg 270deg, ${ink}66 270deg 280deg, transparent 280deg)`, WebkitMaskImage: `radial-gradient(circle, transparent ${r - 6}px, #000 ${r - 5}px)`, maskImage: `radial-gradient(circle, transparent ${r - 6}px, #000 ${r - 5}px)` }} />,
      corner('a', { left: px(c, 0.03), top: px(c, 0.03), borderLeftWidth: 3, borderTopWidth: 3 }),
      corner('b', { right: px(c, 0.03), top: px(c, 0.03), borderRightWidth: 3, borderTopWidth: 3 }),
      corner('c', { left: px(c, 0.03), bottom: px(c, 0.03), borderLeftWidth: 3, borderBottomWidth: 3 }),
      corner('d', { right: px(c, 0.03), bottom: px(c, 0.03), borderRightWidth: 3, borderBottomWidth: 3 }),
    ],
  }
}

const particles: Maker = (c) => {
  const pts = scatter(c, 46, 111).map((s, i) => {
    const x = (s.x + c.frame * (0.3 + s.r) * (i % 2 ? 1 : -1) + c.w * 4) % c.w
    const y = (s.y - c.frame * (0.4 + s.k * 0.6) + c.h * 4) % c.h
    return { x, y, r: px(c, 0.004 + s.r * 0.01), i }
  })
  const links: React.ReactNode[] = []
  for (let a = 0; a < pts.length; a++) for (let b = a + 1; b < pts.length; b++) {
    const d = Math.hypot(pts[a].x - pts[b].x, pts[a].y - pts[b].y)
    if (d < px(c, 0.2)) links.push(<line key={a + '-' + b} x1={pts[a].x} y1={pts[a].y} x2={pts[b].x} y2={pts[b].y} stroke={c.p.accent} strokeWidth={1.2} opacity={0.35 * (1 - d / px(c, 0.2))} />)
  }
  return { layers: [<svg key="svg" width={c.w} height={c.h} style={{ position: 'absolute', inset: 0 }}>{links}{pts.map((q) => <circle key={q.i} cx={q.x} cy={q.y} r={q.r} fill={c.p.highlight} opacity={0.75} />)}</svg>] }
}

const neon: Maker = (c) => {
  const tube = c.p.accent
  const flick = Math.floor(c.f / 5) % 23 === 0 ? 0.55 : 1
  return {
    layers: [
      <F key="wall" style={{ backgroundImage: `linear-gradient(${c.p.shadow}66 1px, transparent 1px), linear-gradient(90deg, ${c.p.shadow}44 1px, transparent 1px)`, backgroundSize: `${px(c, 0.11)}px ${px(c, 0.055)}px` }} />,
      <div key="t1" style={{ position: 'absolute', left: '7%', right: '7%', top: '16%', bottom: '16%', border: `${px(c, 0.006)}px solid ${tube}`, borderRadius: px(c, 0.06), opacity: flick, boxShadow: `0 0 ${px(c, 0.02)}px ${tube}, 0 0 ${px(c, 0.06)}px ${tube}99, inset 0 0 ${px(c, 0.02)}px ${tube}88` }} />,
      <div key="glow" style={{ position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 50% 50%, ${tube}22, transparent 60%)`, opacity: flick }} />,
    ],
  }
}

const sunburst: Maker = (c) => ({
  layers: [
    <F key="rays" style={{ background: `repeating-conic-gradient(from ${c.f * 0.05}deg at 50% 62%, ${c.p.accent}30 0deg 5deg, transparent 5deg 15deg)` }} />,
    <div key="b1" style={{ position: 'absolute', inset: px(c, 0.035), border: `${px(c, 0.005)}px solid ${c.p.accent}`, opacity: 0.75 }} />,
    <div key="b2" style={{ position: 'absolute', inset: px(c, 0.05), border: `${px(c, 0.002)}px solid ${c.p.accent}`, opacity: 0.6 }} />,
  ],
})

const ornament: Maker = (c) => {
  // art nouveau / persian miniature / islamic geometry: a framed, ornamented panel with a star lattice
  const s = px(c, 0.16)
  const stars: React.ReactNode[] = []
  for (let r = 0; r * s < c.h + s; r++) for (let k = 0; k * s < c.w + s; k++) {
    stars.push(<div key={r + '-' + k} style={{ position: 'absolute', left: k * s, top: r * s, width: s, height: s, background: (r + k) % 2 ? `${c.p.accent}22` : `${c.p.secondary}22`, clipPath: 'polygon(50% 0, 61% 20%, 85% 15%, 80% 39%, 100% 50%, 80% 61%, 85% 85%, 61% 80%, 50% 100%, 39% 80%, 15% 85%, 20% 61%, 0 50%, 20% 39%, 15% 15%, 39% 20%)' }} />)
  }
  return {
    layers: [
      <div key="lat" style={{ position: 'absolute', inset: 0 }}>{stars}</div>,
      <div key="f1" style={{ position: 'absolute', inset: px(c, 0.03), border: `${px(c, 0.008)}px solid ${c.p.accent}`, borderRadius: px(c, 0.01), opacity: 0.9 }} />,
      <div key="f2" style={{ position: 'absolute', inset: px(c, 0.055), border: `${px(c, 0.003)}px solid ${c.p.secondary}`, opacity: 0.8 }} />,
      <div key="f3" style={{ position: 'absolute', inset: px(c, 0.07), border: `${px(c, 0.002)}px dotted ${c.p.accent}`, opacity: 0.7 }} />,
    ],
  }
}

const waves: Maker = (c) => {
  // woodblock / ukiyo-e: rows of overlapping wave arcs (seigaiha)
  const r = px(c, 0.09)
  const arcs: React.ReactNode[] = []
  for (let row = 0; row * r * 0.5 < c.h + r; row++) {
    for (let k = -1; k * r * 2 < c.w + r * 2; k++) {
      const x = k * r * 2 + (row % 2 ? r : 0)
      const y = c.h - row * r * 0.5
      const tone = mix(c.p.primary, c.p.background, 0.55 - (row % 3) * 0.1)
      arcs.push(<div key={row + '-' + k} style={{ position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: '50%', background: `radial-gradient(circle, ${tone} 28%, ${mix(tone, c.p.highlight, 0.3)} 29%, ${mix(tone, c.p.highlight, 0.3)} 33%, ${tone} 34%, ${tone} 56%, ${mix(tone, c.p.highlight, 0.3)} 57%, ${mix(tone, c.p.highlight, 0.3)} 61%, ${tone} 62%)`, boxShadow: `0 0 0 1px ${c.p.shadow}55` }} />)
    }
  }
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, <div key="arcs" style={{ position: 'absolute', inset: 0, opacity: 0.55 }}>{arcs}</div>, <F key="wash" style={{ background: `linear-gradient(${c.p.background}EE 0%, ${c.p.background}55 55%, transparent)` }} />], replace: true }
}

const holo: Maker = (c) => ({
  layers: [
    <F key="foil" style={{ background: `linear-gradient(${115 + Math.sin(c.f / 50) * 20}deg, #ff6ec7aa, #7a6bffaa 25%, #3df2e0aa 50%, #fff27aaa 75%, #ff6ec7aa)`, opacity: 0.42, mixBlendMode: 'screen' }} />,
    ...scatter(c, 14, 121).map((s, i) => <div key={i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.02 + s.r * 0.03), height: px(c, 0.02 + s.r * 0.03), background: '#ffffff', opacity: 0.35 + 0.5 * Math.abs(Math.sin((c.f + i * 11) / 18)), clipPath: 'polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%)' }} />),
  ],
})

const chromeLook: Maker = (c) => ({
  layers: [
    <F key="env" style={{ background: `linear-gradient(180deg, ${mix(c.p.background, c.p.highlight, 0.25)} 0%, ${c.p.background} 58%, ${c.p.shadow} 64%, ${mix(c.p.primary, c.p.background, 0.5)} 100%)` }} />,
    <div key="sheen" style={{ position: 'absolute', top: 0, bottom: 0, left: ((c.f * 6) % (c.w * 1.6)) - c.w * 0.3, width: px(c, 0.12), background: `linear-gradient(90deg, transparent, ${c.p.highlight}55, transparent)`, transform: 'skewX(-20deg)' }} />,
  ],
  replace: true,
})

const kawaii: Maker = (c) => {
  const hearts = scatter(c, 16, 131).map((s, i) => (
    <div key={i} style={{ position: 'absolute', left: s.x, top: (((s.y - c.frame * (0.3 + s.r)) % c.h) + c.h) % c.h, width: px(c, 0.03 + s.r * 0.04), height: px(c, 0.03 + s.r * 0.04), background: [c.p.accent, c.p.secondary, c.p.highlight][i % 3], opacity: 0.5, clipPath: i % 2 ? 'polygon(50% 0, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)' : 'polygon(50% 25%, 62% 8%, 82% 5%, 96% 20%, 98% 42%, 84% 66%, 50% 96%, 16% 66%, 2% 42%, 4% 20%, 18% 5%, 38% 8%)' }} />
  ))
  return { layers: [<F key="bg" style={{ backgroundImage: `radial-gradient(${c.p.highlight}55 ${px(c, 0.012)}px, transparent ${px(c, 0.013)}px)`, backgroundSize: `${px(c, 0.07)}px ${px(c, 0.07)}px` }} />, ...hearts] }
}

const graffiti: Maker = (c) => {
  const drips = scatter(c, 9, 141).map((s, i) => <div key={i} style={{ position: 'absolute', left: s.x, top: c.h * 0.2 + s.y * 0.3, width: px(c, 0.008), height: px(c, 0.06 + s.r * 0.14), background: [c.p.accent, c.p.secondary, c.p.primary][i % 3], borderRadius: px(c, 0.008), opacity: 0.7 }} />)
  const spray = scatter(c, 5, 149).map((s, i) => <div key={'s' + i} style={{ position: 'absolute', left: s.x - px(c, 0.1), top: s.y - px(c, 0.1), width: px(c, 0.2 + s.r * 0.15), height: px(c, 0.2 + s.r * 0.15), borderRadius: '50%', background: `radial-gradient(circle, ${[c.p.accent, c.p.secondary, c.p.primary][i % 3]}66, transparent 65%)` }} />)
  return { layers: [<F key="wall" style={{ background: c.p.background }} />, <F key="bricks" style={{ backgroundImage: `linear-gradient(${c.p.shadow}55 ${px(c, 0.004)}px, transparent ${px(c, 0.004)}px), linear-gradient(90deg, ${c.p.shadow}33 ${px(c, 0.004)}px, transparent ${px(c, 0.004)}px)`, backgroundSize: `${px(c, 0.16)}px ${px(c, 0.07)}px` }} />, ...spray, ...drips], replace: true }
}

const steam: Maker = (c) => {
  const gear = (k: string, x: number, y: number, r: number, dir: number) => (
    <div key={k} style={{ position: 'absolute', left: x - r, top: y - r, width: r * 2, height: r * 2, borderRadius: '50%', border: `${r * 0.22}px dashed ${mix(c.p.accent, c.p.shadow, 0.2)}`, boxShadow: `inset 0 0 0 ${r * 0.18}px ${c.p.accent}33`, opacity: 0.6, transform: `rotate(${c.f * 0.5 * dir}deg)` }}>
      <div style={{ position: 'absolute', left: '50%', top: '50%', width: r * 0.6, height: r * 0.6, marginLeft: -r * 0.3, marginTop: -r * 0.3, borderRadius: '50%', border: `${r * 0.08}px solid ${c.p.accent}` }} />
    </div>
  )
  return { layers: [<F key="bg" style={{ background: `radial-gradient(ellipse at 50% 50%, ${mix(c.p.background, c.p.secondary, 0.15)}, ${c.p.background})` }} />, gear('g1', c.w * 0.14, c.h * 0.2, px(c, 0.16), 1), gear('g2', c.w * 0.86, c.h * 0.78, px(c, 0.22), -1), gear('g3', c.w * 0.3, c.h * 0.86, px(c, 0.1), -1)], replace: true }
}

const miniLook: Maker = (c) => ({
  // tilt-shift / miniature: sharp band in the middle, blurred top and bottom
  layers: [
    <F key="top" style={{ backdropFilter: `blur(${px(c, 0.012)}px)`, WebkitMaskImage: 'linear-gradient(to bottom, #000 0%, transparent 28%)', maskImage: 'linear-gradient(to bottom, #000 0%, transparent 28%)' }} />,
    <F key="bot" style={{ backdropFilter: `blur(${px(c, 0.012)}px)`, WebkitMaskImage: 'linear-gradient(to top, #000 0%, transparent 28%)', maskImage: 'linear-gradient(to top, #000 0%, transparent 28%)' }} />,
    <F key="sat" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 55%, ${c.p.shadow}44 100%)` }} />,
  ],
  replace: false,
})

const filmGrain: Maker = (c) => {
  const flick = 0.92 + rand(Math.floor(c.f / 2), 1) * 0.08
  const scratches = scatter(c, 5, 157).map((s, i) => (Math.floor(c.f / 2) + i) % 6 < 2 ? <div key={i} style={{ position: 'absolute', left: ((s.x + c.f * 13) % c.w), top: 0, width: 1, height: c.h, background: c.p.highlight, opacity: 0.18 }} /> : null)
  const dust = scatter(c, 36, 163 + Math.floor(c.f / 2)).map((s, i) => <div key={'d' + i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.002 + s.r * 0.004), height: px(c, 0.002 + s.r * 0.004), borderRadius: '50%', background: c.p.highlight, opacity: 0.35 }} />)
  return { layers: [<F key="warm" style={{ background: `${c.p.accent}14`, opacity: flick }} />, ...scratches, ...dust, <F key="vig" style={{ background: `radial-gradient(ellipse at 50% 50%, transparent 40%, ${c.p.shadow}BB 100%)` }} />], replace: false }
}

const infographic: Maker = (c) => {
  const bars = [0.4, 0.62, 0.5, 0.78, 0.9].map((v, i) => <div key={i} style={{ position: 'absolute', right: c.w * 0.06 + i * px(c, 0.06), bottom: c.h * 0.08, width: px(c, 0.04), height: c.h * 0.4 * v, background: [c.p.accent, c.p.secondary, c.p.primary][i % 3], opacity: 0.45, borderRadius: `${px(c, 0.008)}px ${px(c, 0.008)}px 0 0` }} />)
  return {
    layers: [
      <F key="grid" style={{ backgroundImage: `linear-gradient(${c.p.highlight}12 1px, transparent 1px)`, backgroundSize: `100% ${px(c, 0.06)}px` }} />,
      ...bars,
      <div key="donut" style={{ position: 'absolute', left: c.w * 0.06, top: c.h * 0.08, width: px(c, 0.2), height: px(c, 0.2), borderRadius: '50%', background: `conic-gradient(${c.p.accent} 0 38%, ${c.p.secondary} 38% 70%, ${c.p.primary} 70% 100%)`, opacity: 0.45, WebkitMaskImage: 'radial-gradient(circle, transparent 38%, #000 39%)', maskImage: 'radial-gradient(circle, transparent 38%, #000 39%)' }} />,
    ],
  }
}

const essay: Maker = (c) => ({
  // minimal black-and-white essay: a hairline frame, a big quotation mark and nothing else
  layers: [
    <div key="rule1" style={{ position: 'absolute', left: c.w * 0.1, right: c.w * 0.1, top: c.h * 0.12, height: 2, background: c.p.shadow, opacity: 0.55 }} />,
    <div key="rule2" style={{ position: 'absolute', left: c.w * 0.1, right: c.w * 0.1, bottom: c.h * 0.12, height: 2, background: c.p.shadow, opacity: 0.55 }} />,
    <div key="q" style={{ position: 'absolute', left: c.w * 0.1, top: c.h * 0.14, fontSize: px(c, 0.3), lineHeight: 1, color: c.p.shadow, opacity: 0.12, fontFamily: 'Georgia, serif' }}>{'“'}</div>,
  ],
})

const kineticLook: Maker = (c) => {
  // kinetic typography: lines of text sliding across, drawn as rounded bars (no letters: the script of the video is not ours to guess)
  const tones = [c.p.primary, c.p.secondary, c.p.accent, c.p.primary, c.p.secondary]
  const bars = Array.from({ length: 5 }, (_, i) => {
    const wd = c.w * (0.28 + rand(i, 3) * 0.34)
    const dir = i % 2 ? -1 : 1
    const x = (((rand(i, 5) * c.w + dir * c.frame * (1.6 + i * 0.5)) % (c.w + wd)) + c.w + wd) % (c.w + wd) - wd
    return <div key={i} style={{ position: 'absolute', left: x, top: c.h * (0.1 + i * 0.19), width: wd, height: px(c, 0.07), borderRadius: px(c, 0.035), background: tones[i], opacity: 0.2 }} />
  })
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, ...bars] }
}

const doubleExp: Maker = (c) => ({
  layers: [
    <F key="a" style={{ background: `radial-gradient(ellipse at 30% 40%, ${c.p.secondary}66, transparent 55%)`, mixBlendMode: 'screen' }} />,
    <F key="b" style={{ background: `radial-gradient(ellipse at 72% 62%, ${c.p.accent}55, transparent 50%)`, mixBlendMode: 'screen' }} />,
    <F key="lines" style={{ backgroundImage: `repeating-linear-gradient(0deg, ${c.p.highlight}12 0, ${c.p.highlight}12 1px, transparent 1px, transparent ${px(c, 0.02)}px)` }} />,
  ],
  replace: false,
})

const felt: Maker = (c) => {
  const fur = scatter(c, 280, 171).map((s, i) => <div key={i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.012 + s.r * 0.012), height: 1.5, background: i % 2 ? c.p.highlight : c.p.shadow, opacity: 0.26, transform: `rotate(${s.k * 360}deg)` }} />)
  return { layers: [<F key="felt" style={{ background: `radial-gradient(ellipse at 50% 40%, ${mix(c.p.background, c.p.primary, 0.35)}, ${c.p.background})` }} />, ...fur, <div key="stitch" style={{ position: 'absolute', inset: px(c, 0.04), border: `${px(c, 0.006)}px dashed ${c.p.highlight}`, borderRadius: px(c, 0.03), opacity: 0.8 }} />], replace: true }
}

const sticker: Maker = (c) => {
  const items = scatter(c, 9, 181, true).map((s, i) => <div key={i} style={{ position: 'absolute', left: s.x, top: s.y, width: px(c, 0.07 + s.r * 0.06), height: px(c, 0.07 + s.r * 0.06), borderRadius: i % 3 ? '50%' : px(c, 0.02), background: [c.p.accent, c.p.secondary, c.p.primary][i % 3], border: `${px(c, 0.008)}px solid #ffffff`, boxShadow: `0 ${px(c, 0.006)}px ${px(c, 0.012)}px ${c.p.shadow}66`, transform: `rotate(${(s.k - 0.5) * 50}deg)`, opacity: 0.85 }} />)
  return { layers: items }
}

const corporate: Maker = (c) => {
  const blobs = [
    { x: 0.1, y: 0.2, r: 0.34, t: c.p.primary },
    { x: 0.85, y: 0.8, r: 0.4, t: c.p.secondary },
    { x: 0.7, y: 0.1, r: 0.2, t: c.p.accent },
  ].map((b, i) => <div key={i} style={{ position: 'absolute', left: c.w * b.x - px(c, b.r) / 2, top: c.h * b.y - px(c, b.r) / 2, width: px(c, b.r), height: px(c, b.r), background: b.t, opacity: 0.4, borderRadius: i === 0 ? '60% 40% 55% 45%' : i === 1 ? '45% 55% 40% 60%' : '50%' }} />)
  const leaf = (k: string, x: number, rot: number) => <div key={k} style={{ position: 'absolute', left: c.w * x, bottom: 0, width: px(c, 0.05), height: px(c, 0.16), background: c.p.accent, opacity: 0.55, borderRadius: '100% 0 100% 0', transform: `rotate(${rot}deg)`, transformOrigin: 'bottom center' }} />
  return { layers: [...blobs, leaf('l1', 0.05, -18), leaf('l2', 0.075, 10), leaf('l3', 0.09, 30)] }
}

const groovy: Maker = (c) => {
  const tones = [c.p.accent, c.p.secondary, c.p.primary, c.p.highlight]
  const arcs = Array.from({ length: 6 }, (_, i) => {
    const r = px(c, 0.95 - i * 0.14)
    return <div key={i} style={{ position: 'absolute', left: -r * 0.35, bottom: -r * 0.35, width: r * 2, height: r * 2, borderRadius: '50%', background: mix(tones[i % tones.length], c.p.background, 0.5), opacity: 0.8 }} />
  })
  return { layers: [<F key="bg" style={{ background: c.p.background }} />, ...arcs, <F key="shade" style={{ background: `linear-gradient(115deg, transparent 35%, ${c.p.background}CC 70%)` }} />], replace: true }
}

const stick: Maker = (c) => {
  const lines = Array.from({ length: 7 }, (_, i) => <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: c.h * (0.12 + i * 0.13), height: 2, background: c.p.primary, opacity: 0.18 }} />)
  return { layers: [<F key="paper" style={{ background: mix(c.p.background, c.p.highlight, 0.08) }} />, ...lines, <div key="m" style={{ position: 'absolute', left: c.w * 0.06, top: 0, bottom: 0, width: 2, background: c.p.accent, opacity: 0.4 }} />] }
}

// ----------------------------------------------------------------------------------------------------------------- which motif gets which look

/** motif (instai/styles) -> look. A motif that is not here keeps the family backdrop of Stage.tsx; tests/test_remotion.py checks that every motif of the library is
 *  either here or in PLAIN_MOTIFS, so a new style never silently gets no look at all. */
export const LOOKS: Record<string, Maker> = {
  pixel, voxel, iso: voxel, bricks, lowpoly, origami,
  chalk, whiteboard, blueprint, stained, mosaic, glass, brutal, stitch, felt, clay: felt, sticker, corp: corporate, stick, infographic, type: essay, kinetic: kineticLook,
  memphis: shapes, bauhaus: shapes, geometric: shapes, constructivist: shapes, groovy,
  vapor, synth: vapor, glitch, vhs, terminal, wire, particles, neon, neoncity: neon, holo, y2k: chromeLook, chrome: chromeLook,
  noir, halftone, riso, duotone: riso, paper, collage: paper, sketch, crayon: sketch,
  watercolor, paint: watercolor, ink: watercolor, woodblock: waves, deco: sunburst, nouveau: ornament, miniature: ornament,
  kawaii, graffiti, steam, tiltshift: miniLook, grain: filmGrain, doubleexp: doubleExp,
}

/** A style that shares its motif with a different-looking one gets its own surface by key (Islamic geometry is a star lattice, not scattered mid-century shapes). */
const KEY_LOOKS: Record<string, Maker> = { islamic_geometric_graphic: ornament }

/** Motifs that are deliberately left to the family backdrop of Stage.tsx: their family already is the look (a lit film frame, an anime sky, a flat toon, a 3-D scene,
 *  a layered parallax ...). */
export const PLAIN_MOTIFS = ['film', 'photo', 'anime', 'cg', 'flat', 'wobble', 'silhouette', 'parallax', 'surreal', 'console']

/** Motifs whose pattern covers the whole frame in several colours: a soft veil of the style's own background colour is drawn behind the text so it stays readable. */
const VEILED = new Set([
  'stained', 'mosaic', 'origami', 'lowpoly', 'voxel', 'iso', 'bricks', 'paper', 'collage', 'felt', 'clay', 'woodblock', 'nouveau', 'miniature', 'steam', 'graffiti',
  'memphis', 'bauhaus', 'geometric', 'constructivist', 'holo', 'groovy', 'halftone', 'riso', 'duotone', 'kawaii', 'sticker', 'watercolor', 'paint', 'ink',
])

export function lookFor(kit: StyleKit, c: LookCtx): Look | null {
  // own keys only: a custom style's motif is free text ('constructor' must not find Object's)
  const own = Object.prototype.hasOwnProperty.call(KEY_LOOKS, kit.key) ? KEY_LOOKS[kit.key] : null
  const make = own ?? (Object.prototype.hasOwnProperty.call(LOOKS, kit.motif) ? LOOKS[kit.motif] : null)
  if (!make) return null
  const made = make(c)
  const veil = made.veil ?? VEILED.has(kit.motif)
  const layers = veil ? [...made.layers, <F key="veil" style={{ background: `radial-gradient(ellipse at 50% 50%, ${c.p.background}C8 0%, ${c.p.background}88 34%, transparent 72%)` }} />] : made.layers
  return { ...made, layers, replace: made.replace ?? true }
}
