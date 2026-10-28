import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Monitor, ModelRow, ModelsPayload, PackageInfo, SettingsPayload } from '../api/types'
import { useConfirm } from '../components/feedback'
import { JobView } from '../components/domain'
import { useApp } from '../components/Shell'
import { Async, Badge, Button, Card, CardSkeletons, ChoiceGrid, Link, Notice, PageHead, SelectField, SwitchField, TextField, type Tone } from '../components/ui'
import { useFormats } from '../formats'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

type Values = Record<string, string>

export default function Settings() {
  const { t } = useI18n()
  useTitle(t('nav.settings'))
  const q = useQuery<SettingsPayload>('/settings')
  return (
    <div className="stack-lg">
      <PageHead title={t('nav.settings')} />
      <Async q={q} skeleton={<CardSkeletons n={3} />}>
        {(s) => (
          <>
            <DemoCard s={s} onChanged={(p) => q.setData(p)} />
            <ServicesCard s={s} onSaved={(p) => q.setData(p)} />
            <ModelsSection />
            <WorkersCard />
            <PresetsCard />
            <PathsCard s={s} />
          </>
        )}
      </Async>
    </div>
  )
}

// ---------------------------------------------------------------- demo mode
function DemoCard({ s, onChanged }: { s: SettingsPayload; onChanged: (p: SettingsPayload) => void }) {
  const { t } = useI18n()
  const { refreshDemo } = useApp()
  const confirm = useConfirm()
  const act = useAction()
  const toggle = async (on: boolean) => {
    if (!on && !(await confirm({ message: t('set.demo_off_confirm'), confirmLabel: t('set.demo_off') }))) return
    const p = await act.run(() => api.post<SettingsPayload>('/settings/demo-mode', { enabled: on }), { success: t('common.saved') })
    if (p) {
      onChanged(p)
      refreshDemo()
    }
  }
  return (
    <Card title={t('set.demo_title')} className={s.demo_mode ? 'next-card' : undefined}>
      <div className="stack">
        <SwitchField label={t('set.demo_switch')} hint={s.demo_mode ? t('set.demo_on_hint') : t('set.demo_off_hint')} checked={s.demo_mode} disabled={act.busy} onChange={toggle} />
        <p className="muted">{t('set.demo_text')}</p>
        {s.demo_mode && <Notice tone="warn">{t('set.demo_warn')}</Notice>}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- providers and services
function ServicesCard({ s, onSaved }: { s: SettingsPayload; onSaved: (p: SettingsPayload) => void }) {
  const { t, tr } = useI18n()
  const { refreshDemo } = useApp()
  const models = useQuery<ModelsPayload>('/models?comfy=0')
  const [v, setV] = useState<Values>(s.values)
  const [key, setKey] = useState('')
  useEffect(() => setV(s.values), [s.values])
  const dirty = JSON.stringify(v) !== JSON.stringify(s.values) || key.trim() !== ''
  const save = useAction()
  const test = useAction()
  const [result, setResult] = useState<{ provider: string; ok: boolean; detail: string; model: string; sample?: string; seconds?: number } | null>(null)
  const confirm = useConfirm()
  const set = (k: string, val: string) => setV({ ...v, [k]: val })
  const ollama = s.providers.find((p) => p.id === 'ollama')
  const detected = ollama?.models ?? []
  const imageWorkflows = (models.data?.workflows ?? []).filter((w) => w.kind.includes('image') || w.kind.includes('t2i') || w.id.includes('t2i'))
  const wfOptions = Array.from(new Set([v.image_workflow, ...imageWorkflows.map((w) => w.id)].filter(Boolean)))

  const doSave = async () => {
    const body: Record<string, unknown> = {}
    for (const k of Object.keys(v)) if (v[k] !== s.values[k]) body[k] = v[k]
    if (key.trim()) body.openai_api_key = key.trim()
    const p = await save.run(() => api.put<SettingsPayload>('/settings', body), { success: t('common.saved') })
    if (p) {
      onSaved(p)
      setKey('')
      refreshDemo()
    }
  }
  const clearKey = async () => {
    if (!(await confirm({ message: t('set.key_clear_confirm'), danger: true, confirmLabel: t('set.key_clear') }))) return
    const p = await save.run(() => api.put<SettingsPayload>('/settings', { clear_openai_api_key: true }), { success: t('set.key_cleared') })
    if (p) onSaved(p)
  }
  const runTest = async () => {
    const r = await test.run(() => api.post<NonNullable<typeof result>>('/settings/test-llm', { provider: v.llm_provider }))
    if (r) setResult(r)
  }
  const enums = s.enums

  return (
    <Card title={t('set.services_title')}>
      <div className="stack-lg">
        <section className="stack">
          <ChoiceGrid
            legend={t('set.llm')}
            name="llm"
            value={v.llm_provider}
            onChange={(x) => { set('llm_provider', x); setResult(null) }}
            options={s.providers.map((p) => ({
              value: p.id,
              title: tr('provider.' + p.id, p.label),
              text: p.note,
              extra: (
                <span className="row">
                  <Badge tone={p.ok ? 'ok' : 'warn'}>{p.ok ? t('set.detected') : t('set.not_detected')}</Badge>
                  {p.active && <Badge tone="primary">{t('set.active')}</Badge>}
                </span>
              ),
            }))}
          />
          {v.llm_provider === 'fake' && <Notice tone="warn">{t('set.fake_note')}</Notice>}
          {v.llm_provider === 'ollama' && (
            <div className="grid-2">
              <TextField label={t('set.ollama_url')} type="url" ltr value={v.ollama_url} onChange={(x) => set('ollama_url', x)} />
              <div className="stack-sm">
                <SelectField
                  label={t('set.ollama_model')}
                  value={v.ollama_model}
                  onChange={(x) => set('ollama_model', x)}
                  options={[{ value: '', label: detected.length ? t('set.model_auto') : t('set.model_none') }, ...Array.from(new Set([...(v.ollama_model ? [v.ollama_model] : []), ...detected])).map((m) => ({ value: m, label: m }))]}
                  hint={detected.length ? t('set.models_found', { n: detected.length }) : t('set.models_not_found')}
                />
              </div>
            </div>
          )}
          {v.llm_provider === 'openai' && (
            <div className="stack">
              <div className="grid-2">
                <TextField label={t('set.openai_url')} type="url" ltr value={v.openai_base_url} onChange={(x) => set('openai_base_url', x)} placeholder="https://…/v1" />
                <TextField label={t('set.openai_model')} ltr value={v.openai_model} onChange={(x) => set('openai_model', x)} />
                <SelectField label={t('set.json_mode')} value={v.openai_json_mode} onChange={(x) => set('openai_json_mode', x)} options={(enums.openai_json_mode ?? ['json_object']).map((m) => ({ value: m, label: m }))} hint={t('set.json_mode_hint')} />
              </div>
              <div className="stack-sm">
                <TextField
                  label={t('set.api_key')}
                  type="password"
                  autoComplete="off"
                  ltr
                  value={key}
                  onChange={setKey}
                  placeholder={s.api_key.set ? t('set.key_set', { hint: s.api_key.hint || '…' }) : t('set.key_none')}
                  hint={t('set.key_hint')}
                />
                {s.api_key.set && (
                  <div className="row">
                    <Badge tone="ok">{t('set.key_saved')} {s.api_key.hint && <span className="ltr">{s.api_key.hint}</span>}</Badge>
                    <Button size="sm" variant="danger" onClick={clearKey}>{t('set.key_clear')}</Button>
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="row">
            <Button icon="check" busy={test.busy} disabled={dirty} onClick={runTest}>{t('set.test')}</Button>
            {dirty && <span className="small muted">{t('set.test_save_first')}</span>}
          </div>
          {result && (
            <Notice tone={result.ok ? 'ok' : 'err'}>
              <div className="stack-sm">
                <strong>{result.ok ? t('set.test_ok') : t('set.test_fail')}</strong>
                <div className="small">{t('set.test_provider')}: {tr('provider.' + result.provider, result.provider)}{result.model ? ` · ${t('set.test_model')}: ` : ''}<span className="ltr">{result.model}</span></div>
                {result.detail && <div className="small ltr">{result.detail}</div>}
                {result.sample && <div className="small">{t('set.test_sample')}: <span className="ltr">{result.sample}</span></div>}
                {result.seconds != null && <div className="small">{t('set.test_seconds', { s: result.seconds })}</div>}
              </div>
            </Notice>
          )}
        </section>

        <hr className="divider" />

        <section className="stack">
          <h3>{t('set.media_title')}</h3>
          <div className="grid-2">
            <TextField label={t('set.comfy_url')} type="url" ltr value={v.comfyui_url} onChange={(x) => set('comfyui_url', x)} hint={t('set.comfy_hint')} />
            <TextField label={t('set.comfy_dir')} ltr value={v.comfyui_dir} onChange={(x) => set('comfyui_dir', x)} hint={t('set.comfy_dir_hint')} />
            <SelectField label={t('set.image_engine')} value={v.image_engine} onChange={(x) => set('image_engine', x)} options={(enums.image_engine ?? ['auto']).map((m) => ({ value: m, label: tr('imgengine.' + m, m) }))} hint={t('set.image_engine_hint')} />
            <SelectField label={t('set.workflow')} value={v.image_workflow} onChange={(x) => set('image_workflow', x)} options={wfOptions.map((m) => ({ value: m, label: m }))} hint={t('set.workflow_hint')} />
            <SelectField label={t('set.tts_engine')} value={v.tts_engine} onChange={(x) => set('tts_engine', x)} options={(enums.tts_engine ?? ['auto']).map((m) => ({ value: m, label: tr('ttsengine.' + m, m) }))} hint={t('set.tts_engine_hint')} />
            <TextField label={t('set.piper_voice')} ltr value={v.piper_voice} onChange={(x) => set('piper_voice', x)} />
            <TextField label={t('set.moss_url')} type="url" ltr value={v.moss_tts_url} onChange={(x) => set('moss_tts_url', x)} hint={t('set.moss_hint')} />
            <SelectField label={t('set.research_fetch')} value={v.research_fetch} onChange={(x) => set('research_fetch', x)} options={(enums.research_fetch ?? ['off']).map((m) => ({ value: m, label: tr('fetch.' + m, m) }))} hint={t('set.research_hint')} />
          </div>
        </section>

        <div className="sticky-actions">
          <Button variant="primary" icon="save" busy={save.busy} disabled={!dirty} onClick={doSave}>{t('common.save')}</Button>
          <Button disabled={!dirty} onClick={() => { setV(s.values); setKey('') }}>{t('prof.revert')}</Button>
          {dirty && <span className="small muted">{t('prof.unsaved')}</span>}
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- models, licences, optional packs
const COMMERCIAL: Record<string, { tone: Tone; key: 'lic.yes' | 'lic.conditional' | 'lic.no' | 'lic.unknown' }> = {
  yes: { tone: 'ok', key: 'lic.yes' },
  conditional: { tone: 'warn', key: 'lic.conditional' },
  no: { tone: 'err', key: 'lic.no' },
  unknown: { tone: 'neutral', key: 'lic.unknown' },
}

function ModelsSection() {
  const { t, f } = useI18n()
  const confirm = useConfirm()
  const q = useQuery<ModelsPayload>('/models')
  const runner = useJobRunner({ onFinished: () => q.reload() })
  const [installing, setInstalling] = useState<string | null>(null)
  const install = async (pkg: string, info?: PackageInfo) => {
    const size = info?.size ? f.bytes(info.size) : ''
    if (!(await confirm({ message: t('set.install_confirm', { size }), confirmLabel: t('set.install') }))) return
    setInstalling(pkg)
    runner.start(() => api.post('/downloads', { packages: [pkg] }))
  }
  return (
    <Card title={t('set.models_title')} actions={<Button size="sm" icon="refresh" onClick={q.reload}>{t('common.refresh')}</Button>}>
      <div className="stack-lg">
        <p className="muted">{t('set.models_intro')}</p>
        {runner.job && (
          <div className="stack-sm">
            <JobView job={runner.job} offline={runner.offline} />
            {installing && !runner.busy && <p className="small muted">{installing}</p>}
          </div>
        )}
        <Async q={q} skeleton={<CardSkeletons n={2} />}>
          {(m) => {
            const rows = [...m.models].sort((a, b) => Number(!!a.excluded) - Number(!!b.excluded))
            return (
              <>
                <section className="stack" aria-label={t('set.packages_title')}>
                  <h3>{t('set.packages_title')}</h3>
                  <div className="grid-auto">
                    {Object.entries(m.packages).map(([id, p]) => (
                      <div key={id} className="card flat stack-sm">
                        <div className="row between">
                          <span className="strong ltr">{id}</span>
                          <span className="row">
                            {p.default && <Badge tone="info">{t('set.pkg_default')}</Badge>}
                            {p.complete ? <Badge tone="ok">{t('set.installed')}</Badge> : <Badge>{t('set.pkg_progress', { a: p.installed, b: p.items })}</Badge>}
                          </span>
                        </div>
                        <div className="small" dir="auto">{p.title}</div>
                        <div className="small muted">{t('set.pkg_size')}: {f.bytes(p.size)}</div>
                        <div className="small muted">{t('set.pkg_licence')}: <bdi>{p.licence || '—'}</bdi> {p.licence_verified ? '' : `(${t('set.not_verified')})`}</div>
                        {p.note && <div className="small muted" dir="auto">{p.note}</div>}
                        {!p.complete && (
                          <div>
                            <Button size="sm" icon="download" disabled={runner.busy} onClick={() => install(id, p)}>{t('set.install')}</Button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="stack" aria-label={t('set.licences_title')}>
                  <h3>{t('set.licences_title')}</h3>
                  <p className="small muted">{t('set.licences_note', { date: m.checked_on })}</p>
                  <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 330px), 1fr))' }}>
                    {rows.map((r) => (
                      <ModelCard key={r.id} r={r} pkg={r.package ? m.packages[r.package] : undefined} busy={runner.busy} onInstall={() => r.package && install(r.package, m.packages[r.package])} />
                    ))}
                  </div>
                </section>

                {m.workflows.length > 0 && (
                  <section className="stack" aria-label={t('set.workflows_title')}>
                    <h3>{t('set.workflows_title')}</h3>
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>{t('set.wf_name')}</th>
                            <th>{t('set.wf_kind')}</th>
                            <th>{t('set.wf_vram')}</th>
                            <th>{t('set.wf_licence')}</th>
                            <th>{t('set.wf_available')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {m.workflows.map((w) => (
                            <tr key={w.id}>
                              <td><div className="strong">{w.title}</div><div className="small muted ltr">{w.id}</div></td>
                              <td className="ltr">{w.kind}</td>
                              <td>{w.vram_gb != null ? `${f.num(w.vram_gb)} GB` : '—'}</td>
                              <td className="small">{w.licence} <Badge tone={w.licence_status === 'verified' ? 'ok' : 'warn'}>{w.licence_status}</Badge></td>
                              <td>{w.available == null ? <Badge>{t('set.wf_unknown')}</Badge> : w.available ? <Badge tone="ok">{t('set.wf_ready')}</Badge> : <Badge tone="warn" title={w.missing.join(', ')}>{t('set.wf_missing', { n: w.missing.length })}</Badge>}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </>
            )
          }}
        </Async>
      </div>
    </Card>
  )
}

function ModelCard({ r, pkg, busy, onInstall }: { r: ModelRow; pkg: PackageInfo | undefined; busy: boolean; onInstall: () => void }) {
  const { t, f } = useI18n()
  const c = COMMERCIAL[r.commercial] ?? COMMERCIAL.unknown
  const verified = r.verified === null ? null : r.verified === 'brief' ? t('lic.verified_brief') : r.verified
  return (
    <div className={'card flat stack-sm' + (r.excluded ? ' soft' : '')} style={r.excluded ? { opacity: 0.85 } : undefined}>
      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <span className="strong" dir="auto">{r.name}</span>
        {r.installed != null && <Badge tone={r.installed ? 'ok' : 'neutral'}>{r.installed ? t('set.installed') : t('set.not_installed')}</Badge>}
      </div>
      <div className="small muted" dir="auto">{r.role}</div>
      <div className="row">
        <Badge tone={c.tone}>{t('lic.commercial')}: {t(c.key)}</Badge>
        {r.excluded && <Badge tone="err">{t('lic.excluded')} · EXCLUDED</Badge>}
        {r.decision && <Badge tone="warn">{t('lic.decision')} · OWNER DECISION</Badge>}
      </div>
      <div className="small"><span className="muted">{t('lic.licence')}:</span> <bdi>{r.licence}</bdi></div>
      <div className="small">
        <span className="muted">{t('lic.verified')}:</span> {verified ? <bdi>{verified}</bdi> : <Badge tone="warn">{t('set.not_verified')}</Badge>}
      </div>
      <div className="small"><span className="muted">VRAM:</span> <bdi>{r.vram}</bdi></div>
      {r.notes && <div className="small muted" dir="auto">{r.notes}</div>}
      {r.package && !r.excluded && r.installed === false && (
        <div className="row">
          <Button size="sm" icon="download" disabled={busy} onClick={onInstall}>
            {t('set.install')}{pkg?.size ? ` (${f.bytes(pkg.size)})` : ''}
          </Button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- workers, presets, storage
function WorkersCard() {
  const { t, f } = useI18n()
  const q = useQuery<Monitor>('/monitor', { interval: 5000 })
  return (
    <Card title={t('mon.workers')} actions={<Link to="/monitor">{t('nav.monitor')}</Link>}>
      <Async q={q} skeleton={<CardSkeletons n={1} />}>
        {(m) =>
          m.workers.length === 0 ? (
            <Notice tone="err">{t('mon.worker_down')}</Notice>
          ) : (
            <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {m.workers.map((w) => (
                <li key={w.name} className="row">
                  <span className={'dot ' + (w.alive ? 'ok' : 'err')} aria-hidden="true" />
                  <span className="strong ltr">{w.name}</span>
                  <Badge tone={w.alive ? 'ok' : 'err'}>{w.alive ? t('mon.alive') : t('mon.stopped')}</Badge>
                  <span className="small muted">{t('mon.last_seen')}: {f.ago(w.last_seen)}</span>
                </li>
              ))}
            </ul>
          )
        }
      </Async>
    </Card>
  )
}

function PresetsCard() {
  const { t } = useI18n()
  const fm = useFormats()
  return (
    <Card title={t('set.presets_title')}>
      <p className="muted">{t('set.presets_text')}</p>
      <dl className="kv" style={{ marginBlockStart: '0.75rem' }}>
        {Object.entries(fm.data?.presets ?? {}).map(([k, p]) => (
          <span key={k} style={{ display: 'contents' }}>
            <dt className="strong">{p.label_fa}</dt>
            <dd>{p.note_fa}</dd>
          </span>
        ))}
      </dl>
    </Card>
  )
}

function PathsCard({ s }: { s: SettingsPayload }) {
  const { t, tr } = useI18n()
  return (
    <Card title={t('set.paths_title')}>
      <p className="muted small">{t('set.paths_note')}</p>
      <dl className="kv" style={{ marginBlockStart: '0.5rem' }}>
        {Object.entries(s.paths).map(([k, p]) => (
          <span key={k} style={{ display: 'contents' }}>
            <dt>{tr('path.' + k, k)}</dt>
            <dd className="ltr mono">{p}</dd>
          </span>
        ))}
      </dl>
    </Card>
  )
}
