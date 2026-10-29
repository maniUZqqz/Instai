import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { JobView } from '../components/domain'
import { useConfirm, useToast } from '../components/feedback'
import { Async, AreaField, Badge, Button, Card, CardSkeletons, Empty, ExtLink, Notice, PageHead, TextField, type Tone } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import { useI18n } from '../i18n'

// ---------------------------------------------------------------- what GET /api/models/found returns (instai/core/model_status.py)
interface ComfyInstall {
  root: string
  portable: string | null
  launcher: string | null
  python: string | null
  desktop: boolean
  selected: boolean
  files: number
  model_roots: { kind: string; path: string }[]
  extra_yaml: string[]
  custom_nodes: number
  port: number
}
interface FoundItem {
  id: string
  kind: 'comfy' | 'voice' | 'ollama'
  title: string
  found: boolean
  path?: string | null
  file?: string
  aliases?: string[]
  folder?: string
  listed?: string | null
  found_as?: string | null
  size?: number | null
  size_ok?: boolean
  elsewhere?: string | null
  package?: string | null
  uses: string[]
  running?: boolean
  missing?: string[]
  models?: string[]
  voices?: string[]
  voice?: string
  detail?: string
}
interface Feature {
  id: string
  group: string
  ready: boolean
  missing: string[]
  missing_nodes: string[]
  packages: string[]
}
interface Offer {
  id: string
  name: string
  group: string
  title: string
  why: { fa?: string; en?: string }
  note: { fa?: string; en?: string }
  licence: string
  licence_url: string
  commercial: string
  vram: string
  workflow: string
  complete: boolean
  size: number
  missing_size: number
  needs: { id: string; title: string; complete: boolean; missing_size: number; licence: string }[]
  restart_comfyui: boolean
}
interface ModelsFound {
  scanned_at: string
  seconds: number
  dirs: number
  stopped: string
  defaults: boolean
  roots: string[]
  manual: string[]
  comfyui_dir: string
  comfyui: { installs: ComfyInstall[]; url: string; running: boolean; nodes: number; startable: boolean; started_by_instai: boolean; selected: string | null }
  items: FoundItem[]
  features: Feature[]
  offers: Offer[]
  nm_homes: string[]
  free_gb: number | null
}

const COMMERCIAL_TONE: Record<string, Tone> = { yes: 'ok', conditional: 'warn', no: 'err', unknown: 'neutral' }

export default function Models() {
  const { t } = useI18n()
  useTitle(t('nav.models'))
  const q = useQuery<ModelsFound>('/models/found')
  const act = useAction()
  const rescan = async (quiet = false) => {
    const p = await act.run(() => api.post<ModelsFound>('/models/rescan', {}), quiet ? undefined : { success: t('mdl.rescanned') })
    if (p) q.setData(p)
  }
  return (
    <div className="stack-lg">
      <PageHead title={t('nav.models')}>
        <Button icon="refresh" busy={act.busy} onClick={() => rescan()}>{t('mdl.rescan')}</Button>
      </PageHead>
      <p className="muted">{t('mdl.intro')}</p>
      <Async q={q} skeleton={<CardSkeletons n={4} />}>
        {(m) => (
          <>
            <Summary m={m} />
            <ComfyCard m={m} />
            <FeaturesCard m={m} />
            <ItemsCard m={m} />
            <OffersCard m={m} onFinished={() => rescan(true)} />
            <PathsCard m={m} onSaved={(p) => q.setData(p)} />
          </>
        )}
      </Async>
    </div>
  )
}

function Summary({ m }: { m: ModelsFound }) {
  const { t, f } = useI18n()
  const comfyItems = m.items.filter((i) => i.kind === 'comfy')
  const ready = m.features.filter((x) => x.ready).length
  return (
    <Card title={t('mdl.summary')} actions={<span className="small muted">{t('mdl.scanned', { s: f.num(m.seconds, 1), n: f.num(m.dirs) })} · {f.dateTime(m.scanned_at)}</span>}>
      <div className="stack">
        <div className="row">
          <Badge tone={comfyItems.every((i) => i.found) ? 'ok' : 'warn'}>{t('mdl.files_found', { a: comfyItems.filter((i) => i.found).length, b: comfyItems.length })}</Badge>
          <Badge tone={ready === m.features.length ? 'ok' : 'warn'}>{t('mdl.features_ready', { a: ready, b: m.features.length })}</Badge>
          {m.free_gb != null && <Badge>{t('mdl.free', { n: f.num(m.free_gb, 1) })}</Badge>}
        </div>
        {m.stopped && <Notice tone="warn">{t('mdl.stopped')}</Notice>}
        {!m.defaults && <Notice tone="info">{t('mdl.no_defaults')}</Notice>}
        {m.nm_homes.length > 0 && (
          <div className="small">
            <span className="muted">{t('mdl.nm_homes')}:</span>
            <ul className="ltr mono small" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
              {m.nm_homes.map((h) => <li key={h}>{h}</li>)}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

function ComfyCard({ m }: { m: ModelsFound }) {
  const { t, f } = useI18n()
  const act = useAction()
  const toast = useToast()
  const start = async () => {
    const r = await act.run(() => api.post<{ started: boolean; already_running: boolean }>('/models/comfyui/start', {}))
    if (r) toast.ok(r.already_running ? t('mdl.comfy_already') : t('mdl.comfy_starting'))
  }
  const c = m.comfyui
  return (
    <Card
      title={t('mdl.comfy_title')}
      actions={
        <>
          <Badge tone={c.running ? 'ok' : c.startable ? 'warn' : 'err'}>{c.running ? t('mdl.running', { n: c.nodes }) : c.startable ? t('mdl.not_running_startable') : t('mdl.not_running')}</Badge>
          {!c.running && c.startable && <Button size="sm" icon="play" busy={act.busy} onClick={start}>{t('mdl.comfy_start')}</Button>}
        </>
      }
    >
      <div className="stack">
        <div className="small muted">{t('mdl.comfy_url')}: <span className="ltr">{c.url}</span></div>
        {c.installs.length === 0 ? (
          <Notice tone="warn">{t('mdl.comfy_none')}</Notice>
        ) : (
          c.installs.map((i) => (
            <div key={i.root} className="card flat stack-sm">
              <div className="row between">
                <span className="strong ltr mono small">{i.root}</span>
                <span className="row">
                  {i.selected && <Badge tone="primary">{t('mdl.selected')}</Badge>}
                  {i.desktop && <Badge>ComfyUI Desktop</Badge>}
                  <Badge>{t('mdl.n_files', { n: f.num(i.files) })}</Badge>
                </span>
              </div>
              <dl className="kv small">
                <dt>{t('mdl.launcher')}</dt>
                <dd className="ltr mono">{i.launcher ?? '—'}</dd>
                <dt>{t('mdl.python')}</dt>
                <dd className="ltr mono">{i.python ?? '—'}</dd>
                <dt>{t('mdl.extra_yaml')}</dt>
                <dd className="ltr mono">{i.extra_yaml.length ? i.extra_yaml.join(' · ') : '—'}</dd>
                <dt>{t('mdl.custom_nodes')}</dt>
                <dd>{f.num(i.custom_nodes)}</dd>
              </dl>
              <details>
                <summary className="small" style={{ cursor: 'pointer' }}>{t('mdl.model_roots', { n: i.model_roots.length })}</summary>
                <ul className="small ltr mono" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
                  {i.model_roots.map((r) => <li key={r.kind + r.path}>{r.kind}: {r.path}</li>)}
                </ul>
              </details>
            </div>
          ))
        )}
      </div>
    </Card>
  )
}

function FeaturesCard({ m }: { m: ModelsFound }) {
  const { t, tr } = useI18n()
  return (
    <Card title={t('mdl.features_title')}>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{t('mdl.col_feature')}</th>
              <th>{t('mdl.col_status')}</th>
              <th>{t('mdl.col_missing')}</th>
            </tr>
          </thead>
          <tbody>
            {m.features.map((x) => (
              <tr key={x.id}>
                <td>
                  <div className="strong">{tr('mdl.use.' + x.id, x.id)}</div>
                  <div className="small muted">{tr('mdl.group.' + x.group, x.group)}</div>
                </td>
                <td><Badge tone={x.ready ? 'ok' : 'warn'}>{x.ready ? t('mdl.ready') : t('mdl.blocked')}</Badge></td>
                <td className="small">
                  {x.ready ? '—' : (
                    <div className="stack-sm">
                      {x.missing.length > 0 && <div className="ltr">{x.missing.slice(0, 4).join(' · ')}{x.missing.length > 4 ? ` +${x.missing.length - 4}` : ''}</div>}
                      {x.missing_nodes.length > 0 && <div>{t('mdl.missing_nodes')}: <span className="ltr">{x.missing_nodes.join(', ')}</span></div>}
                      {x.packages.some((p) => m.offers.some((o) => o.id === p || o.needs.some((n) => n.id === p))) && <div className="muted">{t('mdl.see_offers')}</div>}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function ItemsCard({ m }: { m: ModelsFound }) {
  const { t, tr, f } = useI18n()
  const [onlyMissing, setOnlyMissing] = useState(false)
  const rows = m.items.filter((i) => !onlyMissing || !i.found)
  return (
    <Card title={t('mdl.items_title')} actions={<Button size="sm" variant="ghost" onClick={() => setOnlyMissing((v) => !v)}>{onlyMissing ? t('mdl.show_all') : t('mdl.show_missing')}</Button>}>
      {rows.length === 0 ? (
        <Empty icon="check" title={t('mdl.nothing_missing')} />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('mdl.col_model')}</th>
                <th>{t('mdl.col_status')}</th>
                <th>{t('mdl.col_where')}</th>
                <th>{t('mdl.col_used_by')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id}>
                  <td>
                    <div className="strong small" dir="auto">{i.title}</div>
                    {i.file && <div className="small muted ltr mono">{i.file}{i.aliases && i.aliases.length > 0 ? ` (${t('mdl.or')} ${i.aliases.join(', ')})` : ''}</div>}
                  </td>
                  <td className="nowrap">
                    <Badge tone={i.found ? 'ok' : 'err'}>{i.found ? t('mdl.found') : t('mdl.missing')}</Badge>
                    {i.running && <> <Badge tone="info">{t('mdl.running_short')}</Badge></>}
                    {i.size_ok === false && <> <Badge tone="warn" title={t('mdl.size_warn')}>{t('mdl.size_bad')}</Badge></>}
                  </td>
                  <td className="small">
                    {i.path ? <div className="ltr mono">{i.path}</div> : i.listed ? <div className="ltr mono">{t('mdl.listed')}: {i.listed}</div> : null}
                    {!i.found && i.folder && <div className="muted">{t('mdl.put_in', { folder: i.folder })}</div>}
                    {!i.found && i.elsewhere && <div className="muted">{t('mdl.elsewhere')}: <span className="ltr mono">{i.elsewhere}</span></div>}
                    {!i.found && i.missing && i.missing.length > 0 && <div className="muted ltr">{i.missing.slice(0, 3).join(' · ')}</div>}
                    {i.models && i.models.length > 0 && <div className="ltr">{i.models.slice(0, 6).join(', ')}</div>}
                    {i.voices && i.voices.length > 0 && <div className="ltr">{i.voices.slice(0, 6).join(', ')}</div>}
                    {i.size ? <div className="muted">{f.bytes(i.size)}</div> : null}
                  </td>
                  <td className="small">{i.uses.map((u) => tr('mdl.use.' + u, u)).join('، ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function OffersCard({ m, onFinished }: { m: ModelsFound; onFinished: () => void }) {
  const { t, f, lang } = useI18n()
  const confirm = useConfirm()
  const [current, setCurrent] = useState<Offer | null>(null)
  const runner = useJobRunner({ onFinished })
  const download = async (o: Offer) => {
    const parts = o.needs.filter((n) => !n.complete)
    const tooBig = m.free_gb != null && o.missing_size > m.free_gb * 1e9
    const ok = await confirm({
      title: t('mdl.confirm_title', { name: o.name }),
      confirmLabel: t('mdl.download'),
      message: (
        <div className="stack-sm">
          <div><strong>{t('mdl.size_download')}:</strong> {f.bytes(o.missing_size)}</div>
          <div><strong>{t('mdl.licence')}:</strong> <bdi>{o.licence}</bdi></div>
          <div className="small">{(lang === 'en' ? o.why.en : o.why.fa) ?? ''}</div>
          {parts.length > 0 && (
            <div className="small">
              {t('mdl.also_needed')}:
              <ul style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
                {parts.map((n) => <li key={n.id} dir="auto">{n.title} ({f.bytes(n.missing_size)})</li>)}
              </ul>
            </div>
          )}
          {tooBig && <Notice tone="err">{t('mdl.no_space', { n: f.num(m.free_gb ?? 0, 1) })}</Notice>}
          <div className="small muted">{t('mdl.confirm_note')}</div>
        </div>
      ),
    })
    if (!ok) return
    setCurrent(o)
    runner.start(() => api.post(`/models/offers/${o.id}/download`, { confirm: true }))
  }
  if (m.offers.length === 0) return null
  return (
    <Card title={t('mdl.offers_title')}>
      <div className="stack">
        <p className="muted">{t('mdl.offers_intro')}</p>
        {runner.job && (
          <div className="stack-sm">
            {current && <div className="strong">{current.name}</div>}
            <JobView job={runner.job} offline={runner.offline} />
            {runner.succeeded && current?.restart_comfyui && <Notice tone="warn">{t('mdl.restart_comfy')}</Notice>}
          </div>
        )}
        <div className="grid-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 340px), 1fr))' }}>
          {m.offers.map((o) => (
            <div key={o.id} className="card flat stack-sm">
              <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                <span className="strong" dir="auto">{o.name}</span>
                <Badge tone={o.complete ? 'ok' : 'neutral'}>{o.complete ? t('mdl.installed') : t('mdl.not_installed')}</Badge>
              </div>
              <div className="row">
                <Badge tone="info">{t('mdl.offer_group.' + o.group)}</Badge>
                <Badge tone={COMMERCIAL_TONE[o.commercial] ?? 'neutral'}>{t('mdl.commercial')}: {t('mdl.commercial_' + (COMMERCIAL_TONE[o.commercial] ? o.commercial : 'unknown'))}</Badge>
              </div>
              <div className="small">{(lang === 'en' ? o.why.en : o.why.fa) ?? ''}</div>
              {(lang === 'en' ? o.note.en : o.note.fa) && <div className="small muted">{lang === 'en' ? o.note.en : o.note.fa}</div>}
              <div className="small"><span className="muted">{t('mdl.licence')}:</span> <bdi>{o.licence}</bdi>{o.licence_url && <> · <ExtLink href={o.licence_url}>{t('mdl.licence_link')}</ExtLink></>}</div>
              {o.vram && <div className="small"><span className="muted">VRAM:</span> <bdi>{o.vram}</bdi></div>}
              <div className="small"><span className="muted">{t('mdl.size_total')}:</span> {f.bytes(o.size)} · <span className="muted">{t('mdl.size_download')}:</span> {f.bytes(o.missing_size)}</div>
              {o.needs.length > 0 && (
                <div className="small"><span className="muted">{t('mdl.needs')}:</span> {o.needs.map((n) => `${n.title.split(' (')[0]}${n.complete ? ' ✓' : ''}`).join('، ')}</div>
              )}
              {!o.complete && (
                <div>
                  <Button size="sm" icon="download" disabled={runner.busy} onClick={() => download(o)}>{t('mdl.download_ask')}</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}

function PathsCard({ m, onSaved }: { m: ModelsFound; onSaved: (p: ModelsFound) => void }) {
  const { t } = useI18n()
  const [text, setText] = useState(m.manual.join('\n'))
  const [comfyDir, setComfyDir] = useState(m.comfyui_dir)
  const act = useAction()
  useEffect(() => setText(m.manual.join('\n')), [m.manual])
  useEffect(() => setComfyDir(m.comfyui_dir), [m.comfyui_dir])
  const save = async () => {
    const paths = text.split('\n').map((s) => s.trim()).filter(Boolean)
    const p = await act.run(() => api.put<ModelsFound>('/models/paths', { paths, comfyui_dir: comfyDir.trim() }), { success: t('common.saved') })
    if (p) onSaved(p)
  }
  const dirty = text !== m.manual.join('\n') || comfyDir !== m.comfyui_dir
  return (
    <Card title={t('mdl.paths_title')}>
      <div className="stack">
        <p className="muted small">{t('mdl.paths_intro')}</p>
        <AreaField label={t('mdl.paths_label')} hint={t('mdl.paths_hint')} value={text} onChange={setText} rows={4} dir="ltr" placeholder={'C:\\Users\\QQz\\Desktop\\N\nD:\\AI'} />
        <TextField label={t('mdl.comfy_dir')} hint={t('mdl.comfy_dir_hint')} ltr value={comfyDir} onChange={setComfyDir} />
        <div className="row">
          <Button variant="primary" icon="save" busy={act.busy} disabled={!dirty} onClick={save}>{t('mdl.paths_save')}</Button>
        </div>
        <details>
          <summary className="small" style={{ cursor: 'pointer' }}>{t('mdl.roots', { n: m.roots.length })}</summary>
          <ul className="small ltr mono" style={{ margin: '0.25rem 0 0', paddingInlineStart: '1.25rem' }}>
            {m.roots.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </details>
      </div>
    </Card>
  )
}
