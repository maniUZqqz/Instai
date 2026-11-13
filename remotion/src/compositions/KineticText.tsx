// Kinetic text: a script shown a few words at a time. Words enter one after another (the beat is the style's own), *starred* words are
// emphasised in the accent colour, and each line leaves before the next one comes. Works right to left (Persian) and left to right.
import React from 'react'
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion'
import { Stage, useVazirmatn } from '../kit/Stage'
import { enter, leave, motionFor, unrest, type Motion } from '../kit/motion'
import { accentOn, isRtlText, normalizeKit, readableOn, type StyleKit } from '../kit/theme'

export type KineticTextProps = {
  kit: StyleKit
  /** one entry per screen of text; wrap words in *stars* to emphasise them */
  lines: string[]
  fontBase?: string
}

type Word = { text: string; emphasis: boolean }

export function parseLine(line: string): Word[] {
  const out: Word[] = []
  let emphasis = false
  for (const raw of line.split(/\s+/)) {
    if (!raw) continue
    let w = raw
    let startEmph = false
    let endEmph = false
    if (w.startsWith('*')) {
      startEmph = true
      w = w.slice(1)
    }
    if (w.endsWith('*')) {
      endEmph = true
      w = w.slice(0, -1)
    }
    if (startEmph) emphasis = true
    if (w) out.push({ text: w, emphasis })
    if (endEmph) emphasis = false
  }
  return out
}

const HOLD = 34

/** Start frame and length of every line, and the whole clip's length. */
export function kineticTimeline(lines: string[], m: Motion): { starts: number[]; lengths: number[]; total: number } {
  const starts: number[] = []
  const lengths: number[] = []
  let at = 6
  for (const l of lines) {
    const n = Math.max(1, parseLine(l).length)
    const len = m.enterFrames + n * m.stagger + HOLD
    starts.push(at)
    lengths.push(len)
    at += len
  }
  return { starts, lengths, total: at + 10 }
}

export const kineticDuration = (p: KineticTextProps, fps = 30): number => {
  const kit = normalizeKit(p.kit)
  return kineticTimeline(p.lines?.length ? p.lines : [''], motionFor(kit.animation, kit.fps_feel, fps)).total
}

export const KineticText: React.FC<KineticTextProps> = (props) => {
  useVazirmatn(props.fontBase)
  const kit = normalizeKit(props.kit)
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const m = motionFor(kit.animation, kit.fps_feel, fps)
  const u = Math.min(width, height)
  const p = kit.palette
  const lines = props.lines?.length ? props.lines : ['']
  const tl = kineticTimeline(lines, m)
  const color = readableOn(p.background, [p.highlight, '#FFFFFF'])
  const accent = accentOn(p.background, p.accent)
  let idx = 0
  tl.starts.forEach((s, i) => {
    if (frame >= s) idx = i
  })
  const words = parseLine(lines[idx])
  const rtl = isRtlText(lines[idx])
  const start = tl.starts[idx]
  const len = tl.lengths[idx]
  const exit = leave(frame, start + len - 14, m, 12)
  const fontSize = Math.max(u * 0.055, Math.min(u * 0.12, (u * 0.17) / Math.max(1, Math.sqrt(words.length))))
  const hard = ['western_2d', 'graphic', 'cutout', 'stop_motion'].includes(kit.family)

  return (
    <Stage kit={kit}>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: u * 0.08, direction: rtl ? 'rtl' : 'ltr' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'baseline', columnGap: fontSize * 0.32, rowGap: fontSize * 0.18, maxWidth: '88%', opacity: 1 - exit, transform: `translateY(${-exit * u * 0.03}px)` }}>
          {words.map((w, i) => {
            const t = enter(frame, start + i * m.stagger, m, fps)
            const un = unrest(frame, m, i + idx * 11)
            const sz = w.emphasis ? fontSize * 1.22 : fontSize
            const rise = (1 - Math.min(1, t)) * fontSize * 0.7
            const col = w.emphasis ? accent : color
            return (
              <span
                key={i}
                style={{
                  display: 'inline-block',
                  position: 'relative',
                  fontSize: sz,
                  fontWeight: w.emphasis ? 700 : kit.typography.title_weight === 'regular' ? 400 : 700,
                  color: col,
                  opacity: Math.min(1, t * 1.8),
                  transform: `translate(${un.dx}px, ${rise + un.dy}px) rotate(${un.rot + (1 - Math.min(1, t)) * (rtl ? 4 : -4)}deg) scale(${0.6 + 0.4 * t})`,
                  textShadow: hard ? `${u * 0.005}px ${u * 0.005}px 0 ${p.shadow}` : `0 ${u * 0.005}px ${u * 0.02}px ${p.shadow}`,
                  lineHeight: 1.3,
                }}
              >
                {w.text}
                {w.emphasis ? <span style={{ position: 'absolute', insetInlineStart: 0, bottom: -sz * 0.05, height: sz * 0.07, width: `${Math.min(1, enter(frame, start + i * m.stagger + 8, m, fps)) * 100}%`, background: accent, borderRadius: sz }} /> : null}
              </span>
            )
          })}
        </div>
      </AbsoluteFill>
    </Stage>
  )
}
