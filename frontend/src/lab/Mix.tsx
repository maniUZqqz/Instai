import { useState } from 'react'
import { api } from '../api/client'
import type { Job } from '../api/types'
import { JobView } from '../components/domain'
import { useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Notice, NumberField, PageHead, SelectField, SwitchField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { MixTrackRow } from './api2'
import { EpisodePicker } from './pickers'
import { useL } from './useL'
import './lab.css'

interface MixPayload {
  tracks: MixTrackRow[]
  engines: { music: string; sfx: string }
}

type Draft = Partial<Pick<MixTrackRow, 'prompt' | 'gain_db' | 'start_sec' | 'end_sec' | 'duck'>>

function TrackRow({ track, onChanged }: { track: MixTrackRow; onChanged: () => void }) {
  const { s } = useL()
  const act = useAction()
  const confirm = useConfirm()
  const [draft, setDraft] = useState<Draft>({})
  const val = <K extends keyof Draft>(k: K): Draft[K] => (k in draft ? draft[k] : (track[k] as Draft[K]))
  const dirty = Object.keys(draft).length > 0
  const save = () =>
    act.run(async () => { await api.patch(`/mix-tracks/${track.id}`, draft); setDraft({}); onChanged() }, { success: s('mx.saved') })
  const remove = async () => {
    if (!(await confirm({ title: s('mx.delete'), message: s('mx.delete_confirm', { name: track.label }), confirmLabel: s('mx.delete'), danger: true }))) return
    await act.run(async () => { await api.del(`/mix-tracks/${track.id}`); onChanged() })
  }
  return (
    <li className="card flat stack-sm" data-testid={`track-${track.id}`}>
      <div className="row between">
        <span className="row">
          <Badge tone="primary">{s(`mx.kind_${track.kind}` as 'mx.kind_music')}</Badge>
          <span className="strong">{track.label}</span>
        </span>
        <Badge tone={track.status === 'ready' ? 'ok' : track.status === 'failed' ? 'err' : track.status === 'generating' ? 'info' : 'neutral'}>
          <span data-testid={`track-status-${track.id}`}>{s(`mx.st_${track.status}` as 'mx.st_ready')}</span>
        </Badge>
      </div>
      <TextField label={s('mx.prompt')} hint={s('mx.prompt_hint')} value={val('prompt') ?? ''} onChange={(v) => setDraft({ ...draft, prompt: v })} ltr />
      <div className="grid-auto lab-numbers">
        <NumberField label={s('mx.gain')} value={val('gain_db') ?? 0} onChange={(v) => setDraft({ ...draft, gain_db: v ?? 0 })} min={-60} max={12} step={1} />
        <NumberField label={s('mx.start')} value={val('start_sec') ?? 0} onChange={(v) => setDraft({ ...draft, start_sec: v ?? 0 })} min={0} step={0.1} />
        <NumberField label={s('mx.end')} hint={s('mx.end_hint')} value={val('end_sec') ?? null} onChange={(v) => setDraft({ ...draft, end_sec: v })} min={0} step={0.1} />
      </div>
      <SwitchField label={s('mx.duck')} hint={s('mx.duck_hint')} checked={!!val('duck')} onChange={(v) => setDraft({ ...draft, duck: v })} />
      {track.error && <Notice tone="err">{track.error}</Notice>}
      {track.asset && <audio controls preload="none" src={track.asset.url} aria-label={track.label} data-testid={`track-audio-${track.id}`} />}
      <div className="row">
        <Button size="sm" variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{s('common.save')}</Button>
        <Button size="sm" variant="danger" icon="trash" busy={act.busy} onClick={remove}>{s('mx.delete')}</Button>
      </div>
    </li>
  )
}

function AddTrack({ episodeId, onAdded }: { episodeId: number; onAdded: () => void }) {
  const { s } = useL()
  const act = useAction()
  const [kind, setKind] = useState('music')
  const [prompt, setPrompt] = useState('')
  const [gain, setGain] = useState<number | null>(-20)
  const [start, setStart] = useState<number | null>(0)
  const add = () =>
    act.run(async () => {
      await api.post(`/episodes/${episodeId}/mix`, { kind, prompt, label: prompt.slice(0, 60), gain_db: gain ?? -18, start_sec: start ?? 0 })
      setPrompt('')
      onAdded()
    }, { success: s('mx.added') })
  return (
    <div className="stack-sm" data-testid="mix-add">
      <SelectField label={s('mx.kind')} value={kind} onChange={setKind} options={[{ value: 'music', label: s('mx.kind_music') }, { value: 'ambience', label: s('mx.kind_ambience') }, { value: 'sfx', label: s('mx.kind_sfx') }]} data-testid="mix-add-kind" />
      <TextField label={s('mx.prompt')} hint={s('mx.prompt_hint')} value={prompt} onChange={setPrompt} ltr data-testid="mix-add-prompt" />
      <div className="grid-2">
        <NumberField label={s('mx.gain')} value={gain} onChange={setGain} min={-60} max={12} step={1} />
        <NumberField label={s('mx.start')} value={start} onChange={setStart} min={0} step={0.1} />
      </div>
      <div className="row">
        <Button icon="plus" busy={act.busy} disabled={!prompt.trim()} onClick={add} data-testid="mix-add-submit">{s('mx.add')}</Button>
      </div>
    </div>
  )
}

export function MixPanel({ episodeId }: { episodeId: number }) {
  const { s } = useL()
  const act = useAction()
  const mix = useQuery<MixPayload>(`/episodes/${episodeId}/mix`, { interval: (d) => (d && d.tracks.some((t) => t.status === 'generating') ? 2500 : false) })
  const runner = useJobRunner({ onFinished: () => mix.reload() })
  const plan = () => act.run(async () => { await api.post(`/episodes/${episodeId}/mix/plan`, {}); mix.reload() }, { success: s('mx.planned') })
  const generate = () => runner.start(async () => api.post<{ job: Job }>(`/episodes/${episodeId}/mix/generate`, {}))
  return (
    <div className="stack-lg" data-testid="mix-panel">
      <Card title={s('mx.how')}>
        <div className="stack-sm">
          <p className="small">{s('mx.how_text')}</p>
          <p className="small muted">{s('mx.worker_note')}</p>
        </div>
      </Card>
      <Async q={mix} skeleton={<CardSkeletons n={2} />}>
        {(m) => {
          const pending = m.tracks.filter((t) => t.status === 'planned' || t.status === 'failed').length
          return (
            <>
              <div className="row">
                <Button icon="list" busy={act.busy} onClick={plan} data-testid="mix-plan">{s('mx.plan')}</Button>
                <Button variant="primary" icon="play" busy={runner.busy} disabled={pending === 0} onClick={generate} data-testid="mix-generate">{s('mx.generate', { n: pending })}</Button>
                <span className="small muted">{s('mx.engines', { music: m.engines.music, sfx: m.engines.sfx })}</span>
              </div>
              {runner.job && <JobView job={runner.job} offline={runner.offline} />}
              {m.tracks.length === 0 ? (
                <Empty icon="play" title={s('mx.empty')} text={s('mx.empty_text')} />
              ) : (
                <ul className="stack-sm lab-tracks" data-testid="mix-tracks" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                  {m.tracks.map((t) => <TrackRow key={t.id + ':' + t.status + ':' + (t.asset?.id ?? 0)} track={t} onChanged={mix.reload} />)}
                </ul>
              )}
            </>
          )
        }}
      </Async>
      <Card title={s('mx.add_title')}>
        <AddTrack episodeId={episodeId} onAdded={mix.reload} />
      </Card>
    </div>
  )
}

export default function Mix() {
  const { s } = useL()
  useTitle(s('title.mix'))
  return (
    <div className="stack-lg">
      <PageHead title={s('title.mix')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.mix') }]} />
      <p className="muted">{s('mx.intro')}</p>
      <EpisodePicker>{(_page, ep) => <MixPanel key={ep.id} episodeId={ep.id} />}</EpisodePicker>
    </div>
  )
}
