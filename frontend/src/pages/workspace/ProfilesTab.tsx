import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Formats, PageDetail, ProfileKind, ProfileTemplate, Strategy } from '../../api/types'
import { PROFILE_KINDS } from '../../api/types'
import { useConfirm } from '../../components/feedback'
import { JobView } from '../../components/domain'
import { StrategyEditor } from '../../components/StrategyEditor'
import { AreaField, Button, Card, CheckField, ErrorState, Loading, Notice, NumberField, SelectField, Segmented, StringListField, SwitchField, TagsField, TextField } from '../../components/ui'
import { IMPLEMENTED_TECHNIQUES, WEEKDAYS, useFormats } from '../../formats'
import { useAction, useJobRunner, useQuery } from '../../hooks'
import { useI18n } from '../../i18n'
import { useWs } from './Workspace'
import { StylePicker } from '../../components/StylePicker'
import { schemaSubtitle, useLibrary } from '../../library'
import { TextModelsCard } from './LlmCard'

type Draft = Record<string, any>

export function ProfilesTab() {
  const { t } = useI18n()
  const { page, setPage } = useWs()
  const fm = useFormats()
  const [kind, setKind] = useState<ProfileKind>('identity')
  const [drafts, setDrafts] = useState<Partial<Record<ProfileKind, Draft>>>({})
  // when the saved profile changes on the server (save, template), drop the local draft of that kind
  useEffect(() => setDrafts({}), [page.updated_at])
  if (fm.error) return <ErrorState error={fm.error} />
  if (!fm.data) return <Loading />
  const isDirty = (k: ProfileKind) => drafts[k] !== undefined && JSON.stringify(drafts[k]) !== JSON.stringify(page.profiles[k])
  return (
    <div className="stack">
      <div>
        <h2>{t('ws.tab_settings')}</h2>
        <p className="muted">{t('prof.intro')}</p>
      </div>
      <div className="row">
        <Segmented
          label={t('prof.kinds')}
          value={kind}
          onChange={setKind}
          options={PROFILE_KINDS.map((k) => ({ key: k, label: <>{t(('prof.kind_' + k) as 'prof.kind_identity')}{isDirty(k) ? ' •' : ''}</> }))}
        />
      </div>
      <p className="muted small">{t(('prof.about_' + kind) as 'prof.about_identity')}</p>
      <ProfileEditor
        key={kind}
        kind={kind}
        page={page}
        setPage={setPage}
        formats={fm.data}
        draft={drafts[kind] ?? page.profiles[kind]}
        setDraft={(d) => setDrafts((p) => ({ ...p, [kind]: d }))}
        dirty={isDirty(kind)}
        reset={() => setDrafts((p) => ({ ...p, [kind]: undefined }))}
      />
    </div>
  )
}

function ProfileEditor({ kind, page, setPage, formats, draft, setDraft, dirty, reset }: {
  kind: ProfileKind
  page: PageDetail
  setPage: (p: PageDetail) => void
  formats: Formats
  draft: Draft
  setDraft: (d: Draft) => void
  dirty: boolean
  reset: () => void
}) {
  const { t } = useI18n()
  const save = useAction()
  const [pageName, setPageName] = useState(page.name)
  const set = (patch: Draft) => setDraft({ ...draft, ...patch })
  const nameDirty = kind === 'identity' && pageName.trim() !== page.name
  const identityInvalid = kind === 'identity' && (!Array.isArray(draft.languages) || draft.languages.length === 0 || !pageName.trim())

  const doSave = async () => {
    await save.run(
      async () => {
        let p = await api.put<PageDetail>(`/pages/${page.id}/profiles/${kind}`, kind === 'publishing' ? { ...draft, auto_publish: false } : draft)
        if (kind === 'identity') {
          p = await api.patch<PageDetail>(`/pages/${page.id}`, { name: pageName.trim(), handle: String(draft.handle ?? '').replace(/^@/, ''), languages: draft.languages })
        }
        setPage(p)
      },
      { success: t('common.saved') },
    )
  }

  return (
    <div className="stack">
      <Card>
        <div className="stack">
          {kind === 'identity' && <IdentityForm draft={draft} set={set} pageName={pageName} setPageName={setPageName} />}
          {kind === 'strategy' && <StrategyForm draft={draft} set={set} />}
          {kind === 'visual' && <VisualForm draft={draft} set={set} formats={formats} />}
          {kind === 'audio' && <AudioForm draft={draft} set={set} />}
          {kind === 'production' && <ProductionForm draft={draft} set={set} formats={formats} />}
          {kind === 'publishing' && <PublishingForm draft={draft} set={set} />}
        </div>
      </Card>
      <div className="sticky-actions">
        <Button variant="primary" icon="save" busy={save.busy} disabled={(!dirty && !nameDirty) || identityInvalid} onClick={doSave}>
          {t('common.save')}
        </Button>
        <Button onClick={() => { reset(); setPageName(page.name) }} disabled={!dirty && !nameDirty}>
          {t('prof.revert')}
        </Button>
        {(dirty || nameDirty) && <span className="small muted">{t('prof.unsaved')}</span>}
      </div>
      {kind === 'strategy' && <StrategyProposal page={page} setPage={setPage} />}
      <TemplatesCard kind={kind} draft={draft} page={page} setPage={setPage} />
    </div>
  )
}

// ---------------------------------------------------------------- per-kind forms
type FormProps = { draft: Draft; set: (p: Draft) => void }

function IdentityForm({ draft, set, pageName, setPageName }: FormProps & { pageName: string; setPageName: (v: string) => void }) {
  const { t } = useI18n()
  const langs: string[] = draft.languages ?? []
  return (
    <>
      <div className="grid-2">
        <TextField label={t('pf.page_name')} required value={pageName} onChange={setPageName} hint={t('pf.page_name_hint')} />
        <TextField label={t('pf.display_name')} value={draft.display_name ?? ''} onChange={(v) => set({ display_name: v })} />
      </div>
      <TextField label={t('wiz.handle')} ltr value={draft.handle ?? ''} onChange={(v) => set({ handle: v })} />
      <AreaField label={t('pf.bio')} value={draft.bio ?? ''} onChange={(v) => set({ bio: v })} compact />
      <div className="grid-2">
        <TextField label={t('wiz.niche')} value={draft.niche ?? ''} onChange={(v) => set({ niche: v })} />
        <TextField label={t('pf.theme')} value={draft.theme ?? ''} onChange={(v) => set({ theme: v })} />
        <TextField label={t('wiz.audience')} value={draft.audience ?? ''} onChange={(v) => set({ audience: v })} />
        <TextField label={t('wiz.tone')} value={draft.tone ?? ''} onChange={(v) => set({ tone: v })} />
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="field-label">{t('wiz.languages')}</legend>
        <div className="row" style={{ gap: '1.5rem' }}>
          {(['fa', 'en'] as const).map((l) => (
            <CheckField key={l} label={l === 'fa' ? 'فارسی' : 'English'} checked={langs.includes(l)} onChange={(on) => set({ languages: on ? [...langs, l] : langs.filter((x) => x !== l) })} />
          ))}
        </div>
        <div className="field-hint">{t('wiz.languages_hint')}</div>
        {langs.length === 0 && <div className="field-error" role="alert">{t('wiz.languages_required')}</div>}
      </fieldset>
      <StringListField label={t('pf.content_rules')} hint={t('pf.content_rules_hint')} value={draft.content_rules ?? []} onChange={(v) => set({ content_rules: v })} addLabel={t('pf.add_rule')} />
    </>
  )
}

function StrategyForm({ draft, set }: FormProps) {
  const { t } = useI18n()
  return (
    <>
      <AreaField label={t('strat.positioning')} value={draft.positioning ?? ''} onChange={(v) => set({ positioning: v })} />
      <AreaField label={t('strat.audience_insight')} value={draft.audience_insight ?? ''} onChange={(v) => set({ audience_insight: v })} />
      <AreaField label={t('strat.tone')} value={draft.tone_guidelines ?? ''} onChange={(v) => set({ tone_guidelines: v })} />
      <StringListField label={t('strat.pillars')} value={draft.pillars ?? []} onChange={(v) => set({ pillars: v })} addLabel={t('strat.add_pillar')} />
      <TagsField label={t('strat.hashtags')} value={draft.hashtags ?? []} onChange={(v) => set({ hashtags: v })} ltr />
      <StringListField label={t('strat.risks')} value={draft.risks ?? []} onChange={(v) => set({ risks: v })} addLabel={t('strat.add_risk')} />
      <TextField label={t('pf.posting_goal')} value={draft.posting_goal ?? ''} onChange={(v) => set({ posting_goal: v })} />
    </>
  )
}

function ColorList({ label, value, onChange }: { label: string; value: string[]; onChange: (v: string[]) => void }) {
  const { t } = useI18n()
  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="field-label">{label}</legend>
      <div className="row">
        {value.map((c, i) => (
          <span key={i} className="row nw" style={{ gap: '0.25rem' }}>
            <input type="color" value={/^#[0-9a-f]{6}$/i.test(c) ? c : '#888888'} aria-label={`${label} ${i + 1}`} onChange={(e) => onChange(value.map((x, j) => (j === i ? e.target.value : x)))} />
            <Button variant="ghost" size="sm" iconOnly icon="close" aria-label={t('common.remove')} onClick={() => onChange(value.filter((_, j) => j !== i))} />
          </span>
        ))}
        <Button size="sm" icon="plus" onClick={() => onChange([...value, '#3451c7'])}>
          {t('pf.add_color')}
        </Button>
      </div>
    </fieldset>
  )
}

function VisualForm({ draft, set, formats }: FormProps & { formats: Formats }) {
  const { t } = useI18n()
  const sub = draft.subtitle ?? {}
  const setSub = (patch: Draft) => set({ subtitle: { ...sub, ...patch } })
  const lib = useLibrary()
  void formats
  // picking a style or theme also fills what depends on it: the palette, the negative prompt and the subtitle look of the theme
  const pick = (v: { style_key: string; realism: string; theme_key: string }) => {
    const st = lib.style(v.style_key)
    const th = lib.theme(v.theme_key)
    const patch: Draft = { ...v }
    if (st) {
      patch.negative_prompt = [st.image_negative, th?.negative_fragment].filter(Boolean).join(', ')
      patch.palette = th?.palette ?? st.palette
    }
    if (th) patch.subtitle = { ...sub, ...schemaSubtitle(th) }
    set(patch)
  }
  return (
    <>
      <StylePicker value={{ style_key: draft.style_key ?? '', realism: draft.realism ?? '', theme_key: draft.theme_key ?? '' }} onChange={pick} name="page-look" />
      <AreaField label={t('wiz.style_notes')} value={draft.style_notes ?? ''} onChange={(v) => set({ style_notes: v })} compact />
      <div className="grid-2">
        <SelectField label={t('pf.aspect')} value={draft.aspect_ratio ?? '9:16'} onChange={(v) => set({ aspect_ratio: v })} options={['9:16', '1:1', '16:9', '4:5'].map((x) => ({ value: x, label: x }))} />
      </div>
      <ColorList label={t('pf.palette')} value={draft.palette ?? []} onChange={(v) => set({ palette: v })} />
      <AreaField label={t('pf.negative')} value={draft.negative_prompt ?? ''} onChange={(v) => set({ negative_prompt: v })} compact hint={t('pf.negative_hint')} />
      <fieldset className="card soft flat" style={{ margin: 0 }}>
        <legend className="strong">{t('pf.subtitle')}</legend>
        <div className="grid-3">
          <TextField label={t('pf.sub_font')} ltr value={sub.font ?? ''} onChange={(v) => setSub({ font: v })} />
          <NumberField label={t('pf.sub_size')} min={20} max={160} value={sub.size} onChange={(v) => setSub({ size: v ?? 64 })} />
          <SelectField label={t('pf.sub_pos')} value={sub.position ?? 'bottom'} onChange={(v) => setSub({ position: v })} options={[{ value: 'bottom', label: t('pf.pos_bottom') }, { value: 'middle', label: t('pf.pos_middle') }, { value: 'top', label: t('pf.pos_top') }]} />
          <div className="field">
            <label htmlFor="sub-color">{t('pf.sub_color')}</label>
            <input id="sub-color" type="color" value={sub.color ?? '#ffffff'} onChange={(e) => setSub({ color: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="sub-outline">{t('pf.sub_outline')}</label>
            <input id="sub-outline" type="color" value={sub.outline ?? '#000000'} onChange={(e) => setSub({ outline: e.target.value })} />
          </div>
        </div>
      </fieldset>
    </>
  )
}

function AudioForm({ draft, set }: FormProps) {
  const { t } = useI18n()
  return (
    <>
      <div className="grid-2">
        <SelectField label={t('pf.narration_engine')} value={draft.narration_engine ?? 'auto'} onChange={(v) => set({ narration_engine: v })} options={[
          { value: 'auto', label: t('pf.engine_auto') },
          { value: 'moss', label: 'MOSS-TTS' },
          { value: 'piper', label: 'Piper' },
          { value: 'fake', label: t('pf.engine_fake') },
        ]} hint={t('pf.engine_hint')} />
        <TextField label={t('pf.narration_voice')} ltr value={draft.narration_voice ?? ''} onChange={(v) => set({ narration_voice: v })} />
        <SelectField label={t('pf.audio_lang')} value={draft.language ?? 'fa'} onChange={(v) => set({ language: v })} options={[{ value: 'fa', label: 'فارسی' }, { value: 'en', label: 'English' }]} />
        <NumberField label={t('pf.lufs')} min={-30} max={-8} value={draft.target_lufs} onChange={(v) => set({ target_lufs: v ?? -16 })} hint={t('pf.lufs_hint')} />
      </div>
      <div className="grid-2">
        <div className="stack-sm">
          <SwitchField label={t('pf.music')} checked={!!draft.music_enabled} onChange={(v) => set({ music_enabled: v })} />
          <TextField label={t('pf.music_mood')} value={draft.music_mood ?? ''} onChange={(v) => set({ music_mood: v })} disabled={!draft.music_enabled} />
          <NumberField label={t('pf.music_vol')} min={-60} max={0} value={draft.music_volume_db} onChange={(v) => set({ music_volume_db: v ?? -22 })} disabled={!draft.music_enabled} />
        </div>
        <SwitchField label={t('pf.sfx')} checked={!!draft.sfx_enabled} onChange={(v) => set({ sfx_enabled: v })} />
      </div>
      <Notice tone="info">{t('pf.audio_note')}</Notice>
    </>
  )
}

function ProductionForm({ draft, set, formats }: FormProps & { formats: Formats }) {
  const { t, tr, lang } = useI18n()
  const allowed: string[] = draft.allowed_techniques ?? []
  return (
    <>
      <SelectField label={t('wiz.preset')} value={draft.preset ?? 'balanced'} onChange={(v) => set({ preset: v })} options={Object.entries(formats.presets).map(([k, p]) => ({ value: k, label: lang === 'en' ? `${p.label_en ?? p.label_fa} — ${p.note_en ?? p.note_fa}` : `${p.label_fa} — ${p.note_fa}` }))} />
      <div className="grid-3">
        <NumberField label={t('pf.eps_per_series')} min={1} max={60} value={draft.episodes_per_series} onChange={(v) => set({ episodes_per_series: v ?? 5 })} />
        <NumberField label={t('wiz.length')} min={10} max={180} value={draft.episode_length_sec} onChange={(v) => set({ episode_length_sec: v ?? 45 })} />
        <NumberField label={t('pf.max_gpu')} min={1} max={1440} value={draft.max_gpu_minutes_per_episode} onChange={(v) => set({ max_gpu_minutes_per_episode: v ?? 60 })} hint={t('pf.max_gpu_hint')} />
        <NumberField label={t('pf.fps')} min={12} max={60} value={draft.fps} onChange={(v) => set({ fps: v ?? 30 })} />
        <NumberField label={t('pf.preview_h')} min={240} max={1280} value={draft.preview_height} onChange={(v) => set({ preview_height: v ?? 640 })} />
        <NumberField label={t('pf.final_h')} min={480} max={2560} value={draft.final_height} onChange={(v) => set({ final_height: v ?? 1920 })} />
      </div>
      <SwitchField label={t('pf.preview_default')} hint={t('pf.preview_default_hint')} checked={!!draft.preview_default} onChange={(v) => set({ preview_default: v })} />
      <SwitchField label={t('wiz.studio')} hint={t('wiz.studio_hint')} checked={!!draft.studio_mode} onChange={(v) => set({ studio_mode: v })} />
      <TextModelsCard value={draft.llm} onChange={(v) => set({ llm: v })} />
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="field-label">{t('pf.techniques')}</legend>
        <p className="field-hint">{t('pf.techniques_hint')}</p>
        <div className="stack-sm">
          {formats.techniques.map((k) => (
            <CheckField
              key={k}
              label={tr('tech.' + k, k)}
              hint={<>{tr('tech.' + k + '.desc', '')}{!IMPLEMENTED_TECHNIQUES.includes(k) && <> <span className="badge warn">{t('tech.fallback_badge')}</span></>}</>}
              checked={allowed.includes(k)}
              onChange={(on) => set({ allowed_techniques: on ? [...allowed, k] : allowed.filter((x) => x !== k) })}
            />
          ))}
        </div>
      </fieldset>
    </>
  )
}

function PublishingForm({ draft, set }: FormProps) {
  const { t, tr } = useI18n()
  const days: string[] = draft.days ?? []
  return (
    <>
      <Notice tone="info">{t('pub.manual_note')}</Notice>
      <div className="grid-3">
        <SelectField label={t('pf.platform')} value={draft.platform ?? 'instagram'} onChange={(v) => set({ platform: v })} options={[{ value: 'instagram', label: 'Instagram' }]} />
        <NumberField label={t('strat.per_week')} min={1} max={21} value={draft.per_week} onChange={(v) => set({ per_week: v ?? 3 })} />
        <TextField label={t('pf.time')} type="time" ltr value={draft.time ?? '20:00'} onChange={(v) => set({ time: v })} />
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="field-label">{t('pf.days')}</legend>
        <div className="row" style={{ gap: '0.75rem 1.25rem' }}>
          {WEEKDAYS.map((d) => (
            <CheckField key={d} label={tr('day.' + d)} checked={days.includes(d)} onChange={(on) => set({ days: on ? [...days, d] : days.filter((x) => x !== d) })} />
          ))}
        </div>
      </fieldset>
      <AreaField label={t('pf.caption_style')} value={draft.caption_style ?? ''} onChange={(v) => set({ caption_style: v })} compact hint={t('pf.caption_style_hint')} />
      <TagsField label={t('strat.hashtags')} value={draft.hashtags ?? []} onChange={(v) => set({ hashtags: v })} ltr />
      <SwitchField label={t('pf.auto_publish')} hint={t('pf.auto_publish_hint')} checked={false} onChange={() => undefined} disabled />
    </>
  )
}

// ---------------------------------------------------------------- AI strategy for an existing page
function StrategyProposal({ page, setPage }: { page: PageDetail; setPage: (p: PageDetail) => void }) {
  const { t } = useI18n()
  const [strategy, setStrategy] = useState<Strategy | null>(null)
  const [chars, setChars] = useState<string[]>([])
  const runner = useJobRunner<{ strategy: Strategy }>({
    onSucceeded: (j) => {
      const st = j.result.strategy as Strategy | undefined
      if (st) {
        setStrategy({ ...st, characters: st.characters ?? [] })
        const have = new Set(page.characters.map((c) => c.name))
        setChars((st.characters ?? []).map((c) => c.name).filter((n) => n && !have.has(n)))
      }
    },
  })
  const apply = useAction()
  const doApply = async () => {
    if (!strategy) return
    const keep = (strategy.characters ?? []).filter((c) => chars.includes(c.name))
    const p = await apply.run(() => api.post<PageDetail>(`/pages/${page.id}/apply-strategy`, { strategy: { ...strategy, characters: keep } }), { success: t('strat.applied') })
    if (p) {
      setPage(p)
      setStrategy(null)
      runner.reset()
    }
  }
  return (
    <Card title={t('strat.ai_title')}>
      <div className="stack">
        <p className="muted">{t('strat.ai_text')}</p>
        <div>
          <Button icon="spark" busy={runner.starting} disabled={runner.busy} onClick={() => runner.start(() => api.post(`/pages/${page.id}/strategy`, {}))}>
            {t('wiz.propose')}
          </Button>
        </div>
        {runner.job && !runner.succeeded && <JobView job={runner.job} offline={runner.offline} />}
        {strategy && (
          <div className="stack">
            <Notice tone="info">{t('strat.ai_note')}</Notice>
            <StrategyEditor value={strategy} onChange={setStrategy} />
            {chars.length > 0 && <TagsField label={t('strat.new_chars')} hint={t('strat.new_chars_hint')} value={chars} onChange={setChars} />}
            <div className="row">
              <Button variant="primary" icon="check" busy={apply.busy} onClick={doApply}>
                {t('strat.apply')}
              </Button>
              <Button onClick={() => setStrategy(null)}>{t('strat.discard')}</Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- reusable templates
function TemplatesCard({ kind, draft, page, setPage }: { kind: ProfileKind; draft: Draft; page: PageDetail; setPage: (p: PageDetail) => void }) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const q = useQuery<ProfileTemplate[]>(`/profile-templates?kind=${kind}`)
  const [name, setName] = useState('')
  const [pick, setPick] = useState('')
  const act = useAction()
  const saveTpl = async () => {
    const r = await act.run(() => api.post<ProfileTemplate>('/profile-templates', { kind, name: name.trim(), data: draft }), { success: t('tpl.saved') })
    if (r) {
      setName('')
      q.reload()
    }
  }
  const apply = async () => {
    if (!pick) return
    if (!(await confirm({ message: t('tpl.apply_confirm'), confirmLabel: t('tpl.apply') }))) return
    const p = await act.run(() => api.post<PageDetail>(`/pages/${page.id}/apply-template`, { template_id: Number(pick) }), { success: t('tpl.applied') })
    if (p) setPage(p)
  }
  const list = q.data ?? []
  return (
    <Card title={t('tpl.title')}>
      <div className="grid-2">
        <div className="stack-sm">
          <TextField label={t('tpl.name')} value={name} onChange={setName} hint={t('tpl.save_hint')} />
          <div>
            <Button icon="save" disabled={!name.trim()} busy={act.busy} onClick={saveTpl}>
              {t('tpl.save')}
            </Button>
          </div>
        </div>
        <div className="stack-sm">
          <SelectField
            label={t('tpl.pick')}
            value={pick}
            onChange={setPick}
            options={[{ value: '', label: list.length ? t('tpl.pick_ph') : t('tpl.none') }, ...list.map((tp) => ({ value: String(tp.id), label: tp.name || `#${tp.id}` }))]}
          />
          <div>
            <Button disabled={!pick} onClick={apply}>
              {t('tpl.apply')}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
