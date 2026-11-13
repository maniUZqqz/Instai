import React, { useEffect, useState } from 'react'
import { AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import { motionFor, pose, push, rand } from './motion'
import { mix, type StyleKit } from './theme'

/** Vazirmatn (SIL OFL) is the font of every composition. In a render it is loaded from the bundle's public/fonts folder and the frame
 *  waits for it; in the InstAI page (fontBase === 'page') the page's own @font-face is already there. */
export function useVazirmatn(fontBase?: string): void {
  const [handle] = useState(() => (fontBase === 'page' ? null : delayRender('Loading Vazirmatn')))
  useEffect(() => {
    if (handle === null) return
    const base = fontBase || staticFile('fonts/')
    const id = 'vazirmatn-face'
    if (!document.getElementById(id)) {
      const st = document.createElement('style')
      st.id = id
      st.textContent =
        `@font-face{font-family:'Vazirmatn';font-weight:400;src:url('${base.replace(/\/?$/, '/')}Vazirmatn-Regular.woff2') format('woff2');}` +
        `@font-face{font-family:'Vazirmatn';font-weight:700;src:url('${base.replace(/\/?$/, '/')}Vazirmatn-Bold.woff2') format('woff2');}`
      document.head.appendChild(st)
    }
    Promise.all([document.fonts.load("400 40px 'Vazirmatn'"), document.fonts.load("700 40px 'Vazirmatn'")])
      .catch(() => undefined)
      .then(() => continueRender(handle))
  }, [handle, fontBase])
}

export const FONT_STACK = "'Vazirmatn', 'Segoe UI', Tahoma, Arial, sans-serif"

type Props = { kit: StyleKit; children: React.ReactNode; backdrop?: boolean; zoom?: boolean }

/** The background world of a style: colours from its palette, shapes from its family, movement from its animation. */
export const Stage: React.FC<Props> = ({ kit, children, backdrop = true, zoom = true }) => {
  const frame = useCurrentFrame()
  const { fps, durationInFrames, width, height } = useVideoConfig()
  const m = motionFor(kit.animation, kit.fps_feel, fps)
  const p = kit.palette
  const f = pose(frame, m)
  const u = Math.min(width, height)
  const s = zoom ? push(frame, durationInFrames, m) : 1
  const drift = m.drift ? Math.sin(f / 90) : 0

  const layers: React.ReactNode[] = []
  const key = (n: string) => n
  if (backdrop) {
    if (kit.family === 'live_like') {
      layers.push(
        <AbsoluteFill key={key('vig')} style={{ background: `radial-gradient(ellipse at 50% 45%, transparent 35%, ${p.shadow}CC 100%)` }} />,
        <AbsoluteFill key={key('glow')} style={{ background: `radial-gradient(circle at ${30 + drift * 4}% 30%, ${p.secondary}33, transparent 55%)` }} />,
      )
    } else if (kit.family === 'illustration' || kit.family === 'handmade') {
      layers.push(
        <AbsoluteFill key={key('b1')} style={{ background: `radial-gradient(circle at ${25 + drift * 8}% ${30 - drift * 4}%, ${p.primary}88, transparent 45%)` }} />,
        <AbsoluteFill key={key('b2')} style={{ background: `radial-gradient(circle at ${75 - drift * 8}% ${70 + drift * 4}%, ${p.secondary}77, transparent 50%)` }} />,
        <AbsoluteFill key={key('b3')} style={{ background: `radial-gradient(circle at 60% 20%, ${p.accent}44, transparent 40%)` }} />,
      )
    } else if (kit.family === 'anime') {
      layers.push(
        <AbsoluteFill key={key('rays')} style={{ background: `repeating-conic-gradient(from ${f * 0.12}deg at 50% 50%, ${p.accent}22 0deg 4deg, transparent 4deg 14deg)` }} />,
        <AbsoluteFill key={key('fade')} style={{ background: `radial-gradient(circle at 50% 50%, transparent 25%, ${p.shadow}AA 100%)` }} />,
      )
    } else if (kit.family === 'western_2d') {
      layers.push(
        <AbsoluteFill key={key('dots')} style={{ backgroundImage: `radial-gradient(${p.primary}66 22%, transparent 24%)`, backgroundSize: `${u * 0.026}px ${u * 0.026}px`, opacity: 0.7 }} />,
        <AbsoluteFill key={key('band')} style={{ background: `linear-gradient(115deg, transparent 55%, ${p.secondary}55 55%, ${p.secondary}55 70%, transparent 70%)` }} />,
      )
    } else if (kit.family === 'cg_3d') {
      layers.push(
        <AbsoluteFill key={key('floor')} style={{ top: '58%', background: `linear-gradient(${p.primary}00, ${p.primary}88)`, borderTop: `2px solid ${p.accent}55`, transform: 'perspective(600px) rotateX(55deg)', transformOrigin: 'top' }}>
          <AbsoluteFill style={{ backgroundImage: `linear-gradient(${p.accent}33 1px, transparent 1px), linear-gradient(90deg, ${p.accent}33 1px, transparent 1px)`, backgroundSize: `${u * 0.06}px ${u * 0.06}px`, backgroundPosition: `${(f * 2) % (u * 0.06)}px 0` }} />
        </AbsoluteFill>,
        <AbsoluteFill key={key('halo')} style={{ background: `radial-gradient(ellipse at 50% 60%, ${p.secondary}44, transparent 55%)` }} />,
      )
    } else if (kit.family === 'stop_motion') {
      const seed = Math.floor(f / Math.max(2, m.step))
      const dots: React.ReactNode[] = []
      for (let i = 0; i < 46; i++) {
        const x = rand(i, 3) * 100
        const y = rand(i, 9) * 100
        const r = 0.3 + rand(i, 21) * 0.9
        dots.push(<div key={i} style={{ position: 'absolute', left: `${x + (rand(seed, i) - 0.5) * 0.4}%`, top: `${y + (rand(seed, i + 50) - 0.5) * 0.4}%`, width: u * r * 0.012, height: u * r * 0.012, borderRadius: '50%', background: i % 3 ? p.highlight : p.secondary, opacity: 0.22 }} />)
      }
      layers.push(<AbsoluteFill key={key('felt')} style={{ background: `radial-gradient(ellipse at 50% 40%, ${mix(p.background, p.primary, 0.35)}, ${p.background})` }} />, <AbsoluteFill key={key('specks')}>{dots}</AbsoluteFill>)
    } else {
      // graphic / flat: big flat shapes of the palette
      layers.push(
        <div key={key('c1')} style={{ position: 'absolute', width: u * 1.1, height: u * 1.1, borderRadius: '50%', background: p.primary, opacity: 0.55, left: width * 0.62, top: -u * 0.35 }} />,
        <div key={key('c2')} style={{ position: 'absolute', width: u * 0.7, height: u * 0.7, borderRadius: '50%', background: p.secondary, opacity: 0.4, left: -u * 0.2, top: height * 0.6 }} />,
      )
    }
    if (kit.animation === 'motion_graphics') {
      layers.push(<AbsoluteFill key={key('grid')} style={{ backgroundImage: `linear-gradient(${p.highlight}14 1px, transparent 1px), linear-gradient(90deg, ${p.highlight}14 1px, transparent 1px)`, backgroundSize: `${u * 0.05}px ${u * 0.05}px` }} />)
    }
    if (kit.animation === 'cutout') {
      layers.push(<AbsoluteFill key={key('paper')} style={{ boxShadow: `inset 0 0 ${u * 0.08}px ${p.shadow}99` }} />)
    }
  }
  return (
    <AbsoluteFill style={{ background: backdrop ? `linear-gradient(160deg, ${p.background} 0%, ${mix(p.background, p.shadow, 0.65)} 100%)` : 'transparent', fontFamily: FONT_STACK, overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: '50% 50%' }}>
        {layers}
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  )
}
