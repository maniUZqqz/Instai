import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Job } from '../api/types'
import { JobView } from '../components/domain'
import { Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, Notice, PageHead, SelectField, TextField, AreaField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { PageLite } from './api'
import type { AnimeCandidate, CompareClip, Comparison, EpisodeBrief, ProductionConfig } from './api2'
import { PagePicker } from './pickers'
import { licenceTone } from './shared'
import { useL } from './useL'
import './lab.css'

function Candidates({ list }: { list: AnimeCandidate[] }) {
  const { s, f } = useL()
  return (
    <ul className="grid-auto lab-candidates" aria-label={s('cp.candidates')}>
      {list.map((c) => (
        <li key={c.id} className="card flat stack-sm" data-testid={`candidate-${c.id}`}>
          <div className="row between">
            <span className="strong">{c.label}</span>
            <Badge tone={c.available ? 'ok' : 'neutral'}>{c.available ? s('cp.available') : s('cp.unavailable')}</Badge>
          </div>
          <div className="row">
            <Badge tone={licenceTone(c.commercial)}>{c.commercial === 'yes' ? s('cp.comm_yes') : c.commercial === 'no' ? s('cp.comm_no') : s('cp.comm_unknown')}</Badge>
            <Badge tone="warn">{s('cp.not_verified')}</Badge>
          </div>
          <p className="small">{c.licence}</p>
          <p className="small muted">{c.note}</p>
          {c.needs.length > 0 && (
            <div className="small">
              {s('cp.needs')}: <span className="ltr strong">{c.needs.join(', ')}</span>
            </div>
          )}
          {!c.available && c.missing.length > 0 && (
            <details>
              <summary className="small" style={{ cursor: 'pointer' }}>{s('cp.missing', { n: c.missing.length })}</summary>
              <ul className="small ltr" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.1rem' }}>
                {c.missing.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </details>
          )}
          {!c.available && c.missing.length === 0 && <p className="small muted">{s('cp.install_hint', { pack: c.pack })}</p>}
          <p className="small muted" data-testid={`candidate-est-${c.id}`}>
            {s('cp.expected', { time: f.duration(c.expected_seconds) })} · <em>{s('cp.estimate')}</em>
          </p>
        </li>
      ))}
    </ul>
  )
}

function ClipCell({ clip }: { clip: CompareClip | undefined }) {
  const { s, f } = useL()
  if (!clip) return <span className="muted">—</span>
  if (clip.status === 'done' && clip.url) {
    return (
      <div className="stack-sm">
        <video className="lab-compare-video" src={clip.url} controls loop muted playsInline preload="metadata" aria-label={`${clip.candidate} #${clip.seed}`} />
        <span className="small muted">{clip.seconds ? f.duration(clip.seconds) : ''} {clip.device ? `· ${clip.device}` : ''}</span>
      </div>
    )
  }
  return (
    <div className="stack-sm">
      <Badge tone={clip.status === 'failed' ? 'err' : clip.status === 'skipped' ? 'warn' : 'neutral'}>{s(`cp.clip_${clip.status}` as 'cp.clip_done')}</Badge>
      {clip.error && <span className="small muted" data-testid="clip-reason">{clip.error}</span>}
    </div>
  )
}

function Grid({ cmp, candidates, onVoted }: { cmp: Comparison; candidates: AnimeCandidate[]; onVoted: () => void }) {
  const { s } = useL()
  const act = useAction()
  const clips = cmp.clips ?? []
  const labels = Object.fromEntries(candidates.map((c) => [c.id, c.label]))
  const keys = Array.from(new Set(clips.map((c) => `${c.still_index}:${c.seed}`)))
  const vote = (candidate: string) =>
    act.run(
      async () => {
        const r = await api.post<{ winner: string; page_default: string | null; counts: Record<string, number> }>(`/comparisons/${cmp.id}/vote`, { candidate })
        onVoted()
        return r
      },
      { success: s('cp.voted', { model: labels[candidate] ?? candidate }) },
    )
  const doneBy = (cand: string) => clips.some((c) => c.candidate === cand && c.status === 'done')
  return (
    <div className="table-wrap">
      <table className="table lab-compare-table" data-testid="compare-grid">
        <thead>
          <tr>
            <th>{s('cp.still_seed')}</th>
            {cmp.candidates.map((cand) => (
              <th key={cand}>
                <div className="stack-sm">
                  <span>{labels[cand] ?? cand}</span>
                  <div className="row">
                    <Badge tone={cmp.winner === cand ? 'ok' : 'neutral'}>{s('cp.votes', { n: cmp.counts[cand] ?? 0 })}</Badge>
                    {cmp.winner === cand && <Badge tone="ok">{s('cp.leading')}</Badge>}
                  </div>
                  <Button size="sm" variant="primary" icon="check" busy={act.busy} disabled={!doneBy(cand)} onClick={() => vote(cand)} data-testid={`vote-${cand}`}>
                    {s('cp.vote')}
                  </Button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const [si, seed] = k.split(':').map(Number)
            const still = cmp.stills[si]
            return (
              <tr key={k}>
                <td>
                  <div className="stack-sm">
                    {still && <img className="lab-still" src={still.url} alt={s('cp.still_n', { n: si + 1 })} loading="lazy" />}
                    <span className="small ltr">{s('cp.still_n', { n: si + 1 })} · seed {seed}</span>
                  </div>
                </td>
                {cmp.candidates.map((cand) => (
                  <td key={cand} data-testid={`cell-${si}-${seed}-${cand}`}>
                    <ClipCell clip={clips.find((c) => c.still_index === si && c.seed === seed && c.candidate === cand)} />
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CreateForm({ page, candidates, onCreated }: { page: PageLite; candidates: AnimeCandidate[]; onCreated: (c: Comparison, job: Job | undefined) => void }) {
  const { s } = useL()
  const eps = useQuery<EpisodeBrief[]>(`/pages/${page.id}/episodes`)
  const [episode, setEpisode] = useState('')
  const [seeds, setSeeds] = useState('11, 12')
  const [prompt, setPrompt] = useState('')
  const [picked, setPicked] = useState<string[]>(candidates.map((c) => c.id))
  const runner = useJobRunner<Record<string, unknown>>()
  const epId = Number(episode) || eps.data?.[0]?.id
  const stills = useQuery<{ id: number }[]>(epId ? `/assets?episode=${epId}&role=keyframe&kind=image&current=1` : null)
  const noStills = !!stills.data && stills.data.length === 0
  const parsed = seeds.split(/[\s,،]+/).map((x) => Number(x)).filter((n) => Number.isInteger(n) && n >= 0).slice(0, 4)
  const start = () =>
    runner.start(async () => {
      const r = await api.post<{ job: Job; comparison: Comparison }>('/comparisons', { episode: epId, page: page.id, seeds: parsed, candidates: picked, prompt })
      onCreated(r.comparison, r.job)
      return r
    })
  return (
    <Card title={s('cp.new')}>
      <div className="stack-sm">
        <p className="small muted">{s('cp.new_hint')}</p>
        {eps.data && eps.data.length === 0 ? (
          <Notice tone="info">{s('pick.no_episodes_text')}</Notice>
        ) : (
          <SelectField
            label={s('pick.episode')}
            value={String(epId ?? '')}
            onChange={setEpisode}
            options={(eps.data ?? []).map((e) => ({ value: String(e.id), label: `${e.series_title} · ${e.number}. ${e.title}` }))}
            data-testid="compare-episode"
          />
        )}
        {noStills && <Notice tone="warn" icon="alert" role="status">{s('cp.no_stills')}</Notice>}
        <TextField label={s('cp.seeds')} hint={s('cp.seeds_hint')} value={seeds} onChange={setSeeds} ltr data-testid="compare-seeds" />
        <fieldset className="lab-fieldset">
          <legend className="field-label">{s('cp.pick_models')}</legend>
          <div className="stack-sm">
            {candidates.map((c) => (
              <CheckField key={c.id} label={c.label} hint={c.available ? undefined : s('cp.will_skip')} checked={picked.includes(c.id)} onChange={(v) => setPicked(v ? [...picked, c.id] : picked.filter((x) => x !== c.id))} />
            ))}
          </div>
        </fieldset>
        <AreaField label={s('cp.prompt')} hint={s('cp.prompt_hint')} value={prompt} onChange={setPrompt} compact />
        <div className="row">
          <Button variant="primary" icon="play" busy={runner.busy} disabled={!epId || noStills || picked.length === 0 || parsed.length === 0} onClick={start} data-testid="compare-create">
            {s('cp.start')}
          </Button>
        </div>
        {runner.job && <JobView job={runner.job} offline={runner.offline} />}
      </div>
    </Card>
  )
}

function PageCompare({ page, candidates }: { page: PageLite; candidates: AnimeCandidate[] }) {
  const { s, f } = useL()
  const act = useAction()
  const [params, setParams] = useSearchParams()
  const cfg = useQuery<ProductionConfig>(`/pages/${page.id}/production-config`)
  const list = useQuery<Comparison[]>(`/comparisons?page=${page.id}`)
  const want = Number(params.get('comparison')) || null
  const current = list.data?.find((c) => c.id === want) ?? list.data?.[0] ?? null
  const detail = useQuery<Comparison>(current ? `/comparisons/${current.id}` : null, { interval: (d) => (d && d.status !== 'done' ? 2500 : false) })
  const rerun = useJobRunner({ onFinished: () => { detail.reload(); list.reload() } })
  const setDefault = (model: string) =>
    act.run(async () => {
      await api.put(`/pages/${page.id}/production-config`, { anime_model: model })
      cfg.reload()
    }, { success: s('cp.default_saved') })
  const reload = () => { detail.reload(); list.reload(); cfg.reload() }
  const labels = Object.fromEntries(candidates.map((c) => [c.id, c.label]))
  return (
    <div className="stack-lg">
      <Card title={s('cp.default_title')}>
        <div className="stack-sm" data-testid="compare-default">
          <p className="small muted">{s('cp.default_hint')}</p>
          <Async q={cfg} skeleton={<CardSkeletons n={1} />}>
            {(c) => (
              <div className="row">
                <SelectField label={s('cp.default_model')} value={c.anime_model} onChange={setDefault} options={candidates.map((x) => ({ value: x.id, label: x.label }))} disabled={act.busy} data-testid="compare-default-select" />
                <Badge tone="ok">{labels[c.anime_model] ?? c.anime_model}</Badge>
              </div>
            )}
          </Async>
        </div>
      </Card>

      <CreateForm
        page={page}
        candidates={candidates}
        onCreated={(c) => {
          const p = new URLSearchParams(params)
          p.set('comparison', String(c.id))
          setParams(p, { replace: true })
          list.reload()
        }}
      />

      <Card title={s('cp.results')}>
        <Async q={list} skeleton={<CardSkeletons n={1} />}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty icon="layers" title={s('cp.none')} text={s('cp.none_text')} />
            ) : (
              <div className="stack-lg">
                <SelectField
                  label={s('cp.pick_comparison')}
                  value={String(current?.id ?? '')}
                  onChange={(v) => { const p = new URLSearchParams(params); p.set('comparison', v); setParams(p, { replace: true }) }}
                  options={rows.map((r) => ({ value: String(r.id), label: `#${r.id} · ${f.dateTime(r.created_at)} · ${r.status}` }))}
                  data-testid="compare-pick"
                />
                {detail.data && (
                  <div className="stack-sm" data-testid="compare-detail">
                    <div className="row between">
                      <span className="small muted">{detail.data.prompt || s('cp.default_prompt')}</span>
                      <div className="row">
                        <Badge tone={detail.data.status === 'done' ? 'ok' : 'info'}>{detail.data.status}</Badge>
                        <Button size="sm" icon="refresh" busy={rerun.busy} onClick={() => rerun.start(async () => api.post<{ job: Job }>(`/comparisons/${detail.data!.id}/run`, {}))} data-testid="compare-run-again">
                          {s('cp.run_again')}
                        </Button>
                      </div>
                    </div>
                    {rerun.job && <JobView job={rerun.job} offline={rerun.offline} />}
                    {detail.data.winner && <Notice tone="ok" icon="check">{s('cp.leading_note', { model: labels[detail.data.winner] ?? detail.data.winner })}</Notice>}
                    <Grid cmp={detail.data} candidates={candidates} onVoted={reload} />
                  </div>
                )}
              </div>
            )
          }
        </Async>
      </Card>
    </div>
  )
}

export default function Compare() {
  const { s } = useL()
  useTitle(s('title.compare'))
  const cands = useQuery<AnimeCandidate[]>('/anime/candidates')
  return (
    <div className="stack-lg">
      <PageHead title={s('title.compare')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.compare') }]} />
      <p className="muted">{s('cp.intro')}</p>
      <Notice tone="warn">{s('cp.licence_note')}</Notice>
      <Async q={cands} skeleton={<CardSkeletons n={2} />}>
        {(list) => (
          <>
            <Card title={s('cp.candidates')}>
              <Candidates list={list} />
            </Card>
            <PagePicker>{(page) => <PageCompare page={page} candidates={list} />}</PagePicker>
          </>
        )}
      </Async>
    </div>
  )
}
