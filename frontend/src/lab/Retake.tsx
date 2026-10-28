import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { Job } from '../api/types'
import { JobView } from '../components/domain'
import { useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, LinkButton, Notice, NumberField, PageHead, Segmented, SelectField, AreaField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { AssetLite, EpisodeVideo, VideoRetake } from './api2'
import { EpisodePicker } from './pickers'
import { useL } from './useL'
import './lab.css'

type Mode = 'keep' | 'mute' | 'replace' | 'cut'
const MODES: Mode[] = ['keep', 'mute', 'replace', 'cut']

interface EpisodeLite {
  id: number
  title: string
  number: number
  videos: EpisodeVideo[]
}

function Result({ retake, onChanged }: { retake: VideoRetake; onChanged: () => void }) {
  const { s, f } = useL()
  const act = useAction()
  const confirm = useConfirm()
  const source = useQuery<AssetLite>(`/assets/${retake.source_asset}`)
  const [side, setSide] = useState<'after' | 'before'>('after')
  const v = retake.seam.verify
  const url = side === 'after' ? retake.result?.url : source.data?.url
  const revert = async () => {
    if (!(await confirm({ title: s('rt.revert'), message: s('rt.revert_confirm'), confirmLabel: s('rt.revert') }))) return
    await act.run(async () => { await api.post(`/video-retakes/${retake.id}/revert`, {}); onChanged() }, { success: s('rt.reverted') })
  }
  return (
    <div className="stack-sm" data-testid="retake-result">
      <div className="row between">
        <Segmented
          label={s('rt.compare_toggle')}
          value={side}
          onChange={setSide}
          options={[{ key: 'before', label: s('rt.before') }, { key: 'after', label: s('rt.after') }]}
        />
        <Button size="sm" icon="refresh" busy={act.busy} onClick={revert} data-testid="retake-revert">{s('rt.revert')}</Button>
      </div>
      {url && <video className="lab-retake-video" key={url} src={url} controls playsInline preload="metadata" data-testid={`retake-${side}-video`} aria-label={side === 'after' ? s('rt.after') : s('rt.before')} />}
      <div className="grid-auto lab-facts">
        {v && (
          <>
            <div><span className="small muted">{s('rt.verify')}</span><div><Badge tone={v.ok ? 'ok' : 'err'}>{v.ok ? s('rt.verify_ok') : s('rt.verify_bad')}</Badge></div></div>
            <div data-testid="retake-duration-error"><span className="small muted">{s('rt.duration_error')}</span><div className="strong ltr">{f.num(v.duration_error, 3)} s</div></div>
            <div><span className="small muted">{s('rt.frames')}</span><div className="strong ltr">{f.num(v.frames)} / {f.num(v.expected_frames)}</div></div>
            <div><span className="small muted">{s('rt.size_fps')}</span><div className="strong ltr">{v.size} · {f.num(v.fps, 1)} fps</div></div>
            <div><span className="small muted">{s('rt.audio')}</span><div className="strong">{v.has_audio ? s('common.yes') : s('common.no')}</div></div>
          </>
        )}
        {retake.seam.seam && (
          <div data-testid="retake-seams">
            <span className="small muted">{s('rt.seam')}</span>
            <div className="strong ltr">
              {retake.seam.seam.start !== undefined && `${s('rt.seam_start')} ${f.num(retake.seam.seam.start, 2)}`}
              {retake.seam.seam.end !== undefined && ` · ${s('rt.seam_end')} ${f.num(retake.seam.seam.end, 2)}`}
            </div>
          </div>
        )}
        {retake.seam.colour && (
          <div><span className="small muted">{s('rt.colour')}</span><div className="strong ltr">{f.num(retake.seam.colour.before, 1)} → {f.num(retake.seam.colour.after, 1)}</div></div>
        )}
        {retake.seam.device && <div><span className="small muted">{s('rt.device')}</span><div className="strong ltr">{retake.seam.device}</div></div>}
      </div>
      <p className="small muted">{s('rt.seam_hint')}</p>
    </div>
  )
}

/** Retake panel of ONE episode: pick a time range of the rendered video, regenerate / mute / replace / cut it, compare and revert. */
export function RetakePanel({ episodeId }: { episodeId: number }) {
  const { s, f } = useL()
  const ep = useQuery<EpisodeLite>(`/episodes/${episodeId}`)
  const retakes = useQuery<VideoRetake[]>(`/episodes/${episodeId}/video-retakes`, { interval: (d) => (d && d.some((r) => r.status === 'queued' || r.status === 'running') ? 3000 : false) })
  const audios = useQuery<AssetLite[]>(`/assets?episode=${episodeId}&kind=audio&current=1`)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [start, setStart] = useState<number | null>(1)
  const [end, setEnd] = useState<number | null>(2.5)
  const [mode, setMode] = useState<Mode>('keep')
  const [prompt, setPrompt] = useState('')
  const [audioAsset, setAudioAsset] = useState('')
  const [shown, setShown] = useState<number | null>(null)
  const runner = useJobRunner({ onFinished: () => { retakes.reload(); ep.reload() } })
  const video = ep.data?.videos.find((x) => x.role === 'final') ?? ep.data?.videos[0]
  const dur = video?.duration_sec ?? 0
  const len = start !== null && end !== null ? end - start : 0
  const generated = mode !== 'cut'
  let problem = ''
  if (start === null || end === null || end <= start) problem = s('rt.err_order')
  else if (generated && len < 0.4) problem = s('rt.err_short')
  else if (generated && len > 10) problem = s('rt.err_long')
  else if (generated && (start < 0.1 || (dur && end > dur - 0.1))) problem = s('rt.err_edge')
  else if (dur && start >= dur) problem = s('rt.err_outside')
  else if (mode === 'replace' && !audioAsset) problem = s('rt.err_audio')
  const takeTime = (which: 'start' | 'end') => {
    const t = Math.round((videoRef.current?.currentTime ?? 0) * 10) / 10
    if (which === 'start') setStart(t)
    else setEnd(t)
  }
  const submit = () =>
    runner.start(async () => {
      const r = await api.post<{ job: Job; retake: VideoRetake }>(`/episodes/${episodeId}/video-retakes`, {
        start_sec: start, end_sec: end, prompt: mode === 'cut' ? '' : prompt, audio_mode: mode, ...(mode === 'replace' ? { audio_asset: Number(audioAsset) } : {}),
      })
      setShown(r.retake.id)
      return r
    })
  return (
    <div className="stack-lg" data-testid="retake-panel">
      <Async q={ep} skeleton={<CardSkeletons n={2} />}>
        {() =>
          !video ? (
            <Empty icon="film" title={s('rt.no_video')} text={s('rt.no_video_text')} action={<LinkButton to={`/episodes/${episodeId}`} icon="film">{s('rt.open_episode')}</LinkButton>} />
          ) : (
            <Card title={s('rt.source')}>
              <div className="stack-sm">
                <p className="small muted">{s('rt.explain')}</p>
                <div className="row">
                  <Badge tone={video.role === 'final' ? 'ok' : 'info'}>{video.role === 'final' ? s('rt.final') : s('rt.preview')}</Badge>
                  <span className="small muted ltr">{video.width}×{video.height} · {f.num(dur, 1)} s</span>
                </div>
                <video ref={videoRef} className="lab-retake-video" src={video.url} controls playsInline preload="metadata" data-testid="retake-video" aria-label={s('rt.source')} />
                <div className="grid-2">
                  <div className="stack-sm">
                    <NumberField label={s('rt.start')} value={start} onChange={setStart} min={0} step={0.1} data-testid="retake-start" />
                    <Button size="sm" onClick={() => takeTime('start')}>{s('rt.use_now_start')}</Button>
                  </div>
                  <div className="stack-sm">
                    <NumberField label={s('rt.end')} value={end} onChange={setEnd} min={0} step={0.1} data-testid="retake-end" />
                    <Button size="sm" onClick={() => takeTime('end')}>{s('rt.use_now_end')}</Button>
                  </div>
                </div>
                <div className="stack-sm">
                  <span className="field-label">{s('rt.audio_mode')}</span>
                  <div role="radiogroup" aria-label={s('rt.audio_mode')} className="lab-modes">
                    {MODES.map((m) => (
                      <label key={m} className={'choice' + (mode === m ? ' selected' : '')}>
                        <input type="radio" name="retake-mode" value={m} checked={mode === m} onChange={() => setMode(m)} data-testid={`retake-mode-${m}`} />
                        <span className="strong">{s(`rt.mode_${m}` as 'rt.mode_keep')}</span>
                        <span className="small muted">{s(`rt.mode_${m}_text` as 'rt.mode_keep_text')}</span>
                      </label>
                    ))}
                  </div>
                </div>
                {mode === 'replace' && (
                  <SelectField
                    label={s('rt.audio_asset')}
                    value={audioAsset}
                    onChange={setAudioAsset}
                    options={[{ value: '', label: s('rt.pick_audio') }, ...(audios.data ?? []).map((a) => ({ value: String(a.id), label: `#${a.id} · ${a.role} · ${f.num(a.duration_sec ?? 0, 1)} s` }))]}
                    hint={(audios.data ?? []).length === 0 ? s('rt.no_audio') : undefined}
                    data-testid="retake-audio-asset"
                  />
                )}
                {generated && <AreaField label={s('rt.prompt')} hint={s('rt.prompt_hint')} value={prompt} onChange={setPrompt} compact />}
                {mode === 'cut' && <Notice tone="info">{s('rt.cut_note')}</Notice>}
                {problem && <Notice tone="warn" role="status">{problem}</Notice>}
                <div className="row">
                  <Button variant="primary" icon="play" busy={runner.busy} disabled={!!problem} onClick={submit} data-testid="retake-submit">{s('rt.submit')}</Button>
                  {!problem && <span className="small muted">{s('rt.range_len', { n: f.num(len, 1) })}</span>}
                </div>
                {runner.job && <JobView job={runner.job} offline={runner.offline} />}
              </div>
            </Card>
          )
        }
      </Async>

      <Card title={s('rt.history')}>
        <Async q={retakes} skeleton={<CardSkeletons n={1} />}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="muted">{s('rt.history_empty')}</p>
            ) : (
              <div className="stack-sm">
                <ul className="lab-history" data-testid="retake-history">
                  {rows.map((r) => (
                    <li key={r.id} className="row between" data-testid={`retake-history-${r.id}`}>
                      <span className="ltr">#{r.id} · {f.num(r.start_sec, 1)}–{f.num(r.end_sec, 1)} s · {s(`rt.mode_${r.audio_mode}` as 'rt.mode_keep')}</span>
                      <span className="row">
                        <Badge tone={r.status === 'done' ? 'ok' : r.status === 'failed' ? 'err' : 'info'}>{s(`rt.st_${r.status}` as 'rt.st_done')}</Badge>
                        {r.status === 'done' && <Button size="sm" variant="ghost" onClick={() => setShown(r.id)}>{s('rt.show')}</Button>}
                      </span>
                    </li>
                  ))}
                </ul>
                {(() => {
                  const cur = rows.find((r) => r.id === shown) ?? rows.find((r) => r.status === 'done')
                  if (!cur) return null
                  if (cur.status === 'failed') return <Notice tone="err">{cur.error}</Notice>
                  return cur.result ? <Result key={cur.id} retake={cur} onChanged={() => { retakes.reload(); ep.reload() }} /> : null
                })()}
                {rows.some((r) => r.status === 'failed') && <Notice tone="err">{rows.find((r) => r.status === 'failed')!.error}</Notice>}
              </div>
            )
          }
        </Async>
      </Card>
    </div>
  )
}

export default function Retake() {
  const { s } = useL()
  useTitle(s('title.retake'))
  return (
    <div className="stack-lg">
      <PageHead title={s('title.retake')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.retake') }]} />
      <p className="muted">{s('rt.intro')}</p>
      <EpisodePicker>{(_page, ep) => <RetakePanel key={ep.id} episodeId={ep.id} />}</EpisodePicker>
    </div>
  )
}
