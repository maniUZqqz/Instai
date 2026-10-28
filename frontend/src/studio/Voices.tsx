import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useConfirm } from '../components/feedback'
import { JobView } from '../components/domain'
import { Async, AreaField, Badge, Button, Card, CardSkeletons, CheckField, Empty, Notice, NumberField, PageHead, SelectField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import type { CharacterVoices, EngineInfo, EnginesPayload, VoicePreviewResult, VoiceRef, WarningText } from './api'
import { fileToBase64, licenceTone, PageCharacterPicker } from './shared'
import { useS } from './useS'
import type { StudioKey } from './i18n'
import './studio.css'

const LANGS = ['fa', 'en'] as const
type Lang = (typeof LANGS)[number]
const MIN_SECONDS = 3
const MAX_SECONDS = 30
const MAX_BYTES = 10 * 1024 * 1024

/** The warning text in the UI language: the API's `warning_text` first, our own text as the fallback. */
function useWarningText() {
  const { s, lang } = useS()
  return (key: string | null | undefined, text?: WarningText | null): string => {
    if (!key) return ''
    if (text) return text[lang] || text.en
    const own = `vc.warn_${key}` as StudioKey
    return s(own)
  }
}

function warningTone(e: { commercial: string }): 'warn' | 'info' {
  return e.commercial === 'no' ? 'warn' : 'info'
}

function EngineWarning({ engine, testid }: { engine: Pick<EngineInfo, 'warning' | 'warning_text' | 'commercial' | 'id'>; testid?: string }) {
  const wt = useWarningText()
  if (!engine.warning) return null
  return (
    <div data-testid={testid ?? `warning-${engine.id}`}>
      <Notice tone={warningTone(engine)}>{wt(engine.warning, engine.warning_text)}</Notice>
    </div>
  )
}

// ---------------------------------------------------------------- engines and services overview
function EnginesOverview({ data }: { data: EnginesPayload }) {
  const { s } = useS()
  return (
    <Card title={s('vc.engines')}>
      <div className="stack">
        <p className="muted small">{s('vc.engines_intro')}</p>
        <div className="grid-auto">
          {data.engines.map((e) => (
            <section key={e.id} className="card flat stack-sm" data-testid={`engine-${e.id}`} aria-label={e.label}>
              <div className="row between">
                <h3 style={{ fontSize: '1rem' }}>{e.label}</h3>
                <Badge tone={e.available ? 'ok' : 'neutral'}>{e.available ? s('vc.available') : s('vc.not_ready')}</Badge>
              </div>
              <div className="row">
                <Badge tone={licenceTone(e.commercial)} title={s('vc.licence')}>{e.badge}</Badge>
                {e.online && <Badge tone="warn">{s('vc.online')}</Badge>}
                {e.needs_reference && <Badge tone="info">{s('vc.clones')}</Badge>}
              </div>
              <div className="small muted">{s('vc.languages')}: <span className="ltr">{e.languages.join(' / ')}</span> · {s('vc.resource')}: <span className="ltr">{e.resource}</span></div>
              <div className="small muted ltr">{e.detail}</div>
              <EngineWarning engine={e} />
            </section>
          ))}
        </div>
        <p className="small muted">{data.auto_note ? s('vc.auto_note') : ''}</p>
        <div className="stack-sm">
          <h3 style={{ fontSize: '1rem' }}>{s('vc.services')}</h3>
          <div className="grid-auto">
            {data.services.map((sv) => (
              <div key={sv.id} className="card flat stack-sm" data-testid={`service-${sv.id}`}>
                <div className="row between">
                  <span className="strong">{sv.label}</span>
                  <Badge tone={sv.status === 'ready' ? 'ok' : sv.status === 'error' ? 'err' : sv.status === 'loading' ? 'info' : 'neutral'}>{s(`vc.sv_${sv.status}` as StudioKey)}</Badge>
                </div>
                <div className="row">
                  <Badge tone={sv.installed ? 'ok' : 'warn'}>{sv.installed ? s('vc.installed') : s('vc.not_installed')}</Badge>
                  <Badge tone={sv.commercial === 'yes' ? 'ok' : 'warn'}>{sv.licence}</Badge>
                </div>
                {!sv.installed && <div className="small muted">{s('vc.install_hint', { pkg: sv.package })}</div>}
              </div>
            ))}
          </div>
          <div className="row">
            {data.audio.map((a) => (
              <span key={a.id} className="small" data-testid={`audio-${a.data.engine}`}>
                <Badge tone={a.status === 'ok' ? 'ok' : 'neutral'}>{a.label}</Badge> <span className="muted">{a.detail}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- one cast (character x language)
function CastCard({ lang, payload, cast, refs, characterId, onChanged }: {
  lang: Lang
  payload: EnginesPayload
  cast?: CharacterVoices['casts'][number]
  refs: VoiceRef[]
  characterId: number
  onChanged: () => void
}) {
  const { s } = useS()
  const wt = useWarningText()
  const act = useAction()
  const [engine, setEngine] = useState(cast?.engine ?? 'auto')           // never preselects Pocket / Edge: only what was saved
  const [voiceId, setVoiceId] = useState(cast?.voice_id ?? '')
  const [refId, setRefId] = useState(cast?.reference ? String(cast.reference) : '')
  const [speed, setSpeed] = useState<number | null>(cast?.speed ?? 1)
  const [text, setText] = useState(lang === 'fa' ? s('vc.sample_fa') : s('vc.sample_en'))
  const preview = useJobRunner<VoicePreviewResult>()

  const effective = refId ? 'moss' : engine
  const info = payload.engines.find((e) => e.id === effective)
  const options = [{ value: 'auto', label: s('vc.auto') }].concat(
    payload.engines
      .filter((e) => (e.languages.includes(lang) && e.id !== 'fake') || e.id === engine)
      .map((e) => ({ value: e.id, label: `${e.label} [${e.badge}]${e.available ? '' : ' - ' + s('vc.not_ready')}` })),
  )
  const myRefs = refs.filter((r) => r.language === lang)
  const voiceOptions = info?.voices ?? []

  const save = () =>
    act.run(async () => {
      await api.put(`/characters/${characterId}/voices/${lang}`, { engine: effective, voice_id: refId ? '' : voiceId, reference: refId ? Number(refId) : null, speed: speed ?? 1 })
      onChanged()
    }, { success: s('vc.saved') })
  const remove = () =>
    act.run(async () => {
      await api.del(`/characters/${characterId}/voices/${lang}`)
      onChanged()
    }, { success: s('vc.removed') })
  const listen = () =>
    preview.start(() => api.post('/voices/preview', { engine: effective, voice: refId ? '' : voiceId, language: lang, text, reference_id: refId ? Number(refId) : null }))

  const res = preview.result
  return (
    <section className="card flat stack" data-testid={`cast-${lang}`} aria-label={s(lang === 'fa' ? 'vc.lang_fa' : 'vc.lang_en')}>
      <div className="row between">
        <h3 style={{ fontSize: '1.05rem' }}>{s(lang === 'fa' ? 'vc.lang_fa' : 'vc.lang_en')}</h3>
        {cast ? <Badge tone="ok">{s('vc.cast_saved')}</Badge> : <Badge>{s('vc.cast_none')}</Badge>}
      </div>
      <SelectField label={s('vc.engine')} value={effective} onChange={(v) => { setEngine(v); setVoiceId('') }} options={options} disabled={!!refId} hint={refId ? s('vc.ref_forces_moss') : s('vc.engine_hint')} aria-label={`${s('vc.engine')} ${lang}`} />
      {info && info.warning && (
        <div data-testid={`cast-warning-${lang}`}>
          <Notice tone={warningTone(info)}>
            <strong>{info.badge}</strong> — {wt(info.warning, info.warning_text)}
          </Notice>
        </div>
      )}
      {!refId && effective !== 'auto' && (voiceOptions.length > 0 ? (
        <SelectField
          label={s('vc.voice')}
          value={voiceId}
          onChange={setVoiceId}
          options={[{ value: '', label: s('vc.default_voice', { v: info?.default_voice || '—' }) }, ...voiceOptions.map((v) => ({ value: v.id, label: `${v.label}${v.gender ? ' (' + v.gender + ')' : ''}` }))]}
        />
      ) : (
        <TextField label={s('vc.voice')} value={voiceId} onChange={setVoiceId} ltr placeholder={info?.default_voice || ''} hint={s('vc.voice_free_hint')} />
      ))}
      <SelectField
        label={s('vc.reference')}
        value={refId}
        onChange={setRefId}
        options={[{ value: '', label: s('vc.no_reference') }, ...myRefs.map((r) => ({ value: String(r.id), label: `${r.label || r.person_name || '#' + r.id}${r.person_name ? ' — ' + r.person_name : ''}` }))]}
        hint={myRefs.length === 0 ? s('vc.no_refs_for_lang') : s('vc.reference_hint')}
      />
      <NumberField label={s('vc.speed')} value={speed} onChange={setSpeed} min={0.6} max={1.6} step={0.05} />
      <div className="row">
        <Button variant="primary" icon="save" busy={act.busy} onClick={save}>{s('vc.save')}</Button>
        {cast && <Button variant="danger" icon="trash" busy={act.busy} onClick={remove}>{s('vc.remove')}</Button>}
      </div>
      <hr className="divider" />
      <div className="stack-sm">
        <AreaField label={s('vc.preview_text')} value={text} onChange={setText} compact rows={2} maxLength={400} />
        <div className="row">
          <Button icon="play" busy={preview.busy} disabled={!text.trim()} onClick={listen}>{s('vc.listen')}</Button>
        </div>
        {preview.job && preview.busy && <JobView job={preview.job} offline={preview.offline} compact />}
        {preview.failed && preview.job && <Notice tone="err">{preview.job.error || s('vc.preview_failed')}</Notice>}
        {res && (
          <div className="stack-sm" data-testid={`preview-${lang}`}>
            <audio controls src={res.url} aria-label={s('vc.preview_audio')} style={{ width: '100%' }} />
            <div className="row">
              <Badge tone={licenceTone(res.licence.commercial)}>{res.licence.badge}</Badge>
              <span className="small muted ltr">{res.engine}</span>
            </div>
            {res.licence.warning && (
              <div data-testid={`preview-warning-${lang}`}>
                <Notice tone={res.licence.commercial === 'no' ? 'warn' : 'info'}>{wt(res.licence.warning, res.licence.warning_text)}</Notice>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- consented voice references
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const a = new Audio()
    const done = (v: number | null) => {
      URL.revokeObjectURL(url)
      resolve(v)
    }
    a.preload = 'metadata'
    a.onloadedmetadata = () => done(Number.isFinite(a.duration) ? a.duration : null)
    a.onerror = () => done(null)
    a.src = url
  })
}

function RefsCard({ characterId, refs, templates, onChanged }: { characterId: number; refs: VoiceRef[]; templates: { fa: string; en: string }; onChanged: () => void }) {
  const { s, f } = useS()
  const confirm = useConfirm()
  const act = useAction()
  const [lang, setLang] = useState<Lang>('fa')
  const [label, setLabel] = useState('')
  const [person, setPerson] = useState('')
  const [purpose, setPurpose] = useState('')
  const [consent, setConsent] = useState(false)
  const [consentText, setConsentText] = useState('')
  const [touched, setTouched] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [seconds, setSeconds] = useState<number | null>(null)
  const [fileError, setFileError] = useState('')
  const template = lang === 'fa' ? templates.fa : templates.en
  const filled = useMemo(() => template.replace('{person}', person.trim() || '…').replace('{purpose}', purpose.trim() || '…'), [template, person, purpose])
  useEffect(() => {
    if (!touched) setConsentText(filled)
  }, [filled, touched])

  const pickFile = async (fl: File | null) => {
    setFile(fl)
    setSeconds(null)
    setFileError('')
    if (!fl) return
    if (fl.size > MAX_BYTES) {
      setFileError(s('vc.file_too_big'))
      return
    }
    const d = await readDuration(fl)
    setSeconds(d)
    if (d !== null && (d < MIN_SECONDS || d > MAX_SECONDS)) setFileError(s('vc.file_length', { min: MIN_SECONDS, max: MAX_SECONDS, now: Math.round(d * 10) / 10 }))
  }

  const reasons: string[] = []
  if (!consent) reasons.push(s('vc.need_consent'))
  if (!person.trim()) reasons.push(s('vc.need_person'))
  if (!purpose.trim()) reasons.push(s('vc.need_purpose'))
  if (!consentText.trim()) reasons.push(s('vc.need_consent_text'))
  if (!file) reasons.push(s('vc.need_file'))
  if (fileError) reasons.push(fileError)
  const blocked = reasons.length > 0

  const submit = () =>
    act.run(async () => {
      if (!file) return
      const b64 = await fileToBase64(file)
      await api.post(`/characters/${characterId}/voice-refs`, {
        language: lang, label: label.trim() || person.trim(), person_name: person.trim(), purpose: purpose.trim(), consent_given: consent, consent_text: consentText.trim(),
        audio_base64: b64, filename: file.name,
      })
      setLabel('')
      setPerson('')
      setPurpose('')
      setConsent(false)
      setTouched(false)
      setFile(null)
      setSeconds(null)
      onChanged()
    }, { success: s('vc.ref_created') })
  const del = async (r: VoiceRef) => {
    if (!(await confirm({ title: s('vc.ref_delete'), message: s('vc.ref_delete_confirm', { name: r.label || r.person_name || `#${r.id}` }), confirmLabel: s('vc.ref_delete'), danger: true }))) return
    await act.run(async () => {
      await api.del(`/voice-refs/${r.id}`)
      onChanged()
    }, { success: s('vc.ref_deleted') })
  }

  return (
    <Card title={s('vc.refs')}>
      <div className="stack">
        <Notice tone="info">{s('vc.refs_intro')}</Notice>
        {refs.length === 0 ? (
          <Empty icon="users" title={s('vc.refs_empty')} text={s('vc.refs_empty_text')} />
        ) : (
          <ul className="studio-refs" aria-label={s('vc.refs')}>
            {refs.map((r) => (
              <li key={r.id} className="card flat stack-sm" data-testid="voice-ref">
                <div className="row between">
                  <span className="strong">{r.label || r.person_name || `#${r.id}`}</span>
                  <Button size="sm" variant="ghost" iconOnly icon="trash" aria-label={`${s('vc.ref_delete')}: ${r.label || r.person_name}`} onClick={() => del(r)} />
                </div>
                <div className="row small">
                  <Badge tone="info">{r.language}</Badge>
                  <Badge tone="ok">{s('vc.consent_recorded')}</Badge>
                  {r.duration_sec != null && <span className="muted">{f.duration(r.duration_sec)}</span>}
                </div>
                <div className="small muted">{r.person_name}{r.purpose ? ` · ${r.purpose}` : ''}{r.consented_at ? ` · ${f.dateTime(r.consented_at)}` : ''}</div>
                {r.audio_url && <audio controls src={r.audio_url} style={{ width: '100%' }} aria-label={s('vc.preview_audio')} />}
              </li>
            ))}
          </ul>
        )}
        <hr className="divider" />
        <form className="stack" onSubmit={(e) => { e.preventDefault(); if (!blocked) submit() }} aria-label={s('vc.ref_form')} data-testid="ref-form">
          <h3 style={{ fontSize: '1rem' }}>{s('vc.ref_form')}</h3>
          <div className="grid-2">
            <SelectField label={s('vc.ref_language')} value={lang} onChange={(v) => { setLang(v as Lang); setTouched(false) }} options={[{ value: 'fa', label: s('vc.lang_fa') }, { value: 'en', label: s('vc.lang_en') }]} />
            <TextField label={s('vc.ref_label')} value={label} onChange={setLabel} maxLength={120} />
            <TextField label={s('vc.ref_person')} value={person} onChange={setPerson} required maxLength={160} />
            <TextField label={s('vc.ref_purpose')} value={purpose} onChange={setPurpose} required maxLength={200} hint={s('vc.ref_purpose_hint')} />
          </div>
          <AreaField label={s('vc.ref_consent_text')} value={consentText} onChange={(v) => { setConsentText(v); setTouched(true) }} rows={4} required />
          <CheckField label={s('vc.ref_consent_check')} hint={s('vc.ref_consent_hint')} checked={consent} onChange={setConsent} />
          <div className="field">
            <label htmlFor="voice-ref-file">{s('vc.ref_file')}<span className="req" aria-hidden="true"> *</span></label>
            <input id="voice-ref-file" type="file" accept="audio/*,.wav,.mp3" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} aria-describedby="voice-ref-file-h" />
            <div className="field-hint" id="voice-ref-file-h">{s('vc.ref_file_hint', { min: MIN_SECONDS, max: MAX_SECONDS })}{seconds !== null ? ` — ${f.duration(seconds)}` : ''}</div>
            {fileError && <div className="field-error" role="alert">{fileError}</div>}
          </div>
          {blocked && (
            <Notice tone="warn">
              <div data-testid="ref-blocked">{s('vc.ref_blocked')}: {reasons.join(' · ')}</div>
            </Notice>
          )}
          <div className="row">
            <Button type="submit" variant="primary" icon="plus" busy={act.busy} disabled={blocked} data-testid="ref-submit">{s('vc.ref_create')}</Button>
          </div>
        </form>
        {act.error && <Notice tone="err">{act.error}</Notice>}
      </div>
    </Card>
  )
}

function CharacterVoicesSection({ characterId, name, fa, en }: { characterId: number; name: string; fa: EnginesPayload; en: EnginesPayload }) {
  const { s } = useS()
  const q = useQuery<CharacterVoices>(`/characters/${characterId}/voices`)
  return (
    <Async q={q} skeleton={<CardSkeletons n={2} />}>
      {(d) => {
        const castOf = (l: Lang) => d.casts.find((c) => c.language === l)
        const key = (l: Lang) => {
          const c = castOf(l)
          return `${characterId}-${l}-${c?.id ?? 0}-${c?.engine}-${c?.voice_id}-${c?.reference}-${c?.speed}`
        }
        return (
          <>
            <Card title={s('vc.casting', { name })}>
              <div className="grid-2">
                <CastCard key={key('fa')} lang="fa" payload={fa} cast={castOf('fa')} refs={d.refs} characterId={characterId} onChanged={q.reload} />
                <CastCard key={key('en')} lang="en" payload={en} cast={castOf('en')} refs={d.refs} characterId={characterId} onChanged={q.reload} />
              </div>
            </Card>
            <RefsCard characterId={characterId} refs={d.refs} templates={fa.consent_templates} onChanged={q.reload} />
          </>
        )
      }}
    </Async>
  )
}

export default function Voices() {
  const { s } = useS()
  useTitle(s('vc.title'))
  const fa = useQuery<EnginesPayload>('/voices/engines?language=fa', { interval: 15000 })
  const en = useQuery<EnginesPayload>('/voices/engines?language=en')
  return (
    <div className="stack-lg">
      <PageHead title={s('vc.title')} crumbs={[{ label: s('studio.title'), to: '/studio' }, { label: s('vc.title') }]}>
        <Button icon="refresh" onClick={() => { fa.reload(); en.reload() }}>{s('common.refresh')}</Button>
      </PageHead>
      <p className="muted">{s('vc.intro')}</p>
      <Async q={fa} skeleton={<CardSkeletons n={2} />}>
        {(faData) => (
          <>
            <EnginesOverview data={faData} />
            <Async q={en} skeleton={<CardSkeletons n={1} />}>
              {(enData) => (
                <PageCharacterPicker>
                  {(p) => <CharacterVoicesSection characterId={p.character!.id} name={p.character!.name} fa={faData} en={enData} />}
                </PageCharacterPicker>
              )}
            </Async>
          </>
        )}
      </Async>
    </div>
  )
}
