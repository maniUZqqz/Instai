import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, errorText } from '../api/client'
import { useConfirm } from '../components/feedback'
import { JobView } from '../components/domain'
import type { Job } from '../api/types'
import { Badge, Button, Card, CheckField, ChoiceGrid, ExtLink, Loading, Notice, NumberField, SelectField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery } from '../hooks'
import { currentLang, translate, useI18n } from '../i18n'
import { usePL, word } from '../pipeline/kit'
import type { CCover, CContext, CIdea, CIdeas, CMakeResponse, CMeta, CPreview, CSpec, CStyle, CoverTarget } from './types'

const EXPRESSIONS = ['neutral', 'happy', 'laugh', 'sad', 'angry', 'scared', 'surprised', 'smirk']
const LOGO_POS = ['auto', 'tl', 'tr', 'bl', 'br', 'bc', 'tc']
const SIDES = ['auto', 'left', 'right', 'center']
const TEXTURES = ['halftone', 'rays', 'grid', 'stripes', 'grain']

async function uploadPicture(page: number, kind: 'logo' | 'subject' | 'background', file: File): Promise<number> {
  const fd = new FormData()
  fd.append('page', String(page))
  fd.append('kind', kind)
  fd.append('file', file)
  const res = await fetch('/api/covers/upload', { method: 'POST', body: fd, headers: { 'X-Lang': currentLang() } })
  const data = (await res.json().catch(() => null)) as { asset?: { id: number }; error?: { code?: string; message?: string } } | null
  if (!res.ok || !data?.asset) throw new ApiError(data?.error?.code ?? 'error', data?.error?.message ?? translate('error.generic'), res.status)
  return data.asset.id
}

function targetBody(t: CoverTarget) {
  return { page: t.page, episode: t.episode ?? undefined, series: t.series ?? undefined, kind: t.kind }
}

function targetQuery(t: CoverTarget, extra: Record<string, string> = {}) {
  const q = new URLSearchParams()
  if (t.episode) q.set('episode', String(t.episode))
  else if (t.series) q.set('series', String(t.series))
  else q.set('page', String(t.page))
  if (t.kind && !t.episode) q.set('kind', t.kind)
  for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v)
  return q.toString()
}

/** A colour that can be left "automatic" (empty). */
function ColorPick({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const { t } = useI18n()
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="row nw">
        <input type="color" value={value || '#888888'} aria-label={label} onChange={(e) => onChange(e.target.value)} style={{ width: '3rem', height: '2.2rem', padding: 0 }} />
        {value ? (
          <Button size="sm" variant="ghost" onClick={() => onChange('')}>
            {t('cv.color_clear')}
          </Button>
        ) : (
          <span className="small muted">{t('cv.color_auto')}</span>
        )}
      </div>
    </div>
  )
}

function UploadButton({ page, kind, label, onDone }: { page: number; kind: 'logo' | 'subject' | 'background'; label: string; onDone: (id: number) => void }) {
  const { t } = useI18n()
  const ref = useRef<HTMLInputElement>(null)
  const act = useAction()
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file) return
          const id = await act.run(() => uploadPicture(page, kind, file), { success: t('cv.upload_ok') })
          if (id) onDone(id)
        }}
      />
      <Button icon="upload" wrap busy={act.busy} onClick={() => ref.current?.click()}>
        {label}
      </Button>
    </>
  )
}

/** The cover editor of one target (an episode, a series or the channel): layout, text, colours, character, background, logo, ideas, a live preview with safe-zone guides, the A/B versions and the history. */
export function CoverStudio({ target, onChanged }: { target: CoverTarget; onChanged?: () => void }) {
  const { t, tr, f } = useI18n()
  const { pick, lang } = usePL()
  const confirm = useConfirm()
  const meta = useQuery<CMeta>('/covers/meta')
  const [textLang, setTextLang] = useState<'' | 'fa' | 'en'>('')
  const [fmt, setFmt] = useState('')
  const ctx = useQuery<CContext>(`/covers/context?${targetQuery(target, { lang: textLang, fmt })}`)
  const [spec, setSpec] = useState<CSpec | null>(null)
  const [parent, setParent] = useState<number | null>(null)
  const [guides, setGuides] = useState(true)
  const [variants, setVariants] = useState('3')
  const [useAsCover, setUseAsCover] = useState(true)
  const [about, setAbout] = useState(false)
  const covers = useQuery<CCover[]>(`/covers?${targetQuery(target)}`, {
    interval: (d) => (d?.some((c) => c.status === 'waiting_bg' || c.status === 'rendering' || c.status === 'draft') ? 4000 : false),
  })
  const ideasQ = useAction()
  const [ideas, setIdeas] = useState<CIdeas | null>(null)
  const [useAi, setUseAi] = useState(true)
  const [pv, setPv] = useState<CPreview | null>(null)
  const [pvBusy, setPvBusy] = useState(false)
  const [pvErr, setPvErr] = useState('')
  const maker = useJobRunner({ onFinished: () => { covers.reload(); onChanged?.() } })
  const act = useAction()

  // a new context (another target, language or format) starts a fresh spec
  useEffect(() => {
    if (ctx.data) {
      setSpec(ctx.data.spec)
      setParent(null)
    }
  }, [ctx.data])
  const specKey = useMemo(() => JSON.stringify(spec), [spec])
  const tKey = targetQuery(target)
  useEffect(() => {
    if (!spec) return
    let alive = true
    const timer = window.setTimeout(async () => {
      setPvBusy(true)
      try {
        const r = await api.post<CPreview>('/covers/preview', { ...targetBody(target), spec, side: 760 })
        if (alive) {
          setPv(r)
          setPvErr('')
        }
      } catch (e) {
        if (alive) setPvErr(errorText(e))
      } finally {
        if (alive) setPvBusy(false)
      }
    }, 450)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, tKey])

  if (meta.error || ctx.error) return <Notice tone="err">{t('cv.error') + errorText(meta.error ?? ctx.error)}</Notice>
  if (!meta.data || !ctx.data || !spec) return <Loading label={t('cv.loading')} />
  const m = meta.data
  const c = ctx.data
  const style = m.styles.find((s) => s.key === spec.style) as CStyle
  const format = m.formats.find((x) => x.key === spec.format) ?? m.formats[0]
  const arche = m.archetypes.find((a) => a.style === spec.style)
  const set = (fn: (s: CSpec) => CSpec) => setSpec((s) => (s ? fn(s) : s))
  const setContent = (key: string, v: string) => set((s) => ({ ...s, content: { ...s.content, [key]: v } }))
  const subjectRow = c.subjects.find((x) => x.id === spec.subject.character)
  const latest = covers.data?.[0]
  const waiting = covers.data?.some((x) => x.status === 'waiting_bg')

  const applyIdea = (i: CIdea) => {
    set((s) => ({ ...s, style: i.style, content: { ...s.content, ...i.spec_patch.content }, colors: { ...s.colors, mood: i.mood || s.colors.mood } }))
    setAbout(false)
  }
  const suggest = async () => {
    const r = await ideasQ.run(() => api.post<CIdeas>('/covers/ideas', { ...targetBody(target), format: spec.format, lang: spec.lang, use_ai: useAi, count: 6, variation: ideas ? Math.floor(Math.random() * 90) : 0 }))
    if (r) setIdeas(r)
  }
  const make = async () => {
    const r = await maker.start(() => api.post<CMakeResponse>('/covers', { ...targetBody(target), spec, variants: Number(variants), use: useAsCover, parent: parent ?? undefined }))
    if (r) covers.reload()
  }
  const useVersion = async (cv: CCover, letter: string) => {
    const v = cv.variants.find((x) => x.letter === letter)
    if (!v) return
    const r = await act.run(() => api.post<CCover>(`/covers/${cv.id}/use`, { variant: v.index }), { success: t('cv.version_used') })
    if (r) {
      covers.reload()
      onChanged?.()
    }
  }
  const more = async (cv: CCover) => {
    const r = await maker.start(() => api.post<{ job: Job }>(`/covers/${cv.id}/more`, { count: 2 }))
    if (r) covers.reload()
  }
  const editAgain = async (cv: CCover) => {
    const full = await act.run(() => api.get<CCover>(`/covers/${cv.id}`))
    if (!full?.spec) return
    setSpec(full.spec)
    setParent(cv.id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const remove = async (cv: CCover) => {
    if (!(await confirm({ message: t('cv.history_delete_confirm'), danger: true, confirmLabel: t('cv.history_delete') }))) return
    await act.run(async () => {
      await api.del(`/covers/${cv.id}`)
      covers.reload()
      onChanged?.()
    }, { success: t('cv.history_deleted') })
  }
  const recommended = (s: CStyle) => s.formats.includes(spec.format)

  return (
    <div className="stack">
      <div className="cv-layout">
        <div className="stack cv-controls">
          <Card title={t('cv.sec.format')}>
            <div className="stack">
              <div className="stack">
                <SelectField
                  data-testid="cv-format"
                  label={t('cv.format')}
                  value={spec.format}
                  onChange={(v) => set((s) => ({ ...s, format: v }))}
                  options={m.formats.map((x) => ({ value: x.key, label: `${pick(x, 'title')} — ${t('cv.format_size', { w: x.width, h: x.height, aspect: x.aspect })}` }))}
                />
                <SelectField
                  label={t('cv.lang')}
                  value={spec.lang}
                  hint={t('cv.lang_hint')}
                  onChange={(v) => {
                    setTextLang(v as 'fa' | 'en')
                    setFmt(spec.format)
                  }}
                  options={[{ value: 'fa', label: t('cv.lang_fa') }, { value: 'en', label: t('cv.lang_en') }]}
                />
              </div>
              <p className="small muted">
                {pick(format, 'note')} {format.max_kb ? '· ' + t('cv.max_kb', { kb: format.max_kb }) : ''}
              </p>
              <p className="small muted">{t('cv.approx')}</p>
            </div>
          </Card>

          <Card title={t('cv.sec.layout')}>
            <div className="stack">
              <div className="scroll-box">
              <ChoiceGrid
                legend={t('cv.layout_pick')}
                name="cv-style"
                value={spec.style}
                onChange={(v) => set((s) => ({ ...s, style: v }))}
                options={m.styles.map((s) => ({
                  value: s.key,
                  title: pick(s, 'title'),
                  text: pick(s, 'short'),
                  extra: (
                    <span className="row" style={{ gap: '0.3rem' }}>
                      {!recommended(s) && <Badge tone="warn">{t('cv.layout_off')}</Badge>}
                      {s.origin === 'instai' && <Badge tone="primary">{t('cv.layout_new')}</Badge>}
                    </span>
                  ),
                }))}
              />
              </div>
              <Button size="sm" variant="ghost" onClick={() => setAbout((a) => !a)}>
                {t('cv.layout_about')}
              </Button>
              {about && arche && (
                <div className="stack-sm small">
                  <p>{pick(style, 'pattern')}</p>
                  <p><strong>{t('cv.why')}:</strong> {pick(arche, 'why')}</p>
                  <p><strong>{t('cv.dos')}:</strong> {(lang === 'fa' ? arche.dos_fa : arche.dos_en).join(lang === 'fa' ? '، ' : ', ')}</p>
                  <p><strong>{t('cv.donts')}:</strong> {(lang === 'fa' ? arche.donts_fa : arche.donts_en).join(lang === 'fa' ? '، ' : ', ')}</p>
                  <p><strong>{t('cv.text_rule')}:</strong> {pick(arche, 'text_rule')}</p>
                  {style.tips.length > 0 && <p><strong>{t('cv.tips')}:</strong> {style.tips.map((x) => pick(x)).join(' ')}</p>}
                </div>
              )}
            </div>
          </Card>

          <Card title={t('cv.sec.text')}>
            <div className="stack">
              {style.fields.map((fl) => (
                <TextField key={fl.key} label={pick(fl, 'label')} value={spec.content[fl.key] ?? ''} maxLength={m.limits[fl.key]} onChange={(v) => setContent(fl.key, v)} />
              ))}
              <TextField label={t('cv.channel_name')} value={spec.content.channel ?? ''} maxLength={m.limits.channel} onChange={(v) => setContent('channel', v)} hint={t('cv.channel_hint')} />
              <p className="small muted">{t('cv.text_hint')}</p>
            </div>
          </Card>

          <Card title={t('cv.sec.colors')}>
            <div className="stack">
              <div className="grid-2">
                <SelectField
                  label={t('cv.mood')}
                  value={spec.colors.mood}
                  onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, mood: v } }))}
                  options={[{ value: '', label: t('cv.mood_auto') }, ...m.moods.map((x) => ({ value: x.key, label: pick(x) }))]}
                />
                <SelectField
                  label={t('cv.font')}
                  value={spec.font}
                  onChange={(v) => set((s) => ({ ...s, font: v }))}
                  options={[{ value: 'auto', label: t('cv.font_auto') }, ...m.fonts.map((x) => ({ value: x.key, label: pick(x, 'label') }))]}
                />
              </div>
              <CheckField label={t('cv.use_look')} checked={spec.colors.use_brand} onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, use_brand: v } }))} />
              <div className="row">
                <ColorPick label={t('cv.color_primary')} value={spec.colors.primary} onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, primary: v } }))} />
                <ColorPick label={t('cv.color_secondary')} value={spec.colors.secondary} onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, secondary: v } }))} />
                <ColorPick label={t('cv.color_accent')} value={spec.colors.accent} onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, accent: v } }))} />
              </div>
              <NumberField label={t('cv.variation')} min={0} max={7} step={1} value={spec.colors.variation} onChange={(v) => set((s) => ({ ...s, colors: { ...s.colors, variation: v ?? 0 } }))} />
            </div>
          </Card>

          <Card title={t('cv.sec.character')}>
            <div className="stack">
              <SelectField
                label={t('cv.character')}
                value={spec.subject.character ? String(spec.subject.character) : ''}
                onChange={(v) => set((s) => ({ ...s, subject: { ...s.subject, character: v ? Number(v) : null, asset: null } }))}
                options={[{ value: '', label: t('cv.character_none') }, ...c.subjects.map((x) => ({ value: String(x.id), label: `${x.name} · ${t('cv.source.' + x.source)}` }))]}
              />
              {style.needs_second && (
                <SelectField
                  label={t('cv.character_second')}
                  value={spec.subject2.character ? String(spec.subject2.character) : ''}
                  onChange={(v) => set((s) => ({ ...s, subject2: { ...s.subject2, character: v ? Number(v) : null, asset: null } }))}
                  options={[{ value: '', label: t('cv.character_none') }, ...c.subjects.map((x) => ({ value: String(x.id), label: `${x.name} · ${t('cv.source.' + x.source)}` }))]}
                />
              )}
              <div className="grid-2">
                {subjectRow?.source === 'stick' && (
                  <SelectField
                    label={t('cv.expression')}
                    value={spec.subject.expression}
                    onChange={(v) => set((s) => ({ ...s, subject: { ...s.subject, expression: v } }))}
                    options={[{ value: '', label: word(lang, 'happy') }, ...EXPRESSIONS.map((x) => ({ value: x, label: word(lang, x) }))]}
                  />
                )}
                <SelectField
                  label={t('cv.side')}
                  value={spec.subject.side}
                  onChange={(v) => set((s) => ({ ...s, subject: { ...s.subject, side: v } }))}
                  options={SIDES.map((x) => ({ value: x, label: t('cv.side.' + x) }))}
                />
              </div>
              <NumberField label={t('cv.scale')} min={0.5} max={1.4} step={0.05} value={spec.subject.scale} onChange={(v) => set((s) => ({ ...s, subject: { ...s.subject, scale: v ?? 1 } }))} />
              <div className="row">
                <CheckField label={t('cv.outline')} checked={spec.subject.outline} onChange={(v) => set((s) => ({ ...s, subject: { ...s.subject, outline: v } }))} />
                <CheckField label={t('cv.arrow')} checked={spec.accents.arrow} onChange={(v) => set((s) => ({ ...s, accents: { arrow: v } }))} />
              </div>
              <div className="row">
                <UploadButton page={target.page} kind="subject" label={t('cv.character_upload')} onDone={(id) => set((s) => ({ ...s, subject: { ...s.subject, asset: id } }))} />
                {spec.subject.asset && <Badge tone="ok">#{spec.subject.asset}</Badge>}
              </div>
              <p className="small muted">{t('cv.character_hint')}</p>
            </div>
          </Card>

          <Card title={t('cv.sec.background')}>
            <div className="stack">
              <SelectField
                label={t('cv.bg_kind')}
                value={spec.background.kind}
                onChange={(v) => set((s) => ({ ...s, background: { ...s.background, kind: v } }))}
                options={[
                  { value: 'auto', label: t('cv.bg.auto') },
                  { value: 'gradient', label: t('cv.bg.gradient') },
                  { value: 'texture', label: t('cv.bg.texture') },
                  { value: 'photo', label: t('cv.bg.photo') },
                  { value: 'ai', label: t('cv.bg.ai') },
                ]}
              />
              {spec.background.kind === 'ai' && (
                <>
                  <Notice tone={m.ai.demo ? 'warn' : m.ai.available ? 'ok' : 'info'}>{m.ai.demo ? t('cv.bg.ai_demo') : m.ai.available ? t('cv.bg.ai_ready') : t('cv.bg.ai_wait')}</Notice>
                  <p className="small muted">{t('cv.bg.ai_text')}</p>
                </>
              )}
              {(spec.background.kind === 'texture' || spec.background.kind === 'auto') && (
                <SelectField
                  label={t('cv.bg.texture_kind')}
                  value={spec.background.texture}
                  onChange={(v) => set((s) => ({ ...s, background: { ...s.background, texture: v } }))}
                  options={[{ value: '', label: t('cv.color_auto') }, ...TEXTURES.map((x) => ({ value: x, label: t('cv.bg.tex.' + x) }))]}
                />
              )}
              {spec.background.kind === 'photo' && (
                <div className="row">
                  <UploadButton page={target.page} kind="background" label={t('cv.bg.upload')} onDone={(id) => set((s) => ({ ...s, background: { ...s.background, asset: id } }))} />
                  {spec.background.asset && <Badge tone="ok">#{spec.background.asset}</Badge>}
                </div>
              )}
              <div className="grid-2">
                <NumberField label={t('cv.bg.darken')} min={0} max={0.85} step={0.05} value={spec.background.darken} onChange={(v) => set((s) => ({ ...s, background: { ...s.background, darken: v ?? 0 } }))} />
                <NumberField label={t('cv.bg.blur')} min={0} max={40} step={1} value={spec.background.blur} onChange={(v) => set((s) => ({ ...s, background: { ...s.background, blur: v ?? 0 } }))} />
              </div>
            </div>
          </Card>

          <Card title={t('cv.sec.logo')}>
            <div className="stack">
              <CheckField label={t('cv.logo_show')} checked={spec.logo.show} onChange={(v) => set((s) => ({ ...s, logo: { ...s.logo, show: v } }))} />
              <SelectField label={t('cv.logo_pos')} value={spec.logo.position} onChange={(v) => set((s) => ({ ...s, logo: { ...s.logo, position: v } }))} options={LOGO_POS.map((x) => ({ value: x, label: t('cv.logo.' + x) }))} />
              <div className="row">
                <UploadButton page={target.page} kind="logo" label={t('cv.logo_upload')} onDone={(id) => set((s) => ({ ...s, logo: { ...s.logo, asset: id, show: true } }))} />
                {spec.logo.asset && <Badge tone="ok">{t('cv.logo_have')}</Badge>}
              </div>
            </div>
          </Card>
        </div>

        <div className="stack cv-side">
          <Card title={t('cv.sec.preview')} actions={<CheckField label={t('cv.guides')} checked={guides} onChange={setGuides} />}>
            <div className="stack">
              <div className="cv-preview" data-testid="cv-preview" style={{ aspectRatio: `${format.width} / ${format.height}` }}>
                {pv && <img src={pv.image} alt={t('cv.sec.preview')} draggable={false} />}
                {pv && guides && (
                  <>
                    <div className="cv-guide-safe" style={{ left: `${pv.guides.safe[0] * 100}%`, top: `${pv.guides.safe[1] * 100}%`, width: `${(pv.guides.safe[2] - pv.guides.safe[0]) * 100}%`, height: `${(pv.guides.safe[3] - pv.guides.safe[1]) * 100}%` }} title={t('cv.guide_safe')} />
                    {pv.guides.avoid.map((a, i) => (
                      <div key={i} className="cv-guide-avoid" style={{ left: `${a.rect[0] * 100}%`, top: `${a.rect[1] * 100}%`, width: `${(a.rect[2] - a.rect[0]) * 100}%`, height: `${(a.rect[3] - a.rect[1]) * 100}%` }} title={pick(a, 'note')} />
                    ))}
                  </>
                )}
                {pvBusy && <div className="cv-preview-busy small">{t('cv.preview_busy')}</div>}
              </div>
              {pvErr && <Notice tone="err">{t('cv.preview_failed') + pvErr}</Notice>}
              {pv && (
                <p className="small muted">
                  {t('cv.preview_size', { w: pv.full[0], h: pv.full[1] })} · {m.shaping.raqm ? t('cv.shaping_raqm') : t('cv.shaping_builtin')}
                </p>
              )}
              {guides && (
                <p className="small muted">
                  <span className="cv-key cv-key-safe" /> {t('cv.guide_safe')} <span className="cv-key cv-key-avoid" /> {t('cv.guide_avoid')}
                </p>
              )}
              {pv && pv.warnings.length > 0 && (
                <Notice tone="warn">
                  <strong>{t('cv.warnings')}</strong>
                  <ul>{pv.warnings.map((w) => <li key={w.code}>{pick(w)}</li>)}</ul>
                </Notice>
              )}
            </div>
          </Card>

          <Card title={t('cv.sec.ideas')}>
            <div className="stack">
              <p className="small muted">{t('cv.ideas_intro')}</p>
              <div className="row">
                <CheckField label={t('cv.ideas_ai')} checked={useAi} onChange={setUseAi} />
                <Button data-testid="cv-ideas-go" icon="spark" variant="primary" busy={ideasQ.busy} onClick={suggest}>
                  {ideas ? t('cv.ideas_more') : t('cv.ideas_go')}
                </Button>
              </div>
              {ideas ? (
                <>
                  <Notice tone={ideas.via === 'rules' && useAi ? 'warn' : 'info'}>{pick(ideas, 'message')}</Notice>
                  <div className="stack-sm">
                    {ideas.ideas.map((i) => (
                      <div key={i.id} className="cv-idea" data-testid="cv-idea">
                        <div className="grow">
                          <div className="strong">{i.title.replace(/\*/g, '')}</div>
                          {i.subtitle && <div className="small">{i.subtitle}</div>}
                          <div className="small muted">
                            {pick(i, 'style_title')} · {i.source === 'ai' ? t('cv.idea_by_ai') : t('cv.idea_by_rules')}
                          </div>
                          <div className="small muted">{pick(i, 'concept')}</div>
                        </div>
                        <Button size="sm" data-testid="cv-idea-apply" onClick={() => { applyIdea(i) }}>{t('cv.ideas_apply')}</Button>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="small muted">{t('cv.ideas_empty')}</p>
              )}
            </div>
          </Card>

          <Card title={t('cv.sec.make')}>
            <div className="stack">
              <div className="grid-2">
                <SelectField label={t('cv.variants')} value={variants} onChange={setVariants} options={Array.from({ length: m.max_variants }, (_, k) => ({ value: String(k + 1), label: f.num(k + 1) }))} />
                {target.episode ? <CheckField label={t('cv.use_as_cover')} checked={useAsCover} onChange={setUseAsCover} /> : null}
              </div>
              {parent && <Notice tone="info">{t('cv.make_from', { id: parent })}</Notice>}
              <Button data-testid="cv-make" variant="primary" icon="image" busy={maker.starting || maker.busy} onClick={make}>
                {t('cv.make')}
              </Button>
              <p className="small muted">{t('cv.make_hint')}</p>
              {maker.job && !maker.succeeded && <JobView job={maker.job} offline={maker.offline} />}
              {waiting && <Notice tone="info">{t('cv.waiting_note')}</Notice>}
            </div>
          </Card>
        </div>
      </div>

      <Card title={t('cv.sec.versions')}>
        {!latest || latest.variants.length === 0 ? (
          <p className="muted">{t('cv.versions_empty')}</p>
        ) : (
          <div className="stack">
            <div className="row">
              <Badge tone={latest.status === 'ready' ? 'ok' : latest.status === 'failed' ? 'err' : 'info'}>{tr('cv.status.' + latest.status, latest.status)}</Badge>
              <Badge>{tr('cv.bgstate.' + latest.bg_state, latest.bg_state)}</Badge>
              {latest.in_use && <Badge tone="primary">{t('cv.version_in_use')}</Badge>}
              <span className="small muted">{f.dateTime(latest.created_at)}</span>
            </div>
            {latest.status === 'waiting_bg' && <Notice tone="info">{t('cv.waiting_note')}</Notice>}
            {latest.error && <Notice tone="err">{latest.error}</Notice>}
            <div className="cv-variants" data-testid="cv-variants">
              {latest.variants.map((v) => (
                <div key={v.letter} data-testid={'cv-variant-' + v.letter} className={'cv-variant' + (latest.chosen === v.index ? ' chosen' : '')}>
                  {v.url && <img src={v.url} alt={t('cv.version', { letter: v.letter })} loading="lazy" />}
                  {(v.note_fa || v.note_en) && <div className="small muted">{pick(v, 'note')}</div>}
                  <div className="row between nw">
                    <strong>{t('cv.version', { letter: v.letter })}</strong>
                    {latest.chosen === v.index && latest.in_use && <Badge tone="primary">{t('cv.version_in_use')}</Badge>}
                  </div>
                  <div className="row" style={{ gap: '0.35rem' }}>
                    {latest.episode && latest.chosen !== v.index && (
                      <Button size="sm" variant="primary" data-testid={'cv-use-' + v.letter} busy={act.busy} onClick={() => useVersion(latest, v.letter)}>
                        {t('cv.version_use')}
                      </Button>
                    )}
                    <ExtLink href={`/api/covers/${latest.id}/download?variant=${v.letter}&fmt=png`} download className="btn sm">{t('cv.version_png')}</ExtLink>
                    <ExtLink href={`/api/covers/${latest.id}/download?variant=${v.letter}&fmt=jpg`} download className="btn sm">{t('cv.version_jpg')}</ExtLink>
                  </div>
                </div>
              ))}
            </div>
            <div className="row">
              {latest.variants.length < m.max_variants && (
                <Button icon="plus" busy={maker.busy} onClick={() => more(latest)}>
                  {t('cv.version_more')}
                </Button>
              )}
              <ExtLink href={`/api/covers/${latest.id}/zip`} download className="btn">{t('cv.version_zip')}</ExtLink>
            </div>
            {format.max_kb > 0 && <p className="small muted">{t('cv.jpg_hint', { kb: format.max_kb })}</p>}
          </div>
        )}
      </Card>

      <Card title={t('cv.sec.history')}>
        {!covers.data || covers.data.length === 0 ? (
          <p className="muted">{t('cv.history_empty')}</p>
        ) : (
          <div className="cv-history">
            {covers.data.map((cv) => (
              <div key={cv.id} className="cv-hist-row" data-testid="cv-hist-row">
                {(cv.asset?.url || cv.variants[0]?.url) && <img src={cv.asset?.url ?? cv.variants[0]?.url} alt="" loading="lazy" />}
                <div className="grow">
                  <div className="strong">
                    #{cv.id} · {pick(m.styles.find((s) => s.key === cv.style) ?? { title_fa: cv.style, title_en: cv.style }, 'title')}
                  </div>
                  <div className="small muted">
                    {pick(m.formats.find((x) => x.key === cv.format) ?? { title_fa: cv.format, title_en: cv.format }, 'title')} · {f.dateTime(cv.created_at)} · {tr('cv.status.' + cv.status, cv.status)}
                    {cv.parent ? ' · ' + t('cv.make_from', { id: cv.parent }) : ''}
                  </div>
                </div>
                <div className="row" style={{ gap: '0.35rem' }}>
                  <Button size="sm" icon="edit" data-testid="cv-hist-edit" onClick={() => { void editAgain(cv) }}>{t('cv.history_edit')}</Button>
                  <Button size="sm" variant="ghost" icon="trash" onClick={() => remove(cv)}>{t('cv.history_delete')}</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
