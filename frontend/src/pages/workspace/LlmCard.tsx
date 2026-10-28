import type { LlmConfig, LlmSpec, ProviderInfo, SettingsPayload } from '../../api/types'
import { Badge, Notice, SelectField, TextField } from '../../components/ui'
import { useQuery } from '../../hooks'
import { useI18n } from '../../i18n'

export const LLM_GROUPS = ['strategy', 'brainstorm', 'research', 'bible', 'script', 'translate'] as const

/** Text model per page and per task group (brainstorm via an API, scripts via Ollama ...) with a fallback. Only provider and model NAMES are stored on the page. */
export function TextModelsCard({ value, onChange }: { value: LlmConfig | undefined; onChange: (v: LlmConfig) => void }) {
  const { t } = useI18n()
  const q = useQuery<SettingsPayload>('/settings')
  const cfg: LlmConfig = { default: { provider: '', model: '' }, fallback: { provider: '', model: '' }, groups: {}, ...(value ?? {}) }
  const providers = q.data?.providers ?? []
  const setGroup = (g: string, spec: LlmSpec) => {
    const groups = { ...cfg.groups }
    if (!spec.provider && !spec.model) delete groups[g]
    else groups[g] = spec
    onChange({ ...cfg, groups })
  }
  return (
    <fieldset className="card soft flat stack" style={{ margin: 0 }}>
      <legend className="strong">{t('llm.title')}</legend>
      <p className="small muted">{t('llm.intro')}</p>
      <SpecRow label={t('llm.default')} hint={t('llm.default_hint')} spec={cfg.default} providers={providers} onChange={(s) => onChange({ ...cfg, default: s })} global={q.data?.values.llm_provider} id="llm-default" />
      <div className="stack-sm">
        <h3>{t('llm.per_task')}</h3>
        {LLM_GROUPS.map((g) => (
          <SpecRow key={g} label={t(('llm.group.' + g) as 'llm.group.script')} spec={cfg.groups[g] ?? { provider: '', model: '' }} providers={providers} onChange={(s) => setGroup(g, s)} inheritLabel={t('llm.inherit')} id={'llm-' + g} />
        ))}
      </div>
      <SpecRow label={t('llm.fallback')} hint={t('llm.fallback_hint')} spec={cfg.fallback} providers={providers} onChange={(s) => onChange({ ...cfg, fallback: s })} inheritLabel={t('llm.no_fallback')} id="llm-fallback" />
      <Notice tone="info">{t('llm.keys_note')}</Notice>
    </fieldset>
  )
}

function SpecRow({ label, hint, spec, providers, onChange, global, inheritLabel, id }: {
  label: string
  hint?: string
  spec: LlmSpec
  providers: ProviderInfo[]
  onChange: (s: LlmSpec) => void
  global?: string
  inheritLabel?: string
  id: string
}) {
  const { t } = useI18n()
  const cur = providers.find((p) => p.id === spec.provider)
  const opts = [
    { value: '', label: inheritLabel ?? `${t('llm.global')}${global ? ` (${global})` : ''}` },
    ...(['ollama', 'openai', 'fake'] as const).map((id) => {
      const p = providers.find((x) => x.id === id)
      return { value: id, label: `${t(('llm.prov_' + id) as 'llm.prov_ollama')}${p ? (p.ok ? '' : ' · ' + t('llm.not_ready')) : ''}` }
    }),
  ]
  const listId = id + '-models'
  return (
    <div className="grid-2 llm-row">
      <SelectField label={label} hint={hint} value={spec.provider} onChange={(v) => onChange({ provider: v, model: v === spec.provider ? spec.model : '' })} options={opts} />
      {spec.provider && spec.provider !== 'fake' ? (
        <>
          <TextField label={t('llm.model')} ltr value={spec.model} onChange={(v) => onChange({ ...spec, model: v })} list={listId} placeholder={t('llm.model_ph')} />
          <datalist id={listId}>{(cur?.models ?? []).map((m) => <option key={m} value={m} />)}</datalist>
        </>
      ) : (
        <div className="field"><span className="small muted">{spec.provider === 'fake' ? <Badge>{t('llm.demo_badge')}</Badge> : t('llm.model_global')}</span></div>
      )}
    </div>
  )
}
