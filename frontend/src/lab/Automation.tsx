import { useState } from 'react'
import { api } from '../api/client'
import type { Job } from '../api/types'
import { JobView } from '../components/domain'
import { useConfirm } from '../components/feedback'
import { Async, Badge, Button, Card, CardSkeletons, ChoiceGrid, Empty, Link, Notice, NumberField, PageHead, Progress, SelectField, SwitchField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { PageLite } from './api'
import type { AutomationInfo, PublicationRow, PublishTargetRow, RenderWindow, ScheduleInfo } from './api2'
import { PagePicker } from './pickers'
import { useL } from './useL'
import './lab.css'

const DAYS = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'] as const
type Level = 'manual' | 'assisted' | 'automatic'
const LEVELS: Level[] = ['manual', 'assisted', 'automatic']

function Meter({ label, used, budget, unit, testid }: { label: string; used: number; budget: number; unit: string; testid: string }) {
  const { s, f } = useL()
  const frac = budget > 0 ? used / budget : 0
  return (
    <div className="stack-sm" data-testid={testid}>
      <div className="row between">
        <span className="strong">{label}</span>
        <span className="small ltr">{f.num(used, 1)} {unit} / {budget > 0 ? `${f.num(budget, budget % 1 ? 2 : 0)} ${unit}` : s('au.unlimited')}</span>
      </div>
      <Progress value={budget > 0 ? frac : 0} tone={frac >= 1 ? 'err' : frac >= 0.8 ? 'warn' : 'ok'} label={label} />
    </div>
  )
}

function Levels({ info, onChanged }: { info: AutomationInfo; onChanged: () => void }) {
  const { s } = useL()
  const act = useAction()
  const set = (level: Level) => act.run(async () => { await api.put(`/pages/${info.page}/automation`, { level }); onChanged() }, { success: s('au.level_saved') })
  return (
    <Card title={s('au.level_title')}>
      <div className="stack-sm" data-testid="au-levels">
        <ChoiceGrid<Level>
          legend={s('au.level_legend')}
          name="automation-level"
          value={info.level}
          onChange={set}
          options={LEVELS.map((l) => ({
            value: l,
            title: s(`au.level_${l}` as 'au.level_manual'),
            text: s(`au.level_${l}_text` as 'au.level_manual_text'),
          }))}
        />
        <p className="small muted">{s('au.level_never')}</p>
      </div>
    </Card>
  )
}

function Budgets({ info, onChanged }: { info: AutomationInfo; onChanged: () => void }) {
  const { s } = useL()
  const act = useAction()
  const [gpu, setGpu] = useState<number | null>(info.gpu_minutes_per_week)
  const [api$, setApi] = useState<number | null>(info.api_usd_per_week)
  const save = () => act.run(async () => { await api.put(`/pages/${info.page}/automation`, { gpu_minutes_per_week: gpu ?? 0, api_usd_per_week: api$ ?? 0 }); onChanged() }, { success: s('au.budget_saved') })
  return (
    <Card title={s('au.budget_title')}>
      <div className="stack-sm">
        <p className="small muted">{s('au.budget_hint')}</p>
        <Meter label={s('au.gpu_minutes')} used={info.usage.gpu_minutes} budget={info.usage.gpu_budget} unit={s('au.unit_min')} testid="meter-gpu" />
        <Meter label={s('au.api_usd')} used={info.usage.api_usd} budget={info.usage.api_budget} unit="$" testid="meter-api" />
        <div className="grid-2">
          <NumberField label={s('au.gpu_budget')} hint={s('au.zero_unlimited')} value={gpu} onChange={setGpu} min={0} step={10} data-testid="budget-gpu" />
          <NumberField label={s('au.api_budget')} hint={s('au.zero_unlimited')} value={api$} onChange={setApi} min={0} step={0.5} data-testid="budget-api" />
        </div>
        <div className="row"><Button variant="primary" icon="save" busy={act.busy} onClick={save} data-testid="budget-save">{s('common.save')}</Button></div>
      </div>
    </Card>
  )
}

function Windows({ info, onChanged }: { info: AutomationInfo; onChanged: () => void }) {
  const { s, f } = useL()
  const act = useAction()
  const [rows, setRows] = useState<RenderWindow[]>(info.render_windows)
  const [offset, setOffset] = useState<number | null>(info.utc_offset_minutes)
  const patch = (i: number, p: Partial<RenderWindow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...p } : r)))
  const toggle = (i: number, d: string) => patch(i, { days: rows[i].days.includes(d) ? rows[i].days.filter((x) => x !== d) : [...rows[i].days, d] })
  const save = () => act.run(async () => { await api.put(`/pages/${info.page}/automation`, { render_windows: rows, utc_offset_minutes: offset ?? 0 }); onChanged() }, { success: s('au.windows_saved') })
  return (
    <Card title={s('au.windows_title')}>
      <div className="stack-sm">
        <p className="small muted">{s('au.windows_hint')}</p>
        <div className="row">
          <Badge tone={info.window_open_now ? 'ok' : 'warn'}><span data-testid="window-state">{info.window_open_now ? s('au.window_open') : s('au.window_closed')}</span></Badge>
          {!info.window_open_now && <span className="small">{s('au.next_window', { when: f.dateTime(info.next_window) })}</span>}
        </div>
        {rows.length === 0 && <p className="small muted">{s('au.windows_none')}</p>}
        <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }} data-testid="windows">
          {rows.map((w, i) => (
            <li key={i} className="card flat stack-sm" data-testid={`window-${i}`}>
              <fieldset className="lab-fieldset">
                <legend className="field-label">{s('au.window_days')}</legend>
                <div className="row">
                  {DAYS.map((d) => (
                    <label key={d} className={'chip lab-day' + (w.days.includes(d) ? ' on' : '')}>
                      <input type="checkbox" checked={w.days.includes(d)} onChange={() => toggle(i, d)} aria-label={s(`day.${d}` as 'day.mon')} />
                      {s(`day.${d}` as 'day.mon')}
                    </label>
                  ))}
                </div>
                <span className="field-hint">{s('au.window_days_hint')}</span>
              </fieldset>
              <div className="grid-2">
                <TextField label={s('au.window_start')} value={w.start} onChange={(v) => patch(i, { start: v })} type="time" ltr data-testid={`window-start-${i}`} />
                <TextField label={s('au.window_end')} value={w.end} onChange={(v) => patch(i, { end: v })} type="time" ltr data-testid={`window-end-${i}`} />
              </div>
              <div className="row"><Button size="sm" variant="danger" icon="trash" onClick={() => setRows(rows.filter((_, j) => j !== i))}>{s('au.window_remove')}</Button></div>
            </li>
          ))}
        </ul>
        <div className="row">
          <Button icon="plus" onClick={() => setRows([...rows, { days: [], start: '22:00', end: '07:00' }])} data-testid="window-add">{s('au.window_add')}</Button>
        </div>
        <NumberField label={s('au.offset')} hint={s('au.offset_hint')} value={offset} onChange={setOffset} min={-720} max={840} step={30} data-testid="window-offset" />
        <div className="row"><Button variant="primary" icon="save" busy={act.busy} onClick={save} data-testid="windows-save">{s('common.save')}</Button></div>
      </div>
    </Card>
  )
}

function Rhythm({ info, schedule }: { info: AutomationInfo; schedule: ScheduleInfo | undefined }) {
  const { s, f } = useL()
  return (
    <Card title={s('au.rhythm_title')}>
      <div className="stack-sm">
        <p className="small">{s('au.rhythm', { n: info.publishing.per_week, time: info.publishing.time })}</p>
        <div className="small muted">{s('au.rhythm_edit')} <Link to={`/pages/${info.page}/settings`}>{s('au.rhythm_link')}</Link></div>
        <div>
          <span className="field-label">{s('au.next_slots')}</span>
          <ul className="chips" data-testid="slots">{info.publishing.next_slots.map((x) => <li key={x} className="chip">{f.dateTime(x)}</li>)}</ul>
        </div>
        {schedule && schedule.scheduled.length > 0 && (
          <ul className="lab-history" data-testid="scheduled">
            {schedule.scheduled.map((p) => (
              <li key={p.id} className="row between"><span>{p.title}</span><span className="small muted">{p.scheduled_at ? f.dateTime(p.scheduled_at) : '—'} · {p.status}</span></li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

function AutoPublish({ info, onChanged }: { info: AutomationInfo; onChanged: () => void }) {
  const { s, f } = useL()
  const act = useAction()
  const [typed, setTyped] = useState('')
  const ap = info.auto_publish
  const enable = () => act.run(async () => { await api.post(`/pages/${info.page}/auto-publish`, { enable: true, confirm: typed }); setTyped(''); onChanged() }, { success: s('au.ap_enabled') })
  const disable = () => act.run(async () => { await api.post(`/pages/${info.page}/auto-publish`, { enable: false }); onChanged() }, { success: s('au.ap_disabled') })
  return (
    <Card title={s('au.ap_title')}>
      <div className="stack-sm" data-testid="auto-publish">
        <Notice tone="warn" icon="alert">{s('au.ap_warning')}</Notice>
        <div className="row">
          <Badge tone={ap.enabled ? 'err' : 'ok'}><span data-testid="ap-state">{ap.enabled ? s('au.ap_on') : s('au.ap_off')}</span></Badge>
          {ap.confirmed_at && <span className="small muted">{s('au.ap_since', { when: f.dateTime(ap.confirmed_at) })}</span>}
          <Badge tone={ap.feature_flag ? 'ok' : 'neutral'}>{ap.feature_flag ? s('au.flag_on') : s('au.flag_off')}</Badge>
          <Badge tone={ap.can_post_now ? 'err' : 'neutral'}><span data-testid="ap-can-post">{ap.can_post_now ? s('au.can_post') : s('au.cannot_post')}</span></Badge>
        </div>
        {ap.why_not && <p className="small muted" data-testid="ap-why-not">{s('au.why_not')}: {ap.why_not}</p>}
        {ap.enabled ? (
          <div className="row"><Button variant="danger" icon="stop" busy={act.busy} onClick={disable} data-testid="ap-disable">{s('au.ap_disable')}</Button></div>
        ) : (
          <div className="stack-sm">
            <p className="small">{s('au.ap_type')}</p>
            <p className="lab-sentence ltr" data-testid="ap-sentence">{ap.confirm_text}</p>
            <TextField label={s('au.ap_sentence')} value={typed} onChange={setTyped} ltr data-testid="ap-confirm" autoComplete="off" />
            <div className="row">
              <Button variant="danger" icon="check" busy={act.busy} disabled={typed !== ap.confirm_text} onClick={enable} data-testid="ap-enable">{s('au.ap_enable')}</Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

function TargetCard({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { s } = useL()
  const act = useAction()
  const q = useQuery<PublishTargetRow>(`/targets/${id}`)
  const [draft, setDraft] = useState<{ mode?: string; enabled?: boolean; handle?: string; config?: Record<string, any> }>({})
  const t = q.data
  if (!t) return <CardSkeletons n={1} />
  const cfg = { ...t.config, ...(draft.config ?? {}) }
  const mode = draft.mode ?? t.mode
  const enabled = draft.enabled ?? t.enabled
  const save = () => act.run(async () => { await api.patch(`/targets/${id}`, draft); setDraft({}); q.reload(); onChanged() }, { success: s('au.target_saved') })
  const setCfg = (k: string, v: unknown) => setDraft({ ...draft, config: { ...(draft.config ?? {}), [k]: v } })
  return (
    <div className="card flat stack-sm" data-testid={`target-${id}`}>
      <div className="row between">
        <span className="strong ltr">{t.platform} {t.handle}</span>
        <Badge tone={t.ready ? 'ok' : 'warn'}>{t.adapter_label}</Badge>
      </div>
      <div className="grid-2">
        <SelectField label={s('au.target_mode')} value={mode} onChange={(v) => setDraft({ ...draft, mode: v })} options={[{ value: 'manual', label: s('au.mode_manual') }, { value: 'api', label: s('au.mode_api') }]} data-testid={`target-mode-${id}`} />
        <TextField label={s('au.target_handle')} value={draft.handle ?? t.handle} onChange={(v) => setDraft({ ...draft, handle: v })} ltr />
      </div>
      <SwitchField label={s('au.target_enabled')} checked={enabled} onChange={(v) => setDraft({ ...draft, enabled: v })} />
      {mode === 'api' && (
        <div className="stack-sm" data-testid={`target-config-${id}`}>
          <TextField label={s('au.cfg_ig_user_id')} hint={s('au.cfg_ig_user_id_hint')} value={String(cfg.ig_user_id ?? '')} onChange={(v) => setCfg('ig_user_id', v)} ltr data-testid={`cfg-ig-${id}`} />
          <TextField label={s('au.cfg_public_base_url')} hint={s('au.cfg_public_base_url_hint')} value={String(cfg.public_base_url ?? '')} onChange={(v) => setCfg('public_base_url', v)} ltr placeholder="https://media.example.org" />
          <SwitchField label={s('au.cfg_page_linked')} checked={!!cfg.facebook_page_linked} onChange={(v) => setCfg('facebook_page_linked', v)} />
          <Notice tone="info" icon="info">{s('au.token_note')}</Notice>
        </div>
      )}
      <div className="stack-sm">
        <span className="field-label">{s('au.requirements')}</span>
        <ul className="lab-reqs" data-testid={`requirements-${id}`}>
          {t.requirements.map((r) => (
            <li key={r.key} className={r.ok ? 'ok' : 'bad'} data-testid={`req-${id}-${r.key}`}>
              <Badge tone={r.ok ? 'ok' : 'err'}>{r.ok ? s('au.req_ok') : s('au.req_missing')}</Badge> <span className="small">{r.text}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="row"><Button variant="primary" icon="save" busy={act.busy} disabled={Object.keys(draft).length === 0} onClick={save} data-testid={`target-save-${id}`}>{s('common.save')}</Button></div>
    </div>
  )
}

function Targets({ page }: { page: PageLite }) {
  const { s } = useL()
  const act = useAction()
  const list = useQuery<{ id: number }[]>(`/pages/${page.id}/targets`)
  const add = () => act.run(async () => { await api.post(`/pages/${page.id}/targets`, { platform: 'instagram', handle: '' }); list.reload() }, { success: s('au.target_added') })
  return (
    <Card title={s('au.targets_title')} actions={<Button size="sm" icon="plus" busy={act.busy} onClick={add} data-testid="target-add">{s('au.target_add')}</Button>}>
      <div className="stack-sm">
        <details data-testid="instagram-requirements">
          <summary style={{ cursor: 'pointer' }} className="strong">{s('au.ig_title')}</summary>
          <ul className="small" style={{ margin: '0.4rem 0 0', paddingInlineStart: '1.2rem' }}>
            {(['au.ig_1', 'au.ig_2', 'au.ig_3', 'au.ig_4', 'au.ig_5', 'au.ig_6'] as const).map((k) => <li key={k}>{s(k)}</li>)}
          </ul>
        </details>
        <Async q={list} skeleton={<CardSkeletons n={1} />}>
          {(rows) => (rows.length === 0 ? <p className="muted" data-testid="targets-empty">{s('au.targets_empty')}</p> : <div className="stack-sm">{rows.map((r) => <TargetCard key={r.id} id={r.id} onChanged={list.reload} />)}</div>)}
        </Async>
      </div>
    </Card>
  )
}

function Publications({ page }: { page: PageLite }) {
  const { s, f } = useL()
  const confirm = useConfirm()
  const list = useQuery<PublicationRow[]>(`/pages/${page.id}/publications`)
  const runner = useJobRunner<Record<string, any>>({ onFinished: () => list.reload() })
  const act = useAction()
  const exportPkg = (p: PublicationRow) => runner.start(async () => api.post<{ job: Job }>(`/publications/${p.id}/export`, {}))
  const publish = async (p: PublicationRow) => {
    if (!(await confirm({ title: s('au.pub_publish'), message: s('au.pub_confirm', { title: p.episode_title }), confirmLabel: s('au.pub_publish'), danger: true }))) return
    await act.run(async () => { await runner.start(async () => api.post<{ job: Job }>(`/publications/${p.id}/publish`, { confirm: true })) })
  }
  return (
    <Card title={s('au.pubs_title')}>
      <div className="stack-sm">
        <Async q={list} skeleton={<CardSkeletons n={1} />}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty icon="publish" title={s('au.pubs_empty')} text={s('au.pubs_empty_text')} />
            ) : (
              <ul className="lab-history" data-testid="publications">
                {rows.map((p) => (
                  <li key={p.id} className="stack-sm" data-testid={`publication-${p.id}`}>
                    <div className="row between">
                      <span>{p.episode_number}. {p.episode_title}</span>
                      <Badge tone={p.status === 'published' ? 'ok' : p.status === 'failed' ? 'err' : 'neutral'}>{p.status}</Badge>
                    </div>
                    <div className="row">
                      <span className="small muted">{p.scheduled_at ? f.dateTime(p.scheduled_at) : s('au.not_scheduled')}</span>
                      {p.package_url && <a className="small" href={p.package_url} download>{s('au.pub_package')}</a>}
                      <Button size="sm" icon="download" onClick={() => exportPkg(p)} data-testid={`pub-export-${p.id}`}>{s('au.pub_export')}</Button>
                      <Button size="sm" variant="danger" icon="publish" onClick={() => publish(p)} data-testid={`pub-publish-${p.id}`}>{s('au.pub_publish')}</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )
          }
        </Async>
        {runner.job && <JobView job={runner.job} offline={runner.offline} />}
      </div>
    </Card>
  )
}

function PageAutomation({ page }: { page: PageLite }) {
  const { s } = useL()
  const q = useQuery<AutomationInfo>(`/pages/${page.id}/automation`, { interval: 15000 })
  const sched = useQuery<ScheduleInfo>(`/pages/${page.id}/schedule`)
  const act = useAction()
  const [last, setLast] = useState<number | null>(null)
  const tick = () => act.run(async () => { const r = await api.post<{ actions: unknown[] }>('/automation/tick', {}); setLast(r.actions.length); q.reload(); sched.reload() })
  const reload = () => { q.reload(); sched.reload() }
  return (
    <Async q={q} skeleton={<CardSkeletons n={3} />}>
      {(info) => (
        <div className="stack-lg" data-testid="automation-page">
          <Levels info={info} onChanged={reload} />
          <div className="row">
            <Button icon="play" busy={act.busy} onClick={tick} data-testid="au-tick">{s('au.tick')}</Button>
            {last !== null && <span className="small muted" data-testid="au-tick-result">{s('au.tick_result', { n: last })}</span>}
          </div>
          <Budgets key={`b-${info.gpu_minutes_per_week}-${info.api_usd_per_week}`} info={info} onChanged={reload} />
          <Windows key={`w-${JSON.stringify(info.render_windows)}-${info.utc_offset_minutes}`} info={info} onChanged={reload} />
          <Rhythm info={info} schedule={sched.data} />
          <AutoPublish info={info} onChanged={reload} />
          <Targets page={page} />
          <Publications page={page} />
        </div>
      )}
    </Async>
  )
}

export default function Automation() {
  const { s } = useL()
  useTitle(s('title.automation'))
  return (
    <div className="stack-lg">
      <PageHead title={s('title.automation')} crumbs={[{ label: s('lab.title'), to: '/lab' }, { label: s('title.automation') }]} />
      <p className="muted">{s('au.intro')}</p>
      <PagePicker>{(page) => <PageAutomation key={page.id} page={page} />}</PagePicker>
    </div>
  )
}
