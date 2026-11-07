import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { JobLogLine } from '../api/types'
import { Modal, useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, Empty, Link, Notice, PageHead, Progress, Tabs, type Tone } from '../components/ui'
import { useAction, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import type { NodeBrief, QueueData, QueueRow, QueueState } from './types'

export const STATE_TONE: Record<string, Tone> = {
  running: 'info',
  waiting_gpu: 'warn',
  waiting_node: 'warn',
  waiting_service: 'warn',
  retry: 'warn',
  waiting_turn: 'neutral',
  window: 'primary',
  scheduled: 'primary',
  succeeded: 'ok',
  failed: 'err',
  cancelled: 'neutral',
}

const STATE_KEY = 'ops.state.'

export function StateBadge({ state }: { state: QueueState | string }) {
  const { tr } = useI18n()
  return <Badge tone={STATE_TONE[state] ?? 'neutral'}>{tr(STATE_KEY + state, state)}</Badge>
}

export function useNodeName() {
  const { lang } = useI18n()
  return (n: NodeBrief) => (lang === 'en' ? n.name_en : n.name)
}

/** The computers: this PC and every paired PC, online or not. */
function Computers({ nodes }: { nodes: NodeBrief[] }) {
  const { t, f } = useI18n()
  const name = useNodeName()
  return (
    <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 260px), 1fr))' }}>
      {nodes.map((n) => (
        <div key={n.key} className="card flat stack-sm" data-testid={'node-' + n.key}>
          <div className="row between">
            <span className="strong">{name(n)}</span>
            <Badge tone={n.online ? 'ok' : n.enabled ? 'err' : 'neutral'}>{n.online ? t('ops.node.online') : n.enabled ? t('ops.node.offline') : t('ops.node.disabled')}</Badge>
          </div>
          <div className="small muted">{n.last_seen ? t('ops.node.last_seen', { when: f.ago(n.last_seen) }) : t('ops.node.never')}</div>
        </div>
      ))}
    </div>
  )
}

export function JobLogsModal({ job, onClose }: { job: { id: number; title: string }; onClose: () => void }) {
  const { t, f } = useI18n()
  const [lines, setLines] = useState<JobLogLine[]>([])
  const last = useRef(0)
  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const tick = async () => {
      try {
        const more = await api.get<JobLogLine[]>(`/jobs/${job.id}/logs?after=${last.current}`)
        if (alive && more.length) {
          last.current = more[more.length - 1].id
          setLines((l) => [...l, ...more])
        }
      } catch {
        /* the next tick tries again */
      }
      if (alive) timer = window.setTimeout(tick, 2500)
    }
    tick()
    return () => {
      alive = false
      if (timer) window.clearTimeout(timer)
    }
  }, [job.id])
  return (
    <Modal title={t('mon.logs_of', { title: job.title })} onClose={onClose} wide>
      <div className="log-view mono" role="log" tabIndex={0} aria-label={t('mon.logs')}>
        {lines.length === 0 ? <span style={{ opacity: 0.7 }}>{t('mon.logs_empty')}</span> : lines.map((l) => (
          <div key={l.id} className={'log-line lvl-' + l.level}>
            <span style={{ opacity: 0.6 }}>{f.time(l.at)}</span> {l.message}
          </div>
        ))}
      </div>
    </Modal>
  )
}

/** One row of the queue: what it is, the plain state (why it waits), where, how many tries, and what can be done. */
function Row({ r, onChanged, onLogs, finished }: { r: QueueRow; onChanged: () => void; onLogs: () => void; finished?: boolean }) {
  const { t, lang, f } = useI18n()
  const confirm = useConfirm()
  const act = useAction()
  const title = lang === 'en' ? r.title_en : r.title_fa
  const forText = lang === 'en' ? r.for_en : r.for_fa
  const stateText = lang === 'en' ? r.state_en : r.state_fa
  const ex = r.explain
  const cancel = async () => {
    if (!(await confirm({ message: t('ops.q.cancel_ask', { title }), confirmLabel: t('ops.q.cancel'), danger: true }))) return
    await act.run(() => api.post(`/jobs/${r.id}/cancel`, {}), { success: t('mon.cancel_sent') })
    onChanged()
  }
  const retry = async () => {
    await act.run(() => api.post(`/jobs/${r.id}/retry`, {}), { success: t('mon.retried') })
    onChanged()
  }
  const runNow = async () => {
    await act.run(() => api.post(`/jobs/${r.id}/run-now`, {}), { success: t('ops.q.started_now') })
    onChanged()
  }
  return (
    <tr data-testid={'job-' + r.id} className={'q-' + r.state}>
      <td>
        <div className="strong" dir="auto">{title}</div>
        {forText && <div className="small muted" dir="auto">{forText}</div>}
        <div className="small muted ltr">{r.kind} · #{r.id}</div>
      </td>
      <td>
        <StateBadge state={r.state} />
        <div className="small" style={{ marginBlockStart: '0.25rem' }} dir="auto">{stateText}</div>
        {r.state === 'running' && <Progress value={r.progress} indeterminate={r.progress <= 0} label={title} />}
        {finished && ex && (
          <div className="small" style={{ color: 'var(--err)', marginBlockStart: '0.25rem' }} dir="auto">
            {lang === 'en' ? ex.what_en : ex.what_fa}
            <div className="muted">{lang === 'en' ? ex.advice_en : ex.advice_fa}</div>
          </div>
        )}
        {!finished && r.waiting_reason && ['waiting_node', 'waiting_service', 'waiting_gpu'].includes(r.state) && (
          <div className="small muted" dir="auto">{lang === 'en' ? '' : r.waiting_reason}</div>
        )}
      </td>
      <td className="nowrap small">{r.node === 'local' ? t('ops.node.local_short') : r.node}</td>
      <td className="nowrap small">
        {t('ops.q.tries', { a: r.attempts, b: r.max_attempts })}
        {r.deferrals > 0 && <div className="muted">{t('ops.q.waited_n', { n: r.deferrals })}</div>}
      </td>
      <td className="nowrap small muted">
        {finished ? (
          <>
            {f.ago(r.finished_at)}
            {r.duration_sec != null && <div>{f.duration(r.duration_sec)}</div>}
          </>
        ) : (
          <>
            {f.ago(r.created_at)}
            {r.waiting_since && <div>{t('ops.q.waiting_since', { when: f.ago(r.waiting_since) })}</div>}
          </>
        )}
      </td>
      <td>
        <div className="row" style={{ gap: '0.25rem' }}>
          {r.can_cancel && <Button size="sm" variant="danger" icon="stop" busy={act.busy} onClick={cancel}>{t('ops.q.cancel')}</Button>}
          {r.can_retry && <Button size="sm" icon="refresh" busy={act.busy} onClick={retry}>{t('mon.retry')}</Button>}
          {r.can_run_now && <Button size="sm" icon="play" busy={act.busy} onClick={runNow}>{t('ops.q.run_now')}</Button>}
          <Button size="sm" variant="ghost" icon="list" onClick={onLogs}>{t('mon.logs')}</Button>
        </div>
      </td>
    </tr>
  )
}

function Table({ rows, onChanged, onLogs, finished }: { rows: QueueRow[]; onChanged: () => void; onLogs: (r: QueueRow) => void; finished?: boolean }) {
  const { t } = useI18n()
  return (
    <div className="table-wrap">
      <table className="table q-table">
        <thead>
          <tr>
            <th>{t('mon.col_job')}</th>
            <th>{t('eps.col_state')}</th>
            <th>{t('ops.q.col_node')}</th>
            <th>{t('ops.q.col_tries')}</th>
            <th>{finished ? t('mon.col_when') : t('ops.q.col_age')}</th>
            <th>{t('mon.col_actions')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => <Row key={r.id} r={r} finished={finished} onChanged={onChanged} onLogs={() => onLogs(r)} />)}
        </tbody>
      </table>
    </div>
  )
}

type Tab = 'active' | 'done' | 'problem'

/** «صفِ پردازش»: every job that waits or runs, with the reason it waits. Waiting is not failing. */
export default function QueuePage() {
  const { t, lang } = useI18n()
  useTitle(t('ops.q.title'))
  const q = useQuery<QueueData>('/queue', { interval: 3000 })
  const [tab, setTab] = useState<Tab>('active')
  const [logs, setLogs] = useState<{ id: number; title: string } | null>(null)
  const onLogs = (r: QueueRow) => setLogs({ id: r.id, title: lang === 'en' ? r.title_en : r.title_fa })
  return (
    <div className="stack-lg">
      <PageHead title={t('ops.q.title')}>
        <Link to="/report" className="btn">{t('ops.q.to_report')}</Link>
        <Link to="/downloads" className="btn">{t('ops.q.to_downloads')}</Link>
        <Button icon="refresh" onClick={q.reload}>{t('common.refresh')}</Button>
      </PageHead>
      <Notice tone="info" icon="clock">{t('ops.q.intro')}</Notice>
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(d) => {
          const s = d.summary
          const done = d.recent.filter((r) => r.status === 'succeeded')
          const problem = d.recent.filter((r) => r.status !== 'succeeded')
          const offlineWorkers = d.nodes.filter((n) => n.kind === 'worker' && n.enabled && !n.online)
          return (
            <>
              <Computers nodes={d.nodes} />
              {s.waiting_node > 0 && offlineWorkers.length > 0 && <Notice tone="warn" icon="alert">{t('ops.q.waiting_for_pc', { n: s.waiting_node })}</Notice>}
              <div className="grid-auto q-counters" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                <Counter n={s.running} label={t('ops.state.running')} tone="info" />
                <Counter n={s.waiting_node} label={t('ops.q.c_node')} tone="warn" />
                <Counter n={s.waiting_service} label={t('ops.q.c_service')} tone="warn" />
                <Counter n={s.waiting_turn} label={t('ops.state.waiting_turn')} tone="neutral" />
                <Counter n={s.scheduled} label={t('ops.q.c_scheduled')} tone="primary" />
              </div>
              <Card>
                <Tabs<Tab>
                  label={t('ops.q.title')}
                  value={tab}
                  onChange={setTab}
                  tabs={[
                    { key: 'active', label: t('ops.q.tab_active'), badge: <Badge tone="info">{d.active.length}</Badge> },
                    { key: 'done', label: t('ops.q.tab_done'), badge: <Badge>{done.length}</Badge> },
                    { key: 'problem', label: t('ops.q.tab_problem'), badge: <Badge tone={problem.length ? 'err' : 'neutral'}>{problem.length}</Badge> },
                  ]}
                />
                {tab === 'active' && (d.active.length === 0 ? <Empty icon="check" title={t('ops.q.empty')} /> : <Table rows={d.active} onChanged={q.reload} onLogs={onLogs} />)}
                {tab === 'done' && (done.length === 0 ? <Empty icon="list" title={t('mon.recent_empty')} /> : <Table rows={done} finished onChanged={q.reload} onLogs={onLogs} />)}
                {tab === 'problem' && (problem.length === 0 ? <Empty icon="check" title={t('ops.q.no_problem')} /> : <Table rows={problem} finished onChanged={q.reload} onLogs={onLogs} />)}
              </Card>
            </>
          )
        }}
      </Async>
      {logs && <JobLogsModal job={logs} onClose={() => setLogs(null)} />}
    </div>
  )
}

function Counter({ n, label, tone }: { n: number; label: string; tone: Tone }) {
  const { f } = useI18n()
  return (
    <div className={'card flat q-counter ' + tone}>
      <div className="q-counter-n">{f.num(n)}</div>
      <div className="small muted">{label}</div>
    </div>
  )
}
