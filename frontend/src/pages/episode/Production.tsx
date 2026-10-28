import { api } from '../../api/client'
import type { Episode, EpisodeEstimate, Job, PageDetail, Shot } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { JobView } from '../../components/domain'
import { Badge, Button, Card, Notice, Progress } from '../../components/ui'
import { useAction } from '../../hooks'
import { useI18n } from '../../i18n'
import { Icon } from '../../components/Icon'

const isActive = (j: Job) => j.status === 'queued' || j.status === 'running'
const EDIT_STATES = ['storyboarding', 'asset_generation', 'quality_review', 'ready_for_approval', 'failed']

export function activeProdJobs(ep: Episode): Job[] {
  return ep.jobs.filter((j) => isActive(j) && j.kind.startsWith('prod.'))
}

/** Estimated GPU time: preview vs final. Always labelled as an estimate and says where the numbers come from. */
export function EstimateCard({ ep, page }: { ep: Episode; page: PageDetail | undefined }) {
  const { t, f } = useI18n()
  const est = ep.estimate as EpisodeEstimate | undefined
  if (!est || !est.modes || !est.shots) return <Notice tone="info">{t('prod.no_estimate')}</Notice>
  const cap = page?.profiles.production.max_gpu_minutes_per_episode as number | undefined
  const finalMin = est.modes.final?.gpu_minutes ?? 0
  const done = ep.jobs.filter((j) => j.kind.startsWith('prod.') && j.status === 'succeeded')
  const doneSec = done.reduce((n, j) => n + (j.duration_sec ?? 0), 0)
  const doneGpu = done.reduce((n, j) => n + (j.gpu_seconds ?? 0), 0)
  const row = (k: 'preview' | 'final') => {
    const m = est.modes[k]
    return m ? (
      <>
        <td>{f.duration(m.gpu_seconds)}</td>
        <td>{f.duration(m.cpu_seconds)}</td>
        <td>{f.duration(m.total_minutes * 60)}</td>
      </>
    ) : (
      <td colSpan={3}>—</td>
    )
  }
  return (
    <Card title={t('prod.estimate_title')} actions={<Badge tone={est.source === 'measured' ? 'ok' : 'warn'}>{est.source === 'measured' ? t('prod.src_measured') : t('prod.src_planning')}</Badge>}>
      <div className="stack-sm">
        <p className="small muted">{est.source === 'measured' ? t('prod.src_measured_note') : t('prod.src_planning_note')}</p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th rowSpan={2}>{t('prod.mode')}</th>
                <th colSpan={3}>{t('prod.estimate_hdr')}</th>
              </tr>
              <tr>
                <th>{t('prod.gpu')}</th>
                <th>{t('prod.cpu')}</th>
                <th>{t('prod.total')}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{t('prod.preview')}</th>
                {row('preview')}
              </tr>
              <tr>
                <th scope="row">{t('prod.final')}</th>
                {row('final')}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="small muted">
          {t('prod.est_shots', { n: est.shots, v: est.video_shots })}
        </div>
        {cap != null && finalMin > cap && <Notice tone="warn">{t('prod.over_cap', { est: f.num(finalMin, 1), cap })}</Notice>}
        {done.length > 0 && (
          <div className="small">
            <strong>{t('prod.measured_runs')}:</strong> {t('prod.measured_line', { n: done.length, d: f.duration(doneSec), g: f.duration(doneGpu) })}
          </div>
        )}
      </div>
    </Card>
  )
}

export function Production({ ep, page, onChanged, onProduced }: { ep: Episode; page: PageDetail | undefined; onChanged: () => void; onProduced: () => void }) {
  const { t, f, tr } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const active = ep.jobs.filter(isActive)
  const shots: Shot[] = ep.scenes.flatMap((s) => s.shots)
  const canProduce = shots.length > 0 && EDIT_STATES.includes(ep.state) && active.filter((j) => j.kind.startsWith('prod.')).length === 0
  const locked = ['approved', 'scheduled', 'published'].includes(ep.state)
  const est = ep.estimate as EpisodeEstimate | undefined
  const stale = ep.stale ?? {}

  const produce = async (mode: 'preview' | 'final') => {
    if (mode === 'final' && est?.modes?.final) {
      const ok = await confirm({ message: t('prod.final_confirm', { g: f.duration(est.modes.final.gpu_seconds) }), confirmLabel: t('prod.make_final') })
      if (!ok) return
    }
    const r = await act.run(() => api.post(`/episodes/${ep.id}/produce`, { mode }), { success: t('prod.started') })
    if (r) {
      onChanged()
      onProduced()
    }
  }
  const cancel = (j: Job) => act.run(async () => { await api.post(`/jobs/${j.id}/cancel`, {}); onChanged() })
  const m = (k: 'keyframes_preview' | 'keyframes_final' | 'narration') => stale[k] ?? 0
  const total = stale.shots ?? shots.length

  return (
    <div className="stack">
      <EstimateCard ep={ep} page={page} />

      <Card title={t('prod.make_title')}>
        <div className="stack">
          {locked ? (
            <Notice tone="info">{t('prod.locked')}</Notice>
          ) : shots.length === 0 ? (
            <Notice tone="info">{t('prod.no_shots')}</Notice>
          ) : (
            <>
              <div className="stack-sm">
                <div className="small">
                  <strong>{t('prod.stale_title')}</strong>
                </div>
                <ul className="small" style={{ margin: 0, paddingInlineStart: '1.25rem' }}>
                  <li>{t('prod.stale_preview', { a: m('keyframes_preview'), b: m('narration'), n: total })}</li>
                  <li>{t('prod.stale_final', { a: m('keyframes_final'), b: m('narration'), n: total })}</li>
                </ul>
                <div className="small muted">{t('prod.stale_note')}</div>
              </div>
              <div className="row">
                <Button variant="primary" icon="play" busy={act.busy} disabled={!canProduce} onClick={() => produce('preview')}>
                  {t('prod.make_preview')}
                </Button>
                <Button icon="film" busy={act.busy} disabled={!canProduce} onClick={() => produce('final')}>
                  {t('prod.make_final')}
                </Button>
              </div>
              {!canProduce && active.length > 0 && <p className="small muted">{t('prod.busy_note')}</p>}
            </>
          )}
        </div>
      </Card>

      <Card title={t('prod.jobs_title')} actions={active.length > 0 ? <Badge tone="info">{t('prod.jobs_active', { n: active.length })}</Badge> : undefined}>
        {ep.jobs.length === 0 ? (
          <p className="muted">{t('prod.no_jobs')}</p>
        ) : (
          <div className="stack-sm" role="log" aria-live="polite">
            {[...ep.jobs].sort((a, b) => Number(isActive(b)) - Number(isActive(a)) || b.id - a.id).slice(0, 8).map((j) => (
              <JobView key={j.id} job={j} compact onCancel={isActive(j) ? () => cancel(j) : undefined} />
            ))}
          </div>
        )}
      </Card>

      <VideoCard ep={ep} />
      <QcCard ep={ep} />

      <Card title={t('prod.assets_title')}>
        {shots.length === 0 ? (
          <p className="muted">{t('prod.no_shots')}</p>
        ) : (
          <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 150px), 1fr))' }}>
            {shots.map((s, i) => (
              <figure key={s.id} style={{ margin: 0 }} className="stack-sm">
                {s.keyframe ? <img className="thumb" src={s.keyframe.url} alt={t('sbd.keyframe_alt', { n: i + 1 })} loading="lazy" /> : <div className="thumb">{t('sbd.no_keyframe')}</div>}
                <figcaption className="small">
                  <span className="strong">{t('sbd.shot_n', { n: i + 1 })}</span> <span className="muted">· {tr('tech.' + s.technique, s.technique)}</span>
                </figcaption>
                {s.narration_asset && <audio controls preload="none" src={s.narration_asset.url} aria-label={t('sbd.audio_alt', { n: i + 1 })} />}
                {s.approved && <Badge tone="ok">{t('sbd.approved')}</Badge>}
              </figure>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

function VideoCard({ ep }: { ep: Episode }) {
  const { t, f } = useI18n()
  if (ep.videos.length === 0) {
    return (
      <Card title={t('prod.video_title')}>
        <p className="muted">{t('prod.no_video')}</p>
      </Card>
    )
  }
  return (
    <Card title={t('prod.video_title')}>
      <div className="stack-lg">
        {ep.videos.map((v) => (
          <div key={v.id} className="video-box">
            <video controls preload="metadata" src={v.url} poster={ep.cover_url ?? undefined} style={v.width && v.height ? { aspectRatio: `${v.width} / ${v.height}` } : undefined} aria-label={t(v.role === 'final' ? 'prod.final' : 'prod.preview')}>
              <track kind="captions" />
            </video>
            <div className="stack-sm grow" style={{ minWidth: 220 }}>
              <div className="row">
                <Badge tone={v.role === 'final' ? 'ok' : 'info'}>{t(v.role === 'final' ? 'prod.final' : 'prod.preview')}</Badge>
                <span className="small muted">{f.dateTime(v.created_at)}</span>
              </div>
              <dl className="kv small">
                <dt>{t('prod.meta_size')}</dt>
                <dd className="ltr">{v.width && v.height ? `${v.width}×${v.height}` : '—'}</dd>
                <dt>{t('prod.meta_fps')}</dt>
                <dd>{f.num(v.fps, 1)}</dd>
                <dt>{t('prod.meta_duration')}</dt>
                <dd>{f.duration(v.duration_sec)}</dd>
                <dt>{t('prod.meta_loudness')}</dt>
                <dd className="ltr">{v.loudness_lufs != null ? `${f.num(v.loudness_lufs, 1)} LUFS` : '—'}</dd>
                <dt>{t('prod.meta_codec')}</dt>
                <dd className="ltr">{v.codec || '—'}</dd>
                <dt>{t('prod.meta_bytes')}</dt>
                <dd>{f.bytes(v.size_bytes)}</dd>
              </dl>
              <a href={v.url} download className="btn sm">
                <Icon name="download" />
                {t('common.download')}
              </a>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function QcCard({ ep }: { ep: Episode }) {
  const { t, tr } = useI18n()
  const checks = ep.qc?.checks ?? []
  if (checks.length === 0) return null
  const icon = { ok: 'check', warn: 'alert', fail: 'close', info: 'info' } as const
  const tone = { ok: 'var(--ok)', warn: 'var(--warn)', fail: 'var(--err)', info: 'var(--info)' } as const
  return (
    <Card title={t('prod.qc_title')} actions={<Badge tone={ep.qc.ok ? 'ok' : 'err'}>{ep.qc.ok ? t('prod.qc_ok') : t('prod.qc_fail')}</Badge>}>
      <ul className="qc-list">
        {checks.map((c, i) => (
          <li key={i}>
            <span style={{ color: tone[c.level] }}>
              <Icon name={icon[c.level]} />
              <span className="sr-only">{tr('qc.level_' + c.level, c.level)}</span>
            </span>
            <span>{c.message}</span>
          </li>
        ))}
      </ul>
      <Progress value={checks.filter((c) => c.level === 'ok').length / checks.length} tone={ep.qc.ok ? 'ok' : 'warn'} label={t('prod.qc_title')} />
    </Card>
  )
}
