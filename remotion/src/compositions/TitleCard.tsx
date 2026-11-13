// Title card: a kicker, a big title, an accent bar and a subtitle, moving the way the chosen InstAI style moves.
// The entrance (none / fade / pop / slide / typewriter) comes from the style's theme (typography.title_animation) unless `animation` says otherwise.
import React from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { Stage, useVazirmatn } from '../kit/Stage'
import { enter, leave, motionFor, pose, unrest } from '../kit/motion'
import { WEIGHT, accentOn, applyCase, isRtlText, normalizeKit, readableOn, type StyleKit } from '../kit/theme'

export type TitleCardProps = {
  kit: StyleKit
  title: string
  subtitle?: string
  kicker?: string
  /** 'auto' = the style's own title animation */
  animation?: 'auto' | 'none' | 'fade' | 'pop' | 'slide' | 'typewriter'
  fontBase?: string
}

export const titleCardDuration = (_p: TitleCardProps, fps = 30): number => Math.round(fps * 5)

export const TitleCard: React.FC<TitleCardProps> = (props) => {
  useVazirmatn(props.fontBase)
  const kit = normalizeKit(props.kit)
  const frame = useCurrentFrame()
  const { fps, width, height, durationInFrames } = useVideoConfig()
  const m = motionFor(kit.animation, kit.fps_feel, fps)
  const u = Math.min(width, height)
  const p = kit.palette
  const anim = props.animation && props.animation !== 'auto' ? props.animation : kit.typography.title_animation
  const rtl = isRtlText(props.title + (props.subtitle ?? ''))
  const text = applyCase(props.title || '', kit.typography.title_case)
  const color = readableOn(p.background, [p.highlight, '#FFFFFF'])
  const accent = accentOn(p.background, p.accent)
  const subColor = readableOn(p.background, [kit.typography.subtitle_color, p.highlight])
  const hard = ['western_2d', 'graphic', 'cutout', 'stop_motion'].includes(kit.family)

  const start = 8
  const t = enter(frame, start, m, fps)
  const out = leave(frame, durationInFrames - 16, m, 14)
  const alive = 1 - out

  // typewriter reveals words for right-to-left script (letters of a cursive script must stay joined) and letters otherwise
  const tokens = rtl ? text.split(/(\s+)/) : Array.from(text)
  const count = tokens.length
  const reveal = anim === 'typewriter' ? Math.floor(interpolate(pose(frame, m), [start, start + Math.max(18, count * (rtl ? 6 : 2))], [0, count], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })) : count
  const shown = anim === 'typewriter' ? tokens.slice(0, reveal).join('') : text

  const un = unrest(frame, m, 3)
  const size = Math.max(u * 0.05, Math.min(u * 0.115, u * 0.115 * Math.min(1, 16 / Math.max(10, text.length))))
  let opacity = 1
  let scale = 1
  let ty = 0
  if (anim === 'fade') opacity = Math.min(1, t)
  if (anim === 'pop') {
    opacity = Math.min(1, t * 2)
    scale = 0.55 + 0.45 * t
  }
  if (anim === 'slide') {
    opacity = Math.min(1, t * 1.5)
    ty = (1 - t) * u * 0.07
  }
  const tilt = (1 - Math.min(1, t)) * m.tilt3d

  const shadow = hard ? `${u * 0.006}px ${u * 0.006}px 0 ${p.shadow}` : `0 ${u * 0.006}px ${u * 0.025}px ${p.shadow}`
  const bar = enter(frame, start + 14, m, fps)
  const sub = enter(frame, start + 22, m, fps)

  return (
    <Stage kit={kit}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: u * 0.08, direction: rtl ? 'rtl' : 'ltr', textAlign: 'center' }}>
        <div style={{ maxWidth: '86%', opacity: alive, transform: `perspective(900px) rotateX(${tilt}deg) rotate(${un.rot}deg) translate(${un.dx}px, ${un.dy + ty}px) scale(${scale})` }}>
          {props.kicker ? (
            <div style={{ color: accent, fontSize: u * 0.028, fontWeight: 700, letterSpacing: rtl ? 0 : u * 0.004, marginBottom: u * 0.02, opacity: Math.min(1, enter(frame, start - 2, m, fps) * 1.4) }}>{applyCase(props.kicker, kit.typography.title_case)}</div>
          ) : null}
          <div style={{ color, fontSize: size, fontWeight: WEIGHT[kit.typography.title_weight], lineHeight: 1.25, opacity, textShadow: shadow, WebkitTextStroke: kit.typography.title_weight === 'black' ? `${u * 0.0016}px ${color}` : undefined }}>
            {shown}
            {anim === 'typewriter' && reveal < count ? <span style={{ color: accent }}>{rtl ? '' : '|'}</span> : null}
          </div>
          <div style={{ height: u * 0.012, width: `${Math.min(1, bar) * 34}%`, margin: `${u * 0.03}px auto`, background: accent, borderRadius: u * 0.01, boxShadow: hard ? 'none' : `0 0 ${u * 0.02}px ${accent}88` }} />
          {props.subtitle ? <div style={{ color: subColor, fontSize: u * 0.04, fontWeight: 400, lineHeight: 1.6, opacity: Math.min(1, sub * 1.3), transform: `translateY(${(1 - Math.min(1, sub)) * u * 0.02}px)`, textShadow: `0 ${u * 0.003}px ${u * 0.012}px ${p.shadow}` }}>{props.subtitle}</div> : null}
        </div>
      </AbsoluteFill>
    </Stage>
  )
}
