import { Player, type PlayerRef } from '@remotion/player'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { JobView } from '../components/domain'
import { Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, ExtLink, Notice, PageHead, Progress, Segmented, SelectField, Tabs, TextField, AreaField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useStored, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { COMPOSITIONS, FPS, SIZES, byId, metaFor, type CompositionDef, type SizeId } from '../../../remotion/src/catalog'
import type { StyleKit } from '../../../remotion/src/kit/theme'
import type { RmCode, RmKit, RmRenders, RmStatus } from './types'

type TabKey = 'preview' | 'code' | 'renders'
type Values = Record<string, any>
type Draft = { values: Values; texts: Record<string, string> }

const stepsToText = (steps: { title: string; body?: string }[]) => steps.map((s) => (s.body ? `${s.title} | ${s.body}` : s.title)).join('\n')
const textToSteps = (text: string) =>
  text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const i = l.indexOf('|')
      return i < 0 ? { title: l, body: '' } : { title: l.slice(0, i).trim(), body: l.slice(i + 1).trim() }
    })

function initialDraft(def: CompositionDef, lang: 'fa' | 'en'): Draft {
  const d = def.defaults(lang) as Values
  const values: Values = {}
  const texts: Record<string, string> = {}
  for (const f of def.fields) {
    if (f.type === 'lines') texts[f.key] = (d[f.key] as string[]).join('\n')
    else if (f.type === 'steps') texts[f.key] = stepsToText(d[f.key])
    else values[f.key] = d[f.key]
  }
  return { values, texts }
}

function propsOf(def: CompositionDef, draft: Draft): Values {
  const p: Values = { ...draft.values }
  for (const f of def.fields) {
    if (f.type === 'lines') p[f.key] = draft.texts[f.key].split('\n').filter((l) => l.trim())
    if (f.type === 'steps') p[f.key] = textToSteps(draft.texts[f.key])
  }
  return p
}

/** The toolchain card: Node.js, the npm packages and a browser, set up by itself (START.bat starts it; the button repeats it). */
function SetupCard({ st, reload }: { st: RmStatus; reload: () => void }) {
  const { t, lang } = useI18n()
  const act = useAction()
  const runner = useJobRunner({ onFinished: reload })
  const row = (ok: boolean, label: string, detail: string) => (
    <div className="row" style={{ gap: '0.5rem' }}>
      <Badge tone={ok ? 'ok' : st.state === 'running' ? 'info' : 'warn'}>{ok ? t('rm.setup.ok') : st.state === 'running' ? t('rm.setup.running') : t('rm.setup.missing')}</Badge>
      <span className="strong">{label}</span>
      <span className="small muted ltr" dir="ltr">{detail}</span>
    </div>
  )
  const start = () => void act.run(() => runner.start(() => api.post('/remotion/setup', {})), { success: t('rm.setup.started') })
  return (
    <Card title={t('rm.setup.title')} actions={<Badge tone={st.ready ? 'ok' : st.state === 'error' ? 'err' : st.state === 'running' ? 'info' : 'warn'}>{st.ready ? t('rm.setup.ready') : st.state === 'error' ? t('rm.setup.failed') : st.state === 'running' ? t('rm.setup.running') : t('rm.setup.not_ready')}</Badge>}>
      <div className="stack">
        {row(!!st.node, 'Node.js', st.node ? `${st.node.version} (${st.node.source === 'portable' ? t('rm.setup.portable') : t('rm.setup.system')})` : '')}
        {row(st.packages, t('rm.setup.packages'), st.remotion ? `Remotion ${st.remotion}` : '')}
        {row(!!st.browser, t('rm.setup.browser'), st.browser ? st.browser.path.split(/[\\/]/).pop() ?? '' : '')}
        {(st.message_fa || st.message_en) && st.state !== 'ready' && <Notice tone={st.state === 'error' ? 'err' : 'info'} icon={st.state === 'running' ? 'clock' : 'info'}><span dir="auto">{lang === 'en' ? st.message_en : st.message_fa}</span></Notice>}
        {st.state === 'running' && <Progress indeterminate label={t('rm.setup.title')} />}
        {!st.ready && <p className="small muted">{t('rm.setup.auto', { auto: st.auto ? t('rm.setup.auto_on') : t('rm.setup.auto_off') })}</p>}
        {runner.job && <JobView job={runner.job} offline={runner.offline} compact />}
        <div className="row">
          <Button icon="refresh" busy={act.busy || runner.busy} disabled={st.state === 'running'} onClick={start} data-testid="rm-setup-run">{st.ready ? t('rm.setup.recheck') : t('rm.setup.run')}</Button>
          <ExtLink href="https://github.com/remotion-dev/remotion/blob/main/LICENSE.md">{t('rm.license_link')}</ExtLink>
        </div>
        <p className="small muted">{t('rm.license')}</p>
      </div>
    </Card>
  )
}

function KitChip({ k, active, onPick, lang }: { k: RmKit; active: boolean; onPick: () => void; lang: 'fa' | 'en' }) {
  const p = k.palette
  return (
    <button type="button" className={'cur-pkg' + (active ? ' picked' : '')} aria-pressed={active} onClick={onPick} data-testid={'rm-style-' + k.key} style={{ textAlign: 'start', cursor: 'pointer', padding: '0.5rem 0.65rem' }}>
      <div className="strong" dir="auto">{(lang === 'en' ? k.name_en : k.name_fa) || k.name}</div>
      <div className="row" style={{ gap: '0.2rem', margin: '0.25rem 0' }} aria-hidden="true">
        {[p.background, p.primary, p.secondary, p.accent, p.highlight].map((c, i) => <span key={i} style={{ width: 16, height: 16, borderRadius: 4, background: c, border: '1px solid rgba(128,128,128,.4)' }} />)}
      </div>
      <div className="small muted" dir="auto">{(lang === 'en' ? k.animation_en : k.animation_fa) || k.animation}</div>
    </button>
  )
}

function CodeView({ def, code }: { def: CompositionDef; code: RmCode | undefined }) {
  const { t } = useI18n()
  const [file, setFile] = useState<string>('')
  const [copied, setCopied] = useState(false)
  const comp = code?.compositions.find((c) => c.id === def.id)
  const shared = code?.shared ?? []
  const shown = file ? shared.find((s) => s.file === file) : comp
  const text = (shown && 'code' in shown ? shown.code : '') || ''
  const copy = () => {
    try {
      void navigator.clipboard?.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked */
    }
  }
  return (
    <div className="stack" data-testid="rm-code">
      <Notice tone="info" icon="info">{t('rm.code.hint')}</Notice>
      <div className="row">
        <Button size="sm" variant={file ? 'default' : 'primary'} onClick={() => setFile('')}>{def.id}.tsx</Button>
        {shared.map((s) => <Button key={s.file} size="sm" variant={file === s.file ? 'primary' : 'default'} onClick={() => setFile(s.file)}>{s.name}</Button>)}
        <span className="spacer" />
        <Button size="sm" icon="copy" onClick={copy} disabled={!text}>{copied ? t('rm.code.copied') : t('rm.code.copy')}</Button>
      </div>
      {text ? <pre className="code-block ltr" dir="ltr" tabIndex={0} aria-label={shown && 'file' in shown ? shown.file : def.file} style={{ maxHeight: '32rem', overflow: 'auto', whiteSpace: 'pre', fontSize: '0.8rem', padding: '0.75rem', borderRadius: 8, background: 'var(--surface-2, rgba(128,128,128,.12))' }}>{text}</pre> : <Empty icon="info" title={t('rm.code.empty')} />}
    </div>
  )
}

function Renders({ data }: { data: RmRenders | undefined }) {
  const { t, f, lang } = useI18n()
  const rows = data?.renders ?? []
  if (!rows.length) return <Empty icon="film" title={t('rm.renders.empty')} />
  return (
    <div className="stack" data-testid="rm-renders">
      {rows.map((r) => (
        <div key={r.job_id} className="row" style={{ alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
          {r.url && r.kind === 'mp4' ? <video src={r.url} controls preload="metadata" style={{ width: 280, maxWidth: '100%', borderRadius: 8 }} /> : r.url ? <img src={r.url} alt="" style={{ width: 280, maxWidth: '100%', borderRadius: 8 }} /> : null}
          <div className="stack-sm">
            <div className="strong ltr" dir="ltr">{r.composition} #{r.job_id}</div>
            <div className="small muted">{[r.style, r.size && (lang === 'en' ? SIZES[r.size as SizeId]?.en : SIZES[r.size as SizeId]?.fa), r.width && `${r.width}×${r.height}`, r.seconds && f.duration(r.seconds), r.bytes && f.bytes(r.bytes)].filter(Boolean).join(' · ')}</div>
            <Badge tone={r.status === 'succeeded' ? 'ok' : r.status === 'failed' ? 'err' : 'info'}>{t(('job.status.' + r.status) as 'job.status.queued')}</Badge>
            {r.error && <div className="small err-text" dir="auto">{r.error.split('\n')[0]}</div>}
            {r.url && <ExtLink href={r.url} download>{t('rm.renders.download')}</ExtLink>}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function RemotionPage() {
  const { t, lang } = useI18n()
  useTitle(t('rm.title'))
  const act = useAction()
  const status = useQuery<RmStatus>('/remotion/status', { interval: (d) => (d && d.ready ? 20000 : 2500) })
  const kits = useQuery<{ kits: RmKit[]; default: string }>('/remotion/kits')
  const code = useQuery<RmCode>('/remotion/code')
  const renders = useQuery<RmRenders>('/remotion/renders', { interval: 8000 })
  const [tab, setTab] = useStored<TabKey>('rm.tab', 'preview')
  const [compId, setCompId] = useStored<string>('rm.comp', COMPOSITIONS[0].id)
  const [styleKey, setStyleKey] = useStored<string>('rm.style', '')
  const [size, setSize] = useStored<SizeId>('rm.size', 'landscape')
  const def = byId(compId) ?? COMPOSITIONS[0]
  // deep links for tests and bookmarks: /remotion?comp=Explainer&style=stop_motion&size=vertical&frame=120
  const qp = useMemo(() => new URLSearchParams(window.location.search), [])
  useEffect(() => {
    const c = qp.get('comp')
    if (c && byId(c)) setCompId(c)
    const st = qp.get('style')
    if (st) setStyleKey(st)
    const z = qp.get('size')
    if (z && z in SIZES) setSize(z as SizeId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // the preview opens on a frame where the text is already there (frame 0 of an entrance is empty); ?frame= overrides it
  const initialFrame = qp.get('frame') !== null ? Math.max(0, Number(qp.get('frame')) || 0) : 75
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const draft = drafts[def.id] ?? initialDraft(def, lang)
  const setDraft = (d: Draft) => setDrafts((all) => ({ ...all, [def.id]: d }))
  const playerRef = useRef<PlayerRef>(null)
  const runner = useJobRunner({ onFinished: () => renders.reload() })

  const list = kits.data?.kits ?? []
  const kit: RmKit | undefined = list.find((k) => k.key === styleKey) ?? list.find((k) => k.key === kits.data?.default) ?? list[0]
  const props = useMemo(() => propsOf(def, draft), [def, draft])
  const meta = useMemo(() => metaFor(def.id, { ...props, size }), [def, props, size])
  const inputProps = useMemo(() => ({ ...props, kit: (kit ?? undefined) as StyleKit | undefined, size, fontBase: 'page' }), [props, kit, size])

  // a language switch re-seeds the sample texts of compositions the owner has not edited
  useEffect(() => {
    setDrafts({})
  }, [lang])

  const render = (still?: number) => {
    if (!kit) return
    void act.run(() => runner.start(() => api.post('/remotion/render', { composition: def.id, props, style: kit.key, size, ...(still !== undefined ? { still } : {}) })), {
      success: t('rm.render.started'),
    })
  }

  const field = (f: CompositionDef['fields'][number]) => {
    const label = lang === 'en' ? f.en : f.fa
    if (f.type === 'text') return <TextField key={f.key} label={label} value={String(draft.values[f.key] ?? '')} onChange={(v) => setDraft({ ...draft, values: { ...draft.values, [f.key]: v } })} dir="auto" maxLength={400} />
    if (f.type === 'checkbox') return <CheckField key={f.key} label={label} checked={draft.values[f.key] !== false} onChange={(v) => setDraft({ ...draft, values: { ...draft.values, [f.key]: v } })} />
    if (f.type === 'select')
      return <SelectField key={f.key} label={label} value={String(draft.values[f.key] ?? '')} onChange={(v) => setDraft({ ...draft, values: { ...draft.values, [f.key]: v } })} options={(f.options ?? []).map((o) => ({ value: o.value, label: lang === 'en' ? o.en : o.fa }))} />
    return <AreaField key={f.key} label={label} rows={f.type === 'steps' ? 6 : 5} value={draft.texts[f.key] ?? ''} onChange={(v) => setDraft({ ...draft, texts: { ...draft.texts, [f.key]: v } })} dir="auto" />
  }

  const groups: { key: CompositionDef['group']; label: string }[] = [
    { key: 'titles', label: t('rm.group.titles') },
    { key: 'kinetic', label: t('rm.group.kinetic') },
    { key: 'explainers', label: t('rm.group.explainers') },
  ]
  const portrait = meta.height > meta.width

  return (
    <div className="stack" data-testid="rm-page">
      <PageHead title={t('rm.title')} />
      <p className="muted">{t('rm.intro')}</p>
      <Async q={status} skeleton={<CardSkeletons n={1} />}>{(s) => <SetupCard st={s} reload={status.reload} />}</Async>

      <Card title={t('rm.pick.title')}>
        <div className="stack">
          <div className="stack-sm" role="group" aria-label={t('rm.comp')}>
            {groups.map((g) => (
              <div key={g.key} className="row" style={{ gap: '0.5rem', alignItems: 'center' }}>
                <span className="small muted" style={{ minWidth: '7rem' }}>{g.label}</span>
                {COMPOSITIONS.filter((c) => c.group === g.key).map((c) => (
                  <Button key={c.id} size="sm" variant={c.id === def.id ? 'primary' : 'default'} aria-pressed={c.id === def.id} onClick={() => setCompId(c.id)} data-testid={'rm-comp-' + c.id}>{lang === 'en' ? c.en : c.fa}</Button>
                ))}
              </div>
            ))}
          </div>
          <p className="small" dir="auto">{lang === 'en' ? def.descEn : def.descFa}</p>
          <Async q={kits} skeleton={<CardSkeletons n={1} />}>
            {() => (
              <div className="stack-sm">
                <div className="strong">{t('rm.style')}</div>
                <p className="small muted">{t('rm.style_hint')}</p>
                <div className="grid-3" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(11rem, 1fr))', gap: '0.5rem', maxHeight: '15rem', overflow: 'auto' }} data-testid="rm-styles">
                  {list.map((k) => <KitChip key={k.key} k={k} lang={lang} active={kit?.key === k.key} onPick={() => setStyleKey(k.key)} />)}
                </div>
              </div>
            )}
          </Async>
        </div>
      </Card>

      <Tabs<TabKey> label={t('rm.tabs')} value={tab} onChange={setTab} tabs={[{ key: 'preview', label: t('rm.tab.preview') }, { key: 'code', label: t('rm.tab.code') }, { key: 'renders', label: t('rm.tab.renders'), badge: renders.data?.renders.length ? <Badge tone="info">{renders.data.renders.length}</Badge> : undefined }]} />

      {tab === 'preview' && (
        <div className="grid-2" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(20rem, 1fr))', gap: '1rem', alignItems: 'start' }}>
          <Card title={t('rm.edit.title')}>
            <div className="stack">
              {def.fields.map(field)}
              <SelectField label={t('rm.size')} value={size} onChange={(v) => setSize(v as SizeId)} options={(Object.keys(SIZES) as SizeId[]).map((k) => ({ value: k, label: lang === 'en' ? SIZES[k].en : SIZES[k].fa }))} />
              <div className="row">
                <Button variant="primary" icon="film" busy={act.busy || runner.busy} disabled={!kit || !!runner.busy} onClick={() => render()} data-testid="rm-render">{t('rm.render.video')}</Button>
                <Button icon="image" disabled={!kit || runner.busy} onClick={() => render(playerRef.current?.getCurrentFrame() ?? 0)} data-testid="rm-still">{t('rm.render.still')}</Button>
              </div>
              {!status.data?.ready && <Notice tone="info" icon="clock">{t('rm.render.needs_setup')}</Notice>}
              {runner.job && <JobView job={runner.job} offline={runner.offline} />}
              {runner.result?.url && (
                <div className="stack-sm" data-testid="rm-result">
                  <div className="strong">{t('rm.render.result')}</div>
                  {runner.result.kind === 'mp4' ? <video src={runner.result.url} controls style={{ width: '100%', maxWidth: portrait ? 280 : 560, borderRadius: 8 }} /> : <img src={runner.result.url} alt="" style={{ width: '100%', maxWidth: 560, borderRadius: 8 }} />}
                  <ExtLink href={runner.result.url} download>{t('rm.renders.download')}</ExtLink>
                </div>
              )}
            </div>
          </Card>
          <Card title={t('rm.preview.title')} actions={<span className="small muted ltr" dir="ltr">{meta.width}×{meta.height} · {FPS} fps · {(meta.durationInFrames / FPS).toFixed(1)} s</span>}>
            <div className="stack-sm">
              <div dir="ltr" data-testid="rm-player" style={{ width: '100%', maxWidth: portrait ? 300 : '100%', margin: '0 auto' }}>
                {kit ? (
                  <Player
                    ref={playerRef}
                    key={def.id + size}
                    initialFrame={Math.min(initialFrame, Math.max(0, meta.durationInFrames - 1))}
                    component={def.component}
                    inputProps={inputProps}
                    durationInFrames={meta.durationInFrames}
                    compositionWidth={meta.width}
                    compositionHeight={meta.height}
                    fps={meta.fps}
                    controls
                    loop
                    clickToPlay
                    acknowledgeRemotionLicense
                    style={{ width: '100%', borderRadius: 8, overflow: 'hidden' }}
                  />
                ) : <Empty icon="film" title={t('rm.preview.no_style')} />}
              </div>
              <p className="small muted">{t('rm.preview.hint')}</p>
            </div>
          </Card>
        </div>
      )}
      {tab === 'code' && <Card title={t('rm.code.title', { name: def.id })}><CodeView def={def} code={code.data} /></Card>}
      {tab === 'renders' && <Card title={t('rm.renders.title')}><Renders data={renders.data} /></Card>}
    </div>
  )
}
