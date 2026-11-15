import { Player, Thumbnail, type PlayerRef } from '@remotion/player'
import { Component, memo, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { api } from '../api/client'
import { JobView } from '../components/domain'
import { Async, Badge, Button, Card, CardSkeletons, CheckField, Empty, ExtLink, Notice, NumberField, PageHead, Progress, Segmented, SelectField, Tabs, TextField, AreaField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useStored, useTitle } from '../hooks'
import { useI18n } from '../i18n'
import { COMPOSITIONS, FPS, SIZES, byId, metaFor, type CompositionDef, type SizeId } from '../../../remotion/src/catalog'
import { PLAN_TEMPLATES, templatePlan } from '../../../remotion/src/components/defs'
import type { StyleKit } from '../../../remotion/src/kit/theme'
import type { MotionNarrationPlan, MotionValidate, RmCode, RmKit, RmRenders, RmStatus } from './types'

type TabKey = 'preview' | 'code' | 'renders'
type Values = Record<string, any>
type Draft = { values: Values; texts: Record<string, string> }
type Field = CompositionDef['fields'][number]
type Cols = NonNullable<Field['cols']>

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

const DIGITS = '۰۱۲۳۴۵۶۷۸۹'
const ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩'
const toLatinDigits = (v: string) => v.replace(/[۰-۹٠-٩]/g, (d) => String(Math.max(DIGITS.indexOf(d), ARABIC_DIGITS.indexOf(d))))

/** objects <-> text lines «a | b | c» (one object per line, one column per field of `cols`) */
const rowsToText = (rows: Record<string, any>[] | undefined, cols: Cols) =>
  (rows ?? []).map((r) => cols.map((c) => String(r[c.key] ?? '')).join(' | ').replace(/(\s*\|\s*)+$/, '')).join('\n')
const textToRows = (text: string, cols: Cols) =>
  text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const parts = l.split('|').map((x) => x.trim())
      const o: Record<string, any> = {}
      cols.forEach((c, i) => {
        const v = parts[i]
        if (v !== undefined && v !== '') o[c.key] = c.kind === 'number' ? Number(toLatinDigits(v)) || 0 : v
      })
      return o
    })
    .filter((o) => Object.keys(o).length)

/** the scene plan the JSON box holds: the parsed plan, or why it cannot be read */
function parsePlan(text: string): { value?: Values; error?: string } {
  try {
    const v = JSON.parse(text)
    return v && typeof v === 'object' && !Array.isArray(v) ? { value: v } : { error: 'a JSON object is needed' }
  } catch (e) {
    return { error: String((e as Error).message || e) }
  }
}

function initialDraft(def: CompositionDef, lang: 'fa' | 'en'): Draft {
  const d = def.defaults(lang) as Values
  const values: Values = {}
  const texts: Record<string, string> = {}
  for (const f of def.fields) {
    if (f.type === 'lines') texts[f.key] = ((d[f.key] as string[]) ?? []).join('\n')
    else if (f.type === 'steps') texts[f.key] = stepsToText(d[f.key])
    else if (f.type === 'rows') texts[f.key] = rowsToText(d[f.key], f.cols ?? [])
    else if (f.type === 'json') texts[f.key] = JSON.stringify(d[f.key], null, 2)
    else values[f.key] = d[f.key] ?? (f.type === 'checkbox' ? false : '')
  }
  return { values, texts }
}

function propsOf(def: CompositionDef, draft: Draft, lastPlan?: Values): Values {
  const p: Values = { ...draft.values }
  for (const f of def.fields) {
    if (f.type === 'lines') p[f.key] = draft.texts[f.key].split('\n').filter((l) => l.trim())
    if (f.type === 'steps') p[f.key] = textToSteps(draft.texts[f.key])
    if (f.type === 'rows') p[f.key] = textToRows(draft.texts[f.key], f.cols ?? [])
    if (f.type === 'json') p[f.key] = parsePlan(draft.texts[f.key]).value ?? lastPlan
    if (f.type === 'number' && p[f.key] !== undefined && p[f.key] !== '') p[f.key] = Number(p[f.key])
    if ((f.type === 'text' || f.type === 'textarea') && p[f.key] === '') delete p[f.key]
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

/** A style's picture must never take the page down: a composition that fails for one look shows the palette strip instead. */
class ThumbBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

/** True once the element has come near the screen (and for good): the 116 pictures are made only for the cards that are looked at. */
function useSeen<T extends Element>(): [RefObject<T>, boolean] {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(true)
      return
    }
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && (setSeen(true), io.disconnect()), { rootMargin: '120px' })
    io.observe(el)
    return () => io.disconnect()
  }, [seen])
  return [ref, seen]
}

/** One look as a card: the chosen composition drawn in THIS look (a real frame of it, made only when the card is near the screen), then the name and how it moves. */
const KitChip = memo(function KitChip({ k, active, onPick, lang, def, sample }: { k: RmKit; active: boolean; onPick: () => void; lang: 'fa' | 'en'; def: CompositionDef; sample: Values }) {
  const p = k.palette
  const [ref, seen] = useSeen<HTMLButtonElement>()
  const meta = useMemo(() => metaFor(def.id, { ...sample, size: 'landscape' }), [def.id, sample])
  const inputProps = useMemo(() => ({ ...sample, kit: k as unknown as StyleKit, size: 'landscape' as const, fontBase: 'page' }), [sample, k])
  return (
    <button ref={ref} type="button" className={'cur-pkg rm-kit' + (active ? ' picked' : '')} aria-pressed={active} onClick={onPick} data-testid={'rm-style-' + k.key} style={{ textAlign: 'start', cursor: 'pointer', padding: '0.4rem 0.5rem' }}>
      <div className="rm-thumb" dir="ltr" aria-hidden="true" style={{ background: p.background }}>
        {seen && (
          <ThumbBoundary>
            <Thumbnail component={def.component} compositionWidth={meta.width} compositionHeight={meta.height} frameToDisplay={Math.min(75, meta.durationInFrames - 1)} durationInFrames={meta.durationInFrames} fps={meta.fps} inputProps={inputProps} style={{ width: '100%', display: 'block' }} />
          </ThumbBoundary>
        )}
        <div className="rm-thumb-chips">
          {[p.background, p.primary, p.secondary, p.accent, p.highlight].map((c, i) => <span key={i} style={{ background: c }} />)}
        </div>
      </div>
      <div className="strong" dir="auto">{(lang === 'en' ? k.name_en : k.name_fa) || k.name}</div>
      <div className="small muted" dir="auto">{(lang === 'en' ? k.animation_en : k.animation_fa) || k.animation}</div>
    </button>
  )
})

function CodeView({ def, code }: { def: CompositionDef; code: RmCode | undefined }) {
  const { t } = useI18n()
  const [file, setFile] = useState<string>('')
  const [copied, setCopied] = useState(false)
  const own = code?.compositions.find((c) => c.id === def.id)
  const comp = own?.same_as ? code?.compositions.find((c) => c.id === own.same_as) : own      // the library's compositions all play ScenePlan: its code is shown
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
        <Button size="sm" variant={file ? 'default' : 'primary'} onClick={() => setFile('')}>{(comp?.file ?? def.file).split('/').pop()}</Button>
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
            <div className="small muted">{[r.style, r.size && (lang === 'en' ? SIZES[r.size as SizeId]?.en : SIZES[r.size as SizeId]?.fa), r.width && `${r.width}×${r.height}`, r.duration_sec ? t('rm.renders.length', { x: f.duration(r.duration_sec) }) : '', r.bytes && f.bytes(r.bytes)].filter(Boolean).join(' · ')}</div>
            {r.render_seconds ? <div className="small muted">{t('rm.renders.took', { x: f.duration(r.render_seconds) })}</div> : null}
            <Badge tone={r.status === 'succeeded' ? 'ok' : r.status === 'failed' ? 'err' : 'info'}>{t(('job.status.' + r.status) as 'job.status.queued')}</Badge>
            {r.error && <div className="small err-text" dir="auto">{r.error.split('\n')[0]}</div>}
            {r.url && <ExtLink href={r.url} download>{t('rm.renders.download')}</ExtLink>}
          </div>
        </div>
      ))}
    </div>
  )
}

/** The rule checks of a scene plan, live: the cleaned plan's length, the silent corrections and what the QA would fix (no browser needed). */
function PlanChecks({ plan, lang }: { plan: Values | undefined; lang: 'fa' | 'en' }) {
  const { t } = useI18n()
  const [res, setRes] = useState<MotionValidate | { error: string } | null>(null)
  useEffect(() => {
    if (!plan) return
    let live = true
    const id = window.setTimeout(() => {
      api.post<MotionValidate>('/motion/plan/validate', { spec: plan }).then((r) => live && setRes(r)).catch((e) => live && setRes({ error: String(e?.message ?? e) }))
    }, 600)
    return () => {
      live = false
      window.clearTimeout(id)
    }
  }, [plan])
  if (!res) return null
  if ('error' in res) return <Notice tone="err" icon="alert">{res.error}</Notice>
  const bad = res.findings.filter((f) => f.severity !== 'info')
  return (
    <div className="stack-sm" data-testid="rm-plan-checks">
      <div className="row" style={{ gap: '0.5rem', flexWrap: 'wrap' }}>
        <Badge tone={bad.length ? 'warn' : 'ok'}>{lang === 'en' ? res.summary_en : res.summary_fa}</Badge>
        <span className="small muted">{t('rm.plan.length', { x: res.timeline.total.toFixed(1) })}</span>
      </div>
      {res.notes.map((n, i) => <p key={'n' + i} className="small muted" dir="auto">{lang === 'en' ? n.en : n.fa}</p>)}
      {res.findings.map((f, i) => <p key={i} className="small" dir="auto"><Badge tone={f.severity === 'error' ? 'err' : f.severity === 'warn' ? 'warn' : 'neutral'}>{lang === 'en' ? f.label_en : f.label}</Badge> {lang === 'en' ? f.message_en : f.message}</p>)}
    </div>
  )
}

/** Plan from words: the narration of a shot becomes a plan by the deterministic builder (no model), to start from. */
function PlanFromText({ lang, style, size, onPlan }: { lang: 'fa' | 'en'; style: string; size: SizeId; onPlan: (spec: Values) => void }) {
  const { t } = useI18n()
  const act = useAction()
  const [text, setText] = useState('')
  const [secs, setSecs] = useState<number | null>(10)
  const make = () =>
    void act.run(async () => {
      const r = await api.post<MotionNarrationPlan>('/motion/plan/fallback', { narration: text, seconds: secs ?? 10, style, size, lang })
      onPlan(r.spec)
    })
  return (
    <div className="stack-sm" data-testid="rm-plan-text">
      <AreaField label={t('rm.plan.text')} hint={t('rm.plan.text_hint')} rows={3} value={text} onChange={setText} dir="auto" />
      <div className="row">
        <NumberField label={t('rm.plan.seconds')} min={2} max={120} step={1} value={secs} onChange={setSecs} />
        <Button icon="spark" busy={act.busy} disabled={!text.trim()} onClick={make} data-testid="rm-plan-make">{t('rm.plan.make')}</Button>
      </div>
    </div>
  )
}

export default function RemotionPage() {
  const { t, lang } = useI18n()
  useTitle(t('rm.title'))
  const act = useAction()
  const status = useQuery<RmStatus>('/remotion/status', { interval: (d) => (d && d.ready ? 20000 : 2500) })
  const kits = useQuery<{ kits: RmKit[]; default: string; groups?: { key: string; fa: string; en: string }[] }>('/remotion/kits')
  const [tab, setTab] = useStored<TabKey>('rm.tab', 'preview')
  // the code of the compositions (54 KB) is fetched when the code tab is opened for the first time, not with the page; the list of renders is polled only on its own tab
  const [codeWanted, setCodeWanted] = useState(tab === 'code')
  useEffect(() => {
    if (tab === 'code') setCodeWanted(true)
  }, [tab])
  const code = useQuery<RmCode>(codeWanted ? '/remotion/code' : null)
  const renders = useQuery<RmRenders>('/remotion/renders', { interval: () => (tab === 'renders' ? 8000 : false) })
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
  const lastPlan = useRef<Values | undefined>(undefined)

  const all = kits.data?.kits ?? []
  const styleGroups = (kits.data?.groups ?? []).filter((g) => all.some((k) => k.group === g.key))
  const [styleGroup, setStyleGroup] = useState('all')
  const list = styleGroup === 'all' ? all : all.filter((k) => k.group === styleGroup)
  const kit: RmKit | undefined = all.find((k) => k.key === styleKey) ?? all.find((k) => k.key === kits.data?.default) ?? all[0]
  const props = useMemo(() => propsOf(def, draft, lastPlan.current), [def, draft])
  if (def.id === 'ScenePlan' && props.spec) lastPlan.current = props.spec
  const planError = def.id === 'ScenePlan' ? parsePlan(draft.texts.spec ?? '').error : undefined
  // every style card shows the composition with its OWN sample texts (not the ones being typed): the cards do not redraw at every keystroke
  const sample = useMemo(() => propsOf(def, initialDraft(def, lang)), [def, lang])
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

  const field = (f: Field) => {
    const label = lang === 'en' ? f.en : f.fa
    const setValue = (v: unknown) => setDraft({ ...draft, values: { ...draft.values, [f.key]: v } })
    const setText = (v: string) => setDraft({ ...draft, texts: { ...draft.texts, [f.key]: v } })
    if (f.type === 'text') return <TextField key={f.key} label={label} value={String(draft.values[f.key] ?? '')} onChange={setValue} dir="auto" maxLength={400} />
    if (f.type === 'textarea') return <AreaField key={f.key} label={label} rows={3} value={String(draft.values[f.key] ?? '')} onChange={setValue} dir="auto" />
    if (f.type === 'number') return <NumberField key={f.key} label={label} min={f.min} max={f.max} step={1} value={draft.values[f.key] === '' || draft.values[f.key] === undefined ? null : Number(draft.values[f.key])} onChange={(v) => setValue(v ?? '')} />
    if (f.type === 'checkbox') return <CheckField key={f.key} label={label} checked={draft.values[f.key] === true} onChange={setValue} />
    if (f.type === 'select')
      return <SelectField key={f.key} label={label} value={String(draft.values[f.key] ?? '')} onChange={setValue} options={(f.options ?? []).map((o) => ({ value: o.value, label: lang === 'en' ? o.en : o.fa }))} />
    if (f.type === 'json')
      return (
        <div key={f.key} className="stack-sm">
          <AreaField label={label} rows={16} value={draft.texts[f.key] ?? ''} onChange={setText} dir="ltr" hint={t('rm.plan.json_hint')} />
          {planError && <Notice tone="err" icon="alert">{t('rm.plan.json_bad')} <span className="ltr" dir="ltr">{planError}</span></Notice>}
        </div>
      )
    return <AreaField key={f.key} label={label} rows={f.type === 'steps' || f.type === 'rows' ? 6 : 5} value={draft.texts[f.key] ?? ''} onChange={setText} dir="auto" hint={f.type === 'rows' ? t('rm.rows_hint') : undefined} />
  }

  const groups: { key: CompositionDef['group']; label: string }[] = [
    { key: 'titles', label: t('rm.group.titles') },
    { key: 'kinetic', label: t('rm.group.kinetic') },
    { key: 'explainers', label: t('rm.group.explainers') },
    { key: 'plan', label: t('rm.group.plan') },
    { key: 'scene', label: t('rm.group.scene') },
    { key: 'data', label: t('rm.group.data') },
    { key: 'text', label: t('rm.group.text') },
  ]
  const portrait = meta.height > meta.width
  const setPlanText = (spec: Values) => setDraft({ ...draft, texts: { ...draft.texts, spec: JSON.stringify(spec, null, 2) } })

  const picker = (
    <Card title={t('rm.pick.title')}>
      <div className="stack">
        <div className="stack-sm" role="group" aria-label={t('rm.comp')}>
          {groups.map((g, gi) => (
            <div key={g.key} className="row" style={{ gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              {gi === 3 && <hr style={{ width: '100%', border: 0, borderTop: '1px solid var(--border, rgba(128,128,128,.3))', margin: '0.25rem 0' }} />}
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
              {styleGroups.length > 0 && (
                <Segmented<string> label={t('rm.style_groups')} value={styleGroup} onChange={setStyleGroup} options={[{ key: 'all', label: t('rm.style_all') }, ...styleGroups.map((g) => ({ key: g.key, label: lang === 'en' ? g.en : g.fa }))]} />
              )}
              <div className="rm-styles" data-testid="rm-styles">
                {list.map((k) => <KitChip key={k.key} k={k} lang={lang} active={kit?.key === k.key} onPick={() => setStyleKey(k.key)} def={def} sample={sample} />)}
              </div>
            </div>
          )}
        </Async>
      </div>
    </Card>
  )

  const edit = (
    <Card title={t('rm.edit.title')}>
      <div className="stack">
        {def.id === 'ScenePlan' && (
          <>
            <SelectField label={t('rm.plan.template')} value="" onChange={(v) => v && setPlanText(templatePlan(v, lang, size))} options={[{ value: '', label: t('rm.plan.template_pick') }, ...PLAN_TEMPLATES.map((x) => ({ value: x.id, label: lang === 'en' ? x.en : x.fa }))]} />
            <PlanFromText lang={lang} style={kit?.key ?? ''} size={size} onPlan={setPlanText} />
          </>
        )}
        {def.fields.map(field)}
        {def.id === 'ScenePlan' && <PlanChecks plan={props.spec ? { ...props.spec, style: kit?.key ?? '', size } : undefined} lang={lang} />}
        <SelectField label={t('rm.size')} value={size} onChange={(v) => setSize(v as SizeId)} options={(Object.keys(SIZES) as SizeId[]).map((k) => ({ value: k, label: lang === 'en' ? SIZES[k].en : SIZES[k].fa }))} />
        <div className="row">
          <Button variant="primary" icon="film" busy={act.busy || runner.busy} disabled={!kit || !!runner.busy || !!planError} onClick={() => render()} data-testid="rm-render">{t('rm.render.video')}</Button>
          <Button icon="image" disabled={!kit || runner.busy || !!planError} onClick={() => render(playerRef.current?.getCurrentFrame() ?? 0)} data-testid="rm-still">{t('rm.render.still')}</Button>
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
  )

  // the live preview is in the second column and stays in view while the owner scrolls through the styles and the texts (on a phone it sits on top, small)
  const preview = (
    <aside className="rm-side" data-testid="rm-side" style={{ ['--rm-aspect' as string]: String(meta.width / meta.height) }}>
      <Card title={t('rm.preview.title')} actions={<span className="small muted ltr" dir="ltr">{meta.width}×{meta.height} · {meta.fps ?? FPS} fps · {(meta.durationInFrames / (meta.fps ?? FPS)).toFixed(1)} s</span>}>
        <div className="stack-sm">
          <div dir="ltr" data-testid="rm-player" className={'rm-player ' + (portrait ? 'portrait' : 'landscape')}>
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
          {kit && <p className="small strong" dir="auto" data-testid="rm-chosen">{t('rm.chosen_style', { name: (lang === 'en' ? kit.name_en : kit.name_fa) || kit.name })}</p>}
          <p className="small muted rm-hint">{t('rm.preview.hint')}</p>
        </div>
      </Card>
    </aside>
  )

  return (
    <div className="stack" data-testid="rm-page">
      <PageHead title={t('rm.title')} />
      <p className="muted">{t('rm.intro')}</p>
      <Async q={status} skeleton={<CardSkeletons n={1} />}>{(s) => <SetupCard st={s} reload={status.reload} />}</Async>

      <div className="rm-split">
        <div className="stack rm-main">
          {picker}
          <Tabs<TabKey> label={t('rm.tabs')} value={tab} onChange={setTab} tabs={[{ key: 'preview', label: t('rm.tab.preview') }, { key: 'code', label: t('rm.tab.code') }, { key: 'renders', label: t('rm.tab.renders'), badge: renders.data?.renders.length ? <Badge tone="info">{renders.data.renders.length}</Badge> : undefined }]} />
          {tab === 'preview' && edit}
          {tab === 'code' && <Card title={t('rm.code.title', { name: def.id })}><Async q={code} skeleton={<CardSkeletons n={1} />}>{(c) => <CodeView def={def} code={c} />}</Async></Card>}
          {tab === 'renders' && <Card title={t('rm.renders.title')}><Renders data={renders.data} /></Card>}
        </div>
        {preview}
      </div>
    </div>
  )
}
