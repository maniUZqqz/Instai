// Explainer: a topic, then one card per step (number, title, a sentence), a progress rail and a closing line.
// The cards enter and leave the way the chosen InstAI style moves (stepped on twos, bouncy, crisp, 3-D tilt ...).
import React from 'react'
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'
import { Stage, useVazirmatn } from '../kit/Stage'
import { enter, leave, motionFor, pose, unrest, type Motion } from '../kit/motion'
import { accentOn, isRtlText, mix, normalizeKit, readableOn, type StyleKit } from '../kit/theme'

export type ExplainerStep = { title: string; body?: string }

export type ExplainerProps = {
  kit: StyleKit
  title: string
  steps: ExplainerStep[]
  outro?: string
  fontBase?: string
}

const INTRO = 60
const STEP = 100
const OUTRO = 70

export function explainerTimeline(p: ExplainerProps, m: Motion): { intro: number; step: number; outro: number; total: number } {
  const n = Math.max(1, (p.steps ?? []).length)
  const extra = m.enterFrames > 24 ? 12 : 0
  return { intro: INTRO, step: STEP + extra, outro: p.outro ? OUTRO : 28, total: INTRO + n * (STEP + extra) + (p.outro ? OUTRO : 28) }
}

export const explainerDuration = (p: ExplainerProps, fps = 30): number => {
  const kit = normalizeKit(p.kit)
  return explainerTimeline(p, motionFor(kit.animation, kit.fps_feel, fps)).total
}

const digits = (n: number, rtl: boolean) => (rtl ? n.toLocaleString('fa-IR') : String(n))

export const Explainer: React.FC<ExplainerProps> = (props) => {
  useVazirmatn(props.fontBase)
  const kit = normalizeKit(props.kit)
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const m = motionFor(kit.animation, kit.fps_feel, fps)
  const u = Math.min(width, height)
  const p = kit.palette
  const steps = props.steps?.length ? props.steps : [{ title: '' }]
  const tl = explainerTimeline(props, m)
  const rtl = isRtlText(props.title + steps.map((s) => s.title + (s.body ?? '')).join(''))
  const color = readableOn(p.background, [p.highlight, '#FFFFFF'])
  const hard = ['western_2d', 'graphic', 'cutout', 'stop_motion'].includes(kit.family)
  const f = pose(frame, m)
  const inSteps = frame >= tl.intro && frame < tl.intro + steps.length * tl.step
  const cur = Math.min(steps.length - 1, Math.max(0, Math.floor((frame - tl.intro) / tl.step)))
  const local = frame - tl.intro - cur * tl.step
  const overall = interpolate(frame, [0, tl.total], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const cardBg = mix(p.background, p.primary, 0.55)
  const onCard = readableOn(cardBg, [p.highlight, '#FFFFFF'])
  const accentCard = accentOn(cardBg, p.accent)
  const accent = accentOn(p.background, p.accent)

  // the topic: big in the intro, then it moves up and becomes the header
  const introT = enter(frame, 6, m, fps)
  const toHeader = interpolate(f, [tl.intro - 14, tl.intro], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const showOutro = frame >= tl.intro + steps.length * tl.step

  return (
    <Stage kit={kit}>
      <AbsoluteFill style={{ direction: rtl ? 'rtl' : 'ltr', padding: u * 0.06 }}>
        {/* header: the topic */}
        <div
          style={{
            position: 'absolute',
            insetInline: u * 0.06,
            top: interpolate(toHeader, [0, 1], [height * 0.4, u * 0.05]),
            textAlign: toHeader > 0.5 ? (rtl ? 'right' : 'left') : 'center',
            color: toHeader > 0.5 ? accent : color,
            fontSize: interpolate(toHeader, [0, 1], [u * 0.09, u * 0.045]),
            fontWeight: 700,
            opacity: Math.min(1, introT * 1.5),
            textShadow: hard ? `${u * 0.005}px ${u * 0.005}px 0 ${p.shadow}` : `0 ${u * 0.005}px ${u * 0.02}px ${p.shadow}`,
          }}
        >
          {props.title}
        </div>

        {/* the rail: one dot per step */}
        {frame >= tl.intro - 6 ? (
          <div style={{ position: 'absolute', insetInlineStart: u * 0.06, top: u * 0.18, display: 'flex', flexDirection: 'column', gap: u * 0.025 }}>
            {steps.map((s, i) => {
              const done = i < cur || showOutro
              const active = i === cur && inSteps
              const t = enter(frame, tl.intro + i * 4, m, fps, 14)
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: u * 0.015, opacity: Math.min(1, t) * (active ? 1 : done ? 0.75 : 0.4) }}>
                  <div style={{ width: u * 0.045, height: u * 0.045, borderRadius: '50%', background: active || done ? accent : 'transparent', border: `${u * 0.004}px solid ${accent}`, color: active || done ? readableOn(accent, ['#000000', '#FFFFFF']) : accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: u * 0.024, fontWeight: 700 }}>{digits(i + 1, rtl)}</div>
                </div>
              )
            })}
          </div>
        ) : null}

        {/* the current step */}
        {inSteps
          ? (() => {
              const s = steps[cur]
              const t = enter(frame, tl.intro + cur * tl.step + 4, m, fps)
              const out = leave(frame, tl.intro + cur * tl.step + tl.step - 14, m, 12)
              const un = unrest(frame, m, cur + 5)
              const tilt = (1 - Math.min(1, t)) * m.tilt3d
              return (
                <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
                  <div
                    style={{
                      width: '66%',
                      background: cardBg,
                      border: `${u * 0.004}px solid ${accentCard}${hard ? '' : '88'}`,
                      borderRadius: hard ? u * 0.012 : u * 0.03,
                      padding: `${u * 0.05}px ${u * 0.055}px`,
                      boxShadow: hard ? `${u * 0.012}px ${u * 0.012}px 0 ${p.shadow}` : `0 ${u * 0.02}px ${u * 0.06}px ${p.shadow}CC`,
                      opacity: Math.min(1, t * 1.6) * (1 - out),
                      transform: `perspective(1000px) rotateY(${(rtl ? -1 : 1) * tilt}deg) rotate(${un.rot}deg) translate(${un.dx + (1 - Math.min(1, t)) * (rtl ? -1 : 1) * u * 0.08}px, ${un.dy}px) scale(${0.9 + 0.1 * Math.min(1.08, t)})`,
                    }}
                  >
                    <div style={{ color: accentCard, fontSize: u * 0.034, fontWeight: 700, marginBottom: u * 0.012 }}>{rtl ? `مرحلهٔ ${digits(cur + 1, true)}` : `Step ${cur + 1}`}</div>
                    <div style={{ color: onCard, fontSize: u * 0.066, fontWeight: 700, lineHeight: 1.3 }}>{s.title}</div>
                    {s.body ? <div style={{ color: readableOn(cardBg, [kit.typography.subtitle_color, p.highlight]), fontSize: u * 0.038, lineHeight: 1.7, marginTop: u * 0.022, opacity: Math.min(1, enter(frame, tl.intro + cur * tl.step + 16, m, fps) * 1.3) }}>{s.body}</div> : null}
                  </div>
                </AbsoluteFill>
              )
            })()
          : null}

        {/* the closing line */}
        {showOutro && props.outro ? (
          <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: u * 0.1 }}>
            <div style={{ color, fontSize: u * 0.07, fontWeight: 700, textAlign: 'center', lineHeight: 1.4, opacity: Math.min(1, enter(frame, tl.intro + steps.length * tl.step + 2, m, fps) * 1.5), transform: `scale(${0.9 + 0.1 * Math.min(1, enter(frame, tl.intro + steps.length * tl.step + 2, m, fps))})`, textShadow: `0 ${u * 0.005}px ${u * 0.02}px ${p.shadow}` }}>{props.outro}</div>
          </AbsoluteFill>
        ) : null}

        {/* the progress bar */}
        <div style={{ position: 'absolute', insetInline: u * 0.06, bottom: u * 0.04, height: u * 0.01, background: `${p.highlight}22`, borderRadius: u }}>
          <div style={{ height: '100%', width: `${overall * 100}%`, background: accent, borderRadius: u, marginInlineStart: 0 }} />
        </div>
      </AbsoluteFill>
    </Stage>
  )
}
