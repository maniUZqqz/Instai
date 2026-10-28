import type { ReactNode } from 'react'
import type { CharacterVoice } from '../api/types'
import { useI18n } from '../i18n'
import { AreaField, CheckField, SelectField, TextField } from './ui'

export interface CharDraft {
  name: string
  role: string
  personality: string
  appearance: string
  abilities?: string
  motivations?: string
  profile?: string
  is_original: boolean
  franchise: string
  voice?: CharacterVoice
}

export const emptyChar = (): CharDraft => ({ name: '', role: '', personality: '', appearance: '', is_original: true, franchise: '' })

/** The fields of one character. `extended` adds abilities, motivations, background and voice settings (page workspace). */
export function CharacterFields({ value, onChange, extended, children }: { value: CharDraft; onChange: (c: CharDraft) => void; extended?: boolean; children?: ReactNode }) {
  const { t } = useI18n()
  const set = (patch: Partial<CharDraft>) => onChange({ ...value, ...patch })
  const voice = value.voice ?? {}
  const setVoice = (patch: Partial<CharacterVoice>) => set({ voice: { ...voice, ...patch } })
  return (
    <div className="stack">
      <div className="grid-2">
        <TextField label={t('char.name')} required value={value.name} onChange={(v) => set({ name: v })} />
        <TextField label={t('char.role')} value={value.role} onChange={(v) => set({ role: v })} placeholder={t('char.role_ph')} />
      </div>
      <AreaField label={t('char.personality')} compact value={value.personality} onChange={(v) => set({ personality: v })} />
      <AreaField label={t('char.appearance')} compact value={value.appearance} onChange={(v) => set({ appearance: v })} hint={t('char.appearance_hint')} />
      {extended && (
        <>
          <div className="grid-2">
            <AreaField label={t('char.abilities')} compact value={value.abilities ?? ''} onChange={(v) => set({ abilities: v })} />
            <AreaField label={t('char.motivations')} compact value={value.motivations ?? ''} onChange={(v) => set({ motivations: v })} />
          </div>
          <AreaField label={t('char.profile')} compact value={value.profile ?? ''} onChange={(v) => set({ profile: v })} />
          <fieldset className="card soft flat" style={{ margin: 0 }}>
            <legend className="strong">{t('char.voice')}</legend>
            <div className="grid-3">
              <SelectField
                label={t('char.voice_engine')}
                value={voice.engine ?? ''}
                onChange={(v) => setVoice({ engine: v })}
                options={[
                  { value: '', label: t('char.voice_default') },
                  { value: 'moss', label: 'MOSS-TTS' },
                  { value: 'piper', label: 'Piper' },
                  { value: 'fake', label: t('char.voice_fake') },
                ]}
              />
              <TextField label={t('char.voice_id')} ltr value={voice.voice_id ?? ''} onChange={(v) => setVoice({ voice_id: v })} />
              <SelectField
                label={t('char.voice_lang')}
                value={voice.language ?? ''}
                onChange={(v) => setVoice({ language: v })}
                options={[
                  { value: '', label: t('char.voice_default') },
                  { value: 'fa', label: 'فارسی' },
                  { value: 'en', label: 'English' },
                ]}
              />
            </div>
          </fieldset>
        </>
      )}
      <CheckField label={t('char.original')} hint={t('char.original_hint')} checked={value.is_original} onChange={(v) => set({ is_original: v })} />
      {!value.is_original && <TextField label={t('char.franchise')} value={value.franchise} onChange={(v) => set({ franchise: v })} hint={t('char.franchise_hint')} />}
      {children}
    </div>
  )
}
