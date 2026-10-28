import { useState } from 'react'
import { api } from '../api/client'
import type { Job } from '../api/types'
import { JobView } from '../components/domain'
import { useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Notice, NumberField, PageHead } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { EpisodeBrief, LoraRow, ShotRenderRow } from './api2'
import { EpisodeForPage } from './pickers'
import { PageCharacterPicker } from './shared'
import { useL } from './useL'
import './lab.css'

function LoraCard({ lora, onChanged }: { lora: LoraRow; onChanged: () => void }) {
  const { s, f } = useL()
  const act = useAction()
  const b = lora.before.similarity
  const a = lora.after.similarity
  const delta = lora.after.delta
  const approve = (approved: boolean) => act.run(async () => { await api.patch(`/loras/${lora.id}`, { approved }); onChanged() })
  return (
    <li className="card flat stack-sm" data-testid={`lora-${lora.id}`}>
      <div className="row between">
        <span className="ltr strong">#{lora.id} {lora.lora_file}</span>
        <Badge tone={lora.status === 'trained' ? 'ok' : lora.status === 'failed' ? 'err' : 'info'}><span data-testid={`lora-status-${lora.id}`}>{s(`cs.st_${lora.status}` as 'cs.st_trained')}</span></Badge>
      </div>
      <div className="small muted ltr">steps {lora.params.steps ?? '—'} · rank {lora.params.rank ?? '—'}{lora.params.images ? ` · ${lora.params.images} img` : ''}{lora.seconds ? ` · ${f.duration(lora.seconds)}` : ''}</div>
      {lora.status === 'trained' && (
        <div className="grid-auto lab-facts" data-testid={`lora-numbers-${lora.id}`}>
          <div><span className="small muted">{s('cs.before')}</span><div className="strong ltr">{b === null || b === undefined ? '—' : f.num(b, 3)}</div></div>
          <div><span className="small muted">{s('cs.after')}</span><div className="strong ltr">{a === null || a === undefined ? '—' : f.num(a, 3)}</div></div>
          <div><span className="small muted">{s('cs.delta')}</span><div className="strong ltr">{delta === null || delta === undefined ? '—' : (delta > 0 ? '+' : '') + f.num(delta, 3)}</div></div>
          <div><span className="small muted">{s('cs.verdict')}</span><div><Badge tone={lora.after.helped ? 'ok' : 'warn'}>{lora.after.helped ? s('cs.helped') : s('cs.not_helped')}</Badge></div></div>
        </div>
      )}
      {lora.status === 'trained' && <p className="small muted">{s('cs.weak_metric')}</p>}
      {lora.error && <Notice tone="err" role="alert">{lora.error}</Notice>}
      {lora.status === 'trained' && (
        <div className="row">
          <Badge tone={lora.approved ? 'ok' : 'neutral'}>{lora.approved ? s('cs.approved') : s('cs.not_approved')}</Badge>
          <Button size="sm" variant={lora.approved ? 'default' : 'primary'} icon="check" busy={act.busy} onClick={() => approve(!lora.approved)} data-testid={`lora-approve-${lora.id}`}>
            {lora.approved ? s('cs.unapprove') : s('cs.approve')}
          </Button>
        </div>
      )}
    </li>
  )
}

function LoraPanel({ characterId }: { characterId: number }) {
  const { s } = useL()
  const confirm = useConfirm()
  const list = useQuery<LoraRow[]>(`/characters/${characterId}/loras`, { interval: (d) => (d && d.some((l) => l.status === 'queued' || l.status === 'training') ? 4000 : false) })
  const [steps, setSteps] = useState<number | null>(300)
  const [rank, setRank] = useState<number | null>(16)
  const runner = useJobRunner({ onFinished: () => list.reload() })
  const start = async () => {
    if (!(await confirm({ title: s('cs.train'), message: s('cs.train_confirm'), confirmLabel: s('cs.train') }))) return
    await runner.start(async () => api.post<{ job: Job }>(`/characters/${characterId}/loras`, { steps: steps ?? 300, rank: rank ?? 16 }))
    list.reload()
  }
  return (
    <Card title={s('cs.lora_title')}>
      <div className="stack-sm" data-testid="lora-panel">
        <Notice tone="warn" icon="alert">{s('cs.lora_warning')}</Notice>
        <p className="small muted">{s('cs.lora_how')}</p>
        <div className="grid-2">
          <NumberField label={s('cs.steps')} value={steps} onChange={setSteps} min={10} max={4000} step={10} data-testid="lora-steps" />
          <NumberField label={s('cs.rank')} value={rank} onChange={setRank} min={1} max={128} step={1} data-testid="lora-rank" />
        </div>
        <div className="row"><Button variant="primary" icon="play" busy={runner.busy} onClick={start} data-testid="lora-train">{s('cs.train')}</Button></div>
        {runner.job && <JobView job={runner.job} offline={runner.offline} />}
        <Async q={list} skeleton={<CardSkeletons n={1} />}>
          {(rows) => (rows.length === 0 ? <p className="muted" data-testid="lora-empty">{s('cs.lora_none')}</p> : <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>{rows.map((l) => <LoraCard key={l.id + l.status} lora={l} onChanged={list.reload} />)}</ul>)}
        </Async>
      </div>
    </Card>
  )
}

function RendersTable({ episode }: { episode: EpisodeBrief }) {
  const { s, f } = useL()
  const q = useQuery<ShotRenderRow[]>(`/episodes/${episode.id}/renders`)
  return (
    <Card title={s('cs.renders_title')}>
      <div className="stack-sm" data-testid="renders-panel">
        <p className="small muted">{s('cs.renders_hint')}</p>
        <Async q={q} skeleton={<CardSkeletons n={1} />}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty icon="film" title={s('cs.renders_none')} text={s('cs.renders_none_text')} />
            ) : (
              <div className="table-wrap">
                <table className="table" data-testid="renders-table">
                  <thead>
                    <tr>
                      <th>{s('cs.col_shot')}</th><th>{s('cs.col_technique')}</th><th>{s('cs.col_device')}</th><th>{s('cs.col_seconds')}</th><th>{s('cs.col_drift')}</th><th>{s('cs.col_sheet')}</th><th>{s('cs.col_ok')}</th><th>{s('cs.col_notes')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} data-testid={`render-${r.id}`}>
                        <td className="ltr">#{r.shot}</td>
                        <td className="ltr">{r.technique}</td>
                        <td className="ltr">{r.device || '—'}</td>
                        <td className="nowrap">{r.seconds ? f.duration(r.seconds) : '—'}</td>
                        <td className="ltr">{r.qc.drift === null || r.qc.drift === undefined ? '—' : f.num(r.qc.drift, 3)}</td>
                        <td className="ltr">{r.qc.sheet === null || r.qc.sheet === undefined ? '—' : f.num(r.qc.sheet, 3)}</td>
                        <td>{r.status === 'failed' ? <Badge tone="err">{s('cs.failed')}</Badge> : r.qc.ok === undefined ? <span className="muted">—</span> : <Badge tone={r.qc.ok ? 'ok' : 'warn'}>{r.qc.ok ? s('cs.ok') : s('cs.check')}</Badge>}</td>
                        <td className="small">{[...(r.qc.notes ?? []), r.error].filter(Boolean).join(' · ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
        <p className="small muted">{s('cs.threshold_note')}</p>
      </div>
    </Card>
  )
}

export default function Consistency() {
  const { s } = useL()
  useTitle(s('title.consistency'))
  return (
    <div className="stack-lg">
      <PageHead title={s('title.consistency')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.consistency') }]} />
      <p className="muted">{s('cs.intro')}</p>
      <PageCharacterPicker>
        {(p) => (
          <div className="stack-lg">
            <LoraPanel key={p.characterId} characterId={p.characterId!} />
            <EpisodeForPage page={p.page!}>{(_page, ep) => <RendersTable key={ep.id} episode={ep} />}</EpisodeForPage>
          </div>
        )}
      </PageCharacterPicker>
    </div>
  )
}
