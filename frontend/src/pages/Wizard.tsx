import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { DevTemplate, FormatDef, Formats, PageDetail, Strategy } from '../api/types'
import { CharacterFields, emptyChar, type CharDraft } from '../components/CharacterFields'
import { JobView } from '../components/domain'
import { Icon } from '../components/Icon'
import { StrategyEditor } from '../components/StrategyEditor'
import { AreaField, Button, Card, CheckField, ChoiceGrid, ErrorState, Loading, Notice, NumberField, PageHead, SwitchField, TextField } from '../components/ui'
import { useAction, useJobRunner, useTitle } from '../hooks'
import { ANIME, EXPLAINER, useFormats } from '../formats'
import { useI18n } from '../i18n'
import { StylePicker } from '../components/StylePicker'
import { desc, nm, useTemplates } from '../library'

type Level = 'manual' | 'assisted' | 'automatic'
interface Idea {
  title: string
  premise: string
  branch_point: string
  episodes: number
}
interface WState {
  name: string
  handle: string
  format: string
  languages: string[]
  audience: string
  tone: string
  niche: string
  styleKey: string
  realism: string
  themeKey: string
  templateKey: string
  studio: boolean
  styleNotes: string
  characters: CharDraft[]
  automation: Level
  preset: string
  episodes: number
  episodeLength: number
  idea: string
  strategy: Strategy | null
  ideas: Idea[]
  pick: number
  isFan: boolean
  franchise: string
}

const DEFAULT_STYLE: Record<string, { style: string; realism: string; theme: string }> = {
  anime_whatif: { style: 'modern_tv_anime', realism: 'anime', theme: 'pastel_dream' },
  recurring_character: { style: 'western_2d_tv', realism: 'cartoon', theme: 'candy_bright' },
  concept_explainer: { style: 'flat_vector_motion', realism: 'graphic', theme: 'ocean_calm' },
}
const FALLBACK_STYLE = { style: 'modern_tv_anime', realism: 'anime', theme: 'pastel_dream' }
const STEPS = ['wiz.step1', 'wiz.step2', 'wiz.step3', 'wiz.step4', 'wiz.step5', 'wiz.step6'] as const

export default function Wizard() {
  const { t } = useI18n()
  useTitle(t('wiz.title'))
  const nav = useNavigate()
  const fm = useFormats()
  const tpl = useTemplates()
  if (fm.error) return <ErrorState error={fm.error} />
  if (tpl.error) return <ErrorState error={tpl.error} onRetry={tpl.reload} />
  if (!fm.data || !tpl.data) return <Loading />
  return <WizardBody formats={fm.data} templates={tpl.data.templates} navigate={nav} />
}

function WizardBody({ formats, templates, navigate }: { formats: Formats; templates: DevTemplate[]; navigate: (to: string) => void }) {
  const { t, lang } = useI18n()
  const first = formats.formats[0]
  const [step, setStep] = useState(0)
  const [maxStep, setMaxStep] = useState(0)
  const touched = useRef({ style: false, series: false })
  const [s, setS] = useState<WState>({
    name: '',
    handle: '',
    format: first.key,
    languages: ['fa'],
    audience: '',
    tone: '',
    niche: '',
    styleKey: (DEFAULT_STYLE[first.key] ?? FALLBACK_STYLE).style,
    realism: (DEFAULT_STYLE[first.key] ?? FALLBACK_STYLE).realism,
    themeKey: (DEFAULT_STYLE[first.key] ?? FALLBACK_STYLE).theme,
    templateKey: '',
    studio: true,
    styleNotes: '',
    characters: [],
    automation: 'manual',
    preset: 'balanced',
    episodes: first.default_series.episodes,
    episodeLength: first.default_series.episode_length_sec,
    idea: '',
    strategy: null,
    ideas: [],
    pick: 0,
    isFan: false,
    franchise: '',
  })
  const set = (patch: Partial<WState>) => setS((p) => ({ ...p, ...patch }))
  const fmt: FormatDef = formats.formats.find((f) => f.key === s.format) ?? first
  const headRef = useRef<HTMLHeadingElement>(null)

  // A template decides the development steps; its base format decides the policy notices (fan content, sources, presenter).
  const pickTemplate = (tkey: string) => {
    const tp = templates.find((x) => x.key === tkey)!
    const key = tp.base_format
    const f = formats.formats.find((x) => x.key === key) ?? first
    const patch: Partial<WState> = { format: key, templateKey: tp.builtin ? '' : tp.key, strategy: null, ideas: [] }
    if (!touched.current.style) {
      const d = DEFAULT_STYLE[key] ?? FALLBACK_STYLE
      Object.assign(patch, { styleKey: d.style, realism: d.realism, themeKey: d.theme })
    }
    if (!touched.current.series) {
      patch.episodes = tp.default_series.episodes ?? f.default_series.episodes
      patch.episodeLength = tp.default_series.episode_length_sec ?? f.default_series.episode_length_sec
    }
    if (key !== ANIME) patch.isFan = false
    set(patch)
  }

  const runner = useJobRunner<{ strategy: Strategy }>({
    onSucceeded: (j) => {
      const st = j.result.strategy as Strategy | undefined
      if (!st) return
      const ideas: Idea[] = (st.series_ideas ?? []).map((i) => ({
        title: i.title,
        premise: i.premise,
        branch_point: i.branch_point ?? '',
        episodes: i.episodes ?? s.episodes,
      }))
      setS((p) => {
        const have = new Set(p.characters.map((c) => c.name.trim()))
        const added = (st.characters ?? [])
          .filter((c) => c.name && !have.has(c.name.trim()))
          .map<CharDraft>((c) => ({ ...emptyChar(), name: c.name, role: c.role ?? '', personality: c.personality ?? '', appearance: c.appearance ?? '', is_original: c.is_original !== false }))
        return { ...p, strategy: { ...st, characters: [] }, ideas, pick: 0, characters: [...p.characters, ...added] }
      })
    },
  })

  const create = useAction()
  const valid = [s.name.trim().length > 0 && !!s.format, s.languages.length > 0, true, true, s.episodes >= 1 && s.episodeLength >= 10, true]
  const go = (n: number) => {
    setStep(n)
    setMaxStep((m) => Math.max(m, n))
    window.scrollTo({ top: 0 })
    headRef.current?.focus()
  }

  useEffect(() => {
    headRef.current?.focus()
  }, [])

  const propose = () =>
    runner.start(() =>
      api.post('/strategy', {
        page_name: s.name,
        format: s.format,
        language: s.languages[0],
        idea: s.idea,
        niche: s.niche,
        audience: s.audience,
        tone: s.tone,
        episodes_count: s.episodes,
        episode_length_sec: s.episodeLength,
      }),
    )

  const submit = async () => {
    const chars = s.characters.filter((c) => c.name.trim()).map((c) => ({ ...c, name: c.name.trim() }))
    const body: Record<string, unknown> = {
      name: s.name.trim(),
      handle: s.handle.trim().replace(/^@/, ''),
      format: s.format,
      template_key: s.templateKey,
      languages: s.languages,
      idea: s.idea,
      automation_level: s.automation,
      profiles: {
        identity: { display_name: s.name.trim(), handle: s.handle.trim().replace(/^@/, ''), niche: s.niche, audience: s.audience, tone: s.tone, languages: s.languages },
        visual: { style_key: s.styleKey, realism: s.realism, theme_key: s.themeKey, style_notes: s.styleNotes },
        audio: { language: s.languages[0] },
        production: { preset: s.preset, episodes_per_series: s.episodes, episode_length_sec: s.episodeLength, studio_mode: s.studio },
        publishing: { platform: 'instagram', auto_publish: false },
      },
      characters: chars,
    }
    if (s.strategy) {
      body.strategy = { ...s.strategy, characters: [], posting_plan: { ...s.strategy.posting_plan, episode_length_sec: s.episodeLength } }
      const idea = s.ideas[s.pick]
      if (idea) {
        body.series = {
          title: idea.title,
          premise: idea.premise,
          branch_point: idea.branch_point,
          episodes: idea.episodes,
          template_key: s.templateKey,
          is_fan_content: s.format === ANIME && s.isFan,
          franchise: s.format === ANIME && s.isFan ? s.franchise : '',
        }
      }
    }
    const page = await create.run(async () => {
      const p = await api.post<PageDetail>('/pages', body)
      // one call writes the look consistently: realism, theme, subtitle look from the theme's typography, negative prompt and palette
      await api.post(`/pages/${p.id}/apply-look`, { style_key: s.styleKey, theme_key: s.themeKey, style_notes: s.styleNotes }).catch(() => undefined)
      return p
    }, { success: t('wiz.created') })
    if (page) navigate(`/pages/${page.id}`)
  }

  const policy = fmt.policy
  const notices = lang === 'en' && formats.notices_en ? formats.notices_en : formats.notices

  return (
    <div className="stack" style={{ maxWidth: 920 }}>
      <PageHead title={t('wiz.title')} crumbs={[{ label: t('nav.pages'), to: '/pages' }, { label: t('wiz.title') }]} />
      <nav aria-label={t('wiz.steps')}>
        <ol className="wizard-steps" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {STEPS.map((k, i) => (
            <li key={k} style={{ display: 'contents' }}>
              <button type="button" className={i < step ? 'done' : ''} aria-current={i === step ? 'step' : undefined} disabled={i > maxStep} onClick={() => go(i)}>
                <span className="num">{i < step ? <Icon name="check" size={14} /> : (i + 1).toLocaleString(lang === 'fa' ? 'fa-IR' : 'en-US')}</span>
                <span className="lbl">{t(k)}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <h2 tabIndex={-1} ref={headRef} style={{ outline: 'none' }}>
        {t(STEPS[step])}
      </h2>

      {step === 0 && (
        <div className="stack">
          <div className="grid-2">
            <TextField label={t('wiz.name')} required value={s.name} onChange={(v) => set({ name: v })} hint={t('wiz.name_hint')} autoFocus />
            <TextField label={t('wiz.handle')} ltr value={s.handle} onChange={(v) => set({ handle: v })} placeholder="my_page" hint={t('wiz.handle_hint')} />
          </div>
          <ChoiceGrid
            legend={t('wiz.format')}
            name="format"
            value={s.templateKey || s.format}
            onChange={pickTemplate}
            options={templates.map((x) => ({
              value: x.key,
              title: <span className="format-title">{nm(x, lang)}</span>,
              text: desc(x, lang),
            }))}
          />
          <p className="field-hint">{t('wiz.template_hint')}</p>
          <div className="stack-sm" aria-live="polite">
            {policy.fan_notice && <Notice tone="warn">{notices.fan}</Notice>}
            {policy.original_default && fmt.key === ANIME && <Notice tone="info">{t('wiz.original_default')}</Notice>}
            {policy.sourced && <Notice tone="info">{notices.explainer}</Notice>}
            {policy.synthetic_presenter_only && <Notice tone="warn">{notices.presenter}</Notice>}
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="stack">
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field-label">{t('wiz.languages')}</legend>
            <div className="row" style={{ gap: '1.5rem' }}>
              {(['fa', 'en'] as const).map((l) => (
                <CheckField
                  key={l}
                  label={l === 'fa' ? 'فارسی' : 'English'}
                  checked={s.languages.includes(l)}
                  onChange={(on) => set({ languages: on ? [...s.languages, l] : s.languages.filter((x) => x !== l) })}
                />
              ))}
            </div>
            <div className="field-hint">{t('wiz.languages_hint')}</div>
            {s.languages.length === 0 && <div className="field-error" role="alert">{t('wiz.languages_required')}</div>}
          </fieldset>
          <TextField label={t('wiz.niche')} value={s.niche} onChange={(v) => set({ niche: v })} hint={t('wiz.niche_hint')} />
          <TextField label={t('wiz.audience')} value={s.audience} onChange={(v) => set({ audience: v })} hint={t('wiz.audience_hint')} />
          <TextField label={t('wiz.tone')} value={s.tone} onChange={(v) => set({ tone: v })} hint={t('wiz.tone_hint')} list="tone-suggestions" />
          <datalist id="tone-suggestions">
            {['صمیمی و دوستانه', 'جدی و سینمایی', 'طنزآمیز', 'آموزشی و ساده', 'هیجان‌انگیز', 'آرام و فکری'].map((x) => (
              <option key={x} value={x} />
            ))}
          </datalist>
        </div>
      )}

      {step === 2 && (
        <div className="stack">
          <p className="muted">{t('wiz.look_intro')}</p>
          <StylePicker
            value={{ style_key: s.styleKey, realism: s.realism, theme_key: s.themeKey }}
            onChange={(v) => {
              touched.current.style = true
              set({ styleKey: v.style_key, realism: v.realism, themeKey: v.theme_key })
            }}
          />
          <AreaField label={t('wiz.style_notes')} value={s.styleNotes} onChange={(v) => set({ styleNotes: v })} hint={t('wiz.style_notes_hint')} compact />
        </div>
      )}

      {step === 3 && (
        <CharactersStep s={s} set={set} required={fmt.key !== EXPLAINER} />
      )}

      {step === 4 && (
        <div className="stack">
          <ChoiceGrid<Level>
            legend={t('wiz.automation')}
            name="automation"
            value={s.automation}
            onChange={(v) => set({ automation: v })}
            options={[
              { value: 'manual', title: t('wiz.auto_manual'), text: t('wiz.auto_manual_text') },
              { value: 'assisted', title: t('wiz.auto_assisted'), text: t('wiz.auto_assisted_text') },
              { value: 'automatic', title: t('wiz.auto_automatic'), text: t('wiz.auto_automatic_text') },
            ]}
          />
          <Notice tone="info">{t('wiz.auto_note')}</Notice>
          <SwitchField label={t('wiz.studio')} hint={t('wiz.studio_hint')} checked={s.studio} onChange={(v) => set({ studio: v })} />
          <ChoiceGrid
            legend={t('wiz.preset')}
            name="preset"
            value={s.preset}
            onChange={(v) => set({ preset: v })}
            options={Object.entries(formats.presets).map(([k, p]) => ({ value: k, title: lang === 'en' ? p.label_en ?? p.label_fa : p.label_fa, text: lang === 'en' ? p.note_en ?? p.note_fa : p.note_fa }))}
          />
          <div className="grid-2">
            <NumberField
              label={t('wiz.episodes')}
              min={1}
              max={60}
              value={s.episodes}
              onChange={(v) => {
                touched.current.series = true
                set({ episodes: v ?? 1 })
              }}
              hint={t('wiz.episodes_hint', { n: fmt.default_series.episodes })}
            />
            <NumberField
              label={t('wiz.length')}
              min={10}
              max={180}
              value={s.episodeLength}
              onChange={(v) => {
                touched.current.series = true
                set({ episodeLength: v ?? 30 })
              }}
              hint={t('wiz.length_hint', { n: fmt.default_series.episode_length_sec })}
            />
          </div>
        </div>
      )}

      {step === 5 && (
        <div className="stack">
          <p className="muted">{t('wiz.idea_intro')}</p>
          <AreaField label={t('wiz.idea')} value={s.idea} onChange={(v) => set({ idea: v })} placeholder={lang === 'en' ? fmt.idea_hint_en ?? fmt.idea_hint_fa : fmt.idea_hint_fa} hint={t('wiz.idea_hint')} />
          <div className="row">
            <Button variant="primary" icon="spark" busy={runner.starting || (runner.busy && !runner.job)} disabled={runner.busy} onClick={propose}>
              {s.strategy ? t('wiz.propose_again') : t('wiz.propose')}
            </Button>
            {s.strategy && <span className="small muted">{t('wiz.propose_replace')}</span>}
          </div>
          {runner.job && !runner.succeeded && <JobView job={runner.job} offline={runner.offline} />}
          {runner.failed && <Notice tone="err">{t('wiz.propose_failed')}</Notice>}

          {s.strategy && (
            <Card title={t('wiz.proposal')}>
              <div className="stack-lg">
                <Notice tone="info">{t('wiz.proposal_note')}</Notice>
                <StrategyEditor value={s.strategy} onChange={(st) => set({ strategy: st })} />
                <section className="stack" aria-labelledby="ideas-h">
                  <h3 id="ideas-h">{t('wiz.series_ideas')}</h3>
                  <p className="muted small">{t('wiz.series_ideas_hint')}</p>
                  {s.ideas.length === 0 && <Notice tone="warn">{t('wiz.no_ideas')}</Notice>}
                  {s.ideas.map((idea, i) => (
                    <div key={i} className={'choice' + (s.pick === i ? ' selected' : '')} style={{ cursor: 'default' }}>
                      <label className="check">
                        <input type="radio" name="idea" checked={s.pick === i} onChange={() => set({ pick: i })} />
                        <span className="strong">{t('wiz.pick_this')}</span>
                      </label>
                      <div className="stack-sm">
                        <TextField label={t('wiz.series_title')} value={idea.title} onChange={(v) => set({ ideas: s.ideas.map((x, j) => (j === i ? { ...x, title: v } : x)) })} />
                        <AreaField label={t('wiz.series_premise')} compact value={idea.premise} onChange={(v) => set({ ideas: s.ideas.map((x, j) => (j === i ? { ...x, premise: v } : x)) })} />
                        {s.format === ANIME && (
                          <AreaField label={t('wiz.series_branch')} compact value={idea.branch_point} onChange={(v) => set({ ideas: s.ideas.map((x, j) => (j === i ? { ...x, branch_point: v } : x)) })} />
                        )}
                        <NumberField label={t('wiz.series_episodes')} min={1} max={60} value={idea.episodes} onChange={(v) => set({ ideas: s.ideas.map((x, j) => (j === i ? { ...x, episodes: v ?? 1 } : x)) })} />
                      </div>
                    </div>
                  ))}
                  {s.format === ANIME && s.ideas.length > 0 && (
                    <div className="stack-sm">
                      <SwitchField label={t('wiz.fan')} hint={t('wiz.fan_hint')} checked={s.isFan} onChange={(v) => set({ isFan: v })} />
                      {s.isFan && (
                        <>
                          <Notice tone="warn">{notices.fan}</Notice>
                          <TextField label={t('wiz.franchise')} value={s.franchise} onChange={(v) => set({ franchise: v })} />
                        </>
                      )}
                    </div>
                  )}
                </section>
                {s.characters.length > 0 && <p className="small muted">{t('wiz.proposal_chars', { n: s.characters.length })}</p>}
              </div>
            </Card>
          )}
        </div>
      )}

      <div className="sticky-actions">
        {step > 0 && (
          <Button icon={lang === 'fa' ? 'next' : 'prev'} onClick={() => go(step - 1)}>
            {t('common.back')}
          </Button>
        )}
        {step < STEPS.length - 1 ? (
          <Button variant="primary" disabled={!valid[step]} onClick={() => go(step + 1)}>
            {t('common.next')}
            <Icon name={lang === 'fa' ? 'prev' : 'next'} />
          </Button>
        ) : (
          <Button variant="primary" icon="check" busy={create.busy} disabled={!valid.every(Boolean) || runner.busy} onClick={submit}>
            {s.strategy ? t('wiz.create') : t('wiz.create_without')}
          </Button>
        )}
        {step === STEPS.length - 1 && !s.strategy && <span className="small muted">{t('wiz.skip_note')}</span>}
        {!valid[step] && <span className="small" style={{ color: 'var(--err)' }}>{t('wiz.fix_step')}</span>}
      </div>
    </div>
  )
}

function CharactersStep({ s, set, required }: { s: WState; set: (p: Partial<WState>) => void; required: boolean }) {
  const { t } = useI18n()
  const upd = (i: number, c: CharDraft) => set({ characters: s.characters.map((x, j) => (j === i ? c : x)) })
  return (
    <div className="stack">
      <Notice tone="info">{required ? t('wiz.chars_hint') : t('wiz.chars_hint_explainer')}</Notice>
      {s.characters.some((c) => !c.is_original) && <Notice tone="warn">{t('wiz.chars_fan_hint')}</Notice>}
      {s.characters.length === 0 && <p className="muted">{t('wiz.chars_empty')}</p>}
      {s.characters.map((c, i) => (
        <Card key={i} title={c.name || t('wiz.char_n', { n: i + 1 })} actions={<Button size="sm" variant="danger" icon="trash" onClick={() => set({ characters: s.characters.filter((_, j) => j !== i) })}>{t('common.remove')}</Button>}>
          <CharacterFields value={c} onChange={(nc) => upd(i, nc)} />
        </Card>
      ))}
      <div>
        <Button icon="plus" onClick={() => set({ characters: [...s.characters, emptyChar()] })}>
          {t('wiz.add_char')}
        </Button>
      </div>
    </div>
  )
}
