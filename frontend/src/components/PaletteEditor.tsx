import { useI18n } from '../i18n'
import { Button } from './ui'

/** A list of colours (hex) the owner can pick, add and remove. */
export function PaletteEditor({ label, value, onChange, max = 8, roles }: { label: string; value: string[]; onChange: (v: string[]) => void; max?: number; roles?: string[] }) {
  const { t } = useI18n()
  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="field-label">{label}</legend>
      <div className="row">
        {value.map((c, i) => (
          <span key={i} className="row nw" style={{ gap: '0.25rem' }}>
            <input
              type="color"
              value={/^#[0-9a-f]{6}$/i.test(c) ? c : '#888888'}
              aria-label={`${label} ${i + 1}${roles?.[i] ? ' (' + t(('lib.role.' + roles[i]) as 'lib.role.primary') + ')' : ''}`}
              title={roles?.[i] ? t(('lib.role.' + roles[i]) as 'lib.role.primary') : undefined}
              onChange={(e) => onChange(value.map((x, j) => (j === i ? e.target.value.toUpperCase() : x)))}
            />
            <Button variant="ghost" size="sm" iconOnly icon="close" aria-label={t('common.remove')} onClick={() => onChange(value.filter((_, j) => j !== i))} />
          </span>
        ))}
        {value.length < max && (
          <Button size="sm" icon="plus" onClick={() => onChange([...value, '#3451C7'])}>
            {t('pf.add_color')}
          </Button>
        )}
      </div>
    </fieldset>
  )
}
