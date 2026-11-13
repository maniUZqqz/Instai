// Lower third: the name and role of a speaker, a bar that slides in over the bottom of the picture and leaves again.
// `backdrop: false` leaves the background empty (for an overlay that is placed over a video elsewhere).
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'
import { Stage, useVazirmatn } from '../kit/Stage'
import { enter, leave, motionFor, unrest } from '../kit/motion'
import { accentOn, isRtlText, mix, normalizeKit, readableOn, type StyleKit } from '../kit/theme'

export type LowerThirdProps = {
  kit: StyleKit
  name: string
  role?: string
  backdrop?: boolean
  fontBase?: string
}

export const lowerThirdDuration = (_p: LowerThirdProps, fps = 30): number => Math.round(fps * 5)

export const LowerThird: React.FC<LowerThirdProps> = (props) => {
  useVazirmatn(props.fontBase)
  const kit = normalizeKit(props.kit)
  const frame = useCurrentFrame()
  const { fps, width, height, durationInFrames } = useVideoConfig()
  const m = motionFor(kit.animation, kit.fps_feel, fps)
  const u = Math.min(width, height)
  const p = kit.palette
  const rtl = isRtlText(props.name + (props.role ?? ''))
  const hard = ['western_2d', 'graphic', 'cutout', 'stop_motion'].includes(kit.family)
  const bar = enter(frame, 6, m, fps, m.enterFrames + 6)
  const text = enter(frame, 16, m, fps)
  const role = enter(frame, 26, m, fps)
  const out = leave(frame, durationInFrames - 22, m, 16)
  const un = unrest(frame, m, 9)
  const panel = mix(p.background, p.primary, 0.7)
  const onPanel = readableOn(panel, [p.highlight, '#FFFFFF'])
  const accentPanel = accentOn(panel, p.accent)
  const side = rtl ? -1 : 1
  const slide = (1 - Math.min(1, bar)) * width * 0.4 * -side + out * width * 0.4 * -side

  return (
    <Stage kit={kit} backdrop={props.backdrop !== false} zoom={false}>
      <AbsoluteFill style={{ direction: rtl ? 'rtl' : 'ltr', justifyContent: 'flex-end', padding: `${u * 0.08}px ${u * 0.07}px` }}>
        <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'stretch', transform: `translate(${slide + un.dx}px, ${un.dy}px) rotate(${un.rot}deg)`, opacity: Math.min(1, bar * 2) * (1 - out * 0.4) }}>
          <div style={{ width: u * 0.018, background: p.accent, borderRadius: hard ? 0 : u }} />
          <div style={{ background: panel, padding: `${u * 0.022}px ${u * 0.04}px`, borderRadius: hard ? 0 : rtl ? `${u * 0.018}px 0 0 ${u * 0.018}px` : `0 ${u * 0.018}px ${u * 0.018}px 0`, boxShadow: hard ? `${u * 0.008}px ${u * 0.008}px 0 ${p.shadow}` : `0 ${u * 0.012}px ${u * 0.04}px ${p.shadow}AA`, minWidth: u * 0.4 }}>
            <div style={{ color: onPanel, fontSize: u * 0.058, fontWeight: 700, lineHeight: 1.3, opacity: Math.min(1, text * 1.6), transform: `translateX(${(1 - Math.min(1, text)) * -side * u * 0.03}px)` }}>{props.name}</div>
            {props.role ? <div style={{ color: accentPanel, fontSize: u * 0.034, fontWeight: 400, lineHeight: 1.5, marginTop: u * 0.004, opacity: Math.min(1, role * 1.6) }}>{props.role}</div> : null}
          </div>
        </div>
      </AbsoluteFill>
    </Stage>
  )
}
