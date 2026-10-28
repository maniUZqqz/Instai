import { useId, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, NavLink, type LinkProps } from 'react-router-dom'
import { useI18n } from '../i18n'
import type { Query } from '../hooks'
import { ApiError, errorText } from '../api/client'
import { Icon, type IconName } from './Icon'

// ---------------------------------------------------------------- buttons
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'danger' | 'ghost' | 'default'
  size?: 'sm' | 'md'
  busy?: boolean
  icon?: IconName
  iconOnly?: boolean
  solid?: boolean
  block?: boolean
  wrap?: boolean
}

function btnClass(v: BtnProps['variant'], size: BtnProps['size'], extra: string) {
  return ['btn', v && v !== 'default' ? v : '', size === 'sm' ? 'sm' : '', extra].filter(Boolean).join(' ')
}

export function Button({ variant = 'default', size = 'md', busy, icon, iconOnly, solid, block, wrap, className, children, disabled, type = 'button', ...rest }: BtnProps) {
  const cls = btnClass(variant, size, [iconOnly ? 'icon' : '', solid ? 'solid' : '', block ? 'block' : '', wrap ? 'wrap' : '', className ?? ''].filter(Boolean).join(' '))
  return (
    <button {...rest} type={type} className={cls} disabled={disabled || busy} aria-busy={busy || undefined}>
      {busy ? <span className="spinner" aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  )
}

export function LinkButton({ variant = 'default', size = 'md', icon, className, children, ...rest }: LinkProps & { variant?: BtnProps['variant']; size?: BtnProps['size']; icon?: IconName }) {
  return (
    <Link {...rest} className={btnClass(variant, size, className ?? '')}>
      {icon && <Icon name={icon} />}
      {children}
    </Link>
  )
}

export function ExtLink({ href, children, download, className }: { href: string; children: ReactNode; download?: boolean; className?: string }) {
  return (
    <a href={href} className={className} {...(download ? { download: true } : { target: '_blank', rel: 'noreferrer noopener' })}>
      {children}
    </a>
  )
}

export { Link, NavLink }

// ---------------------------------------------------------------- badges and small blocks
export type Tone = 'neutral' | 'ok' | 'warn' | 'err' | 'info' | 'primary'
export function Badge({ tone = 'neutral', children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={'badge' + (tone !== 'neutral' ? ' ' + tone : '')} title={title}>
      {children}
    </span>
  )
}

export function Notice({ tone = 'info', children, icon, role }: { tone?: 'info' | 'warn' | 'err' | 'ok'; children: ReactNode; icon?: IconName; role?: 'alert' | 'status' }) {
  return (
    <div className={'notice ' + tone} role={role ?? (tone === 'err' ? 'alert' : undefined)}>
      <Icon name={icon ?? (tone === 'err' || tone === 'warn' ? 'alert' : tone === 'ok' ? 'check' : 'info')} />
      <div className="notice-body">{children}</div>
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row" role="status">
      <span className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  )
}

export function Loading({ label }: { label?: string }) {
  const { t } = useI18n()
  return (
    <div className="loading-block" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label ?? t('common.loading')}</span>
    </div>
  )
}

export function Skeleton({ lines = 3, height }: { lines?: number; height?: number }) {
  return (
    <div className="stack-sm" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: height ?? 18, width: i === lines - 1 ? '60%' : '100%' }} />
      ))}
    </div>
  )
}

export function CardSkeletons({ n = 3 }: { n?: number }) {
  const { t } = useI18n()
  return (
    <div className="grid-auto" role="status" aria-label={t('common.loading')}>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="card">
          <Skeleton lines={4} />
        </div>
      ))}
    </div>
  )
}

export function Empty({ icon = 'info', title, text, action }: { icon?: IconName; title: string; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} size={36} />
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n()
  const isNotFound = error instanceof ApiError && error.code === 'not_found'
  return (
    <div className="card" role="alert">
      <Notice tone="err">{errorText(error)}</Notice>
      {(onRetry || isNotFound) && (
        <div style={{ marginBlockStart: '0.75rem' }}>
          {isNotFound ? (
            <LinkButton to="/" icon="home">
              {t('nav.dashboard')}
            </LinkButton>
          ) : (
            <Button icon="refresh" onClick={onRetry}>
              {t('common.retry')}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

/** Show a skeleton while the first load runs, an error with retry, or the data. */
export function Async<T>({ q, skeleton, children }: { q: Query<T>; skeleton?: ReactNode; children: (data: T) => ReactNode }) {
  if (q.data !== undefined) return <>{children(q.data)}</>
  if (q.error) return <ErrorState error={q.error} onRetry={q.reload} />
  return <>{skeleton ?? <CardSkeletons />}</>
}

export function Progress({ value, tone, indeterminate, label }: { value?: number; tone?: 'ok' | 'warn' | 'err'; indeterminate?: boolean; label?: string }) {
  const pct = Math.max(0, Math.min(1, value ?? 0)) * 100
  return (
    <div
      className={'progress' + (indeterminate ? ' indeterminate' : '') + (tone ? ' ' + tone : '')}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(pct)}
    >
      <i style={{ width: pct + '%' }} />
    </div>
  )
}

export function PageHead({ title, children, crumbs }: { title: ReactNode; children?: ReactNode; crumbs?: { label: string; to?: string }[] }) {
  return (
    <>
      {crumbs && crumbs.length > 0 && <Breadcrumbs items={crumbs} />}
      <div className="page-head">
        <h1>{title}</h1>
        {children}
      </div>
    </>
  )
}

export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  const { t } = useI18n()
  return (
    <nav className="crumbs" aria-label={t('common.breadcrumbs')}>
      {items.map((it, i) => (
        <span key={i} className="row" style={{ gap: '0.4rem' }}>
          {i > 0 && <span className="sep" aria-hidden="true">/</span>}
          {it.to ? <Link to={it.to}>{it.label}</Link> : <span aria-current="page">{it.label}</span>}
        </span>
      ))}
    </nav>
  )
}

export function Card({ title, actions, children, className, soft }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; soft?: boolean }) {
  return (
    <section className={'card' + (soft ? ' soft' : '') + (className ? ' ' + className : '')}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h2 style={{ fontSize: '1.1rem' }}>{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

// ---------------------------------------------------------------- forms (label + control + hint + error in one component)
interface FieldBase {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  className?: string
}

function FieldShell({ label, hint, error, required, className, children, id }: FieldBase & { children: ReactNode; id: string }) {
  return (
    <div className={'field' + (className ? ' ' + className : '')}>
      <label htmlFor={id}>
        {label}
        {required && <span className="req" aria-hidden="true"> *</span>}
      </label>
      {children}
      {hint && <div className="field-hint" id={id + '-h'}>{hint}</div>}
      {error && <div className="field-error" id={id + '-e'} role="alert">{error}</div>}
    </div>
  )
}

const aria = (id: string, hint: unknown, error: unknown) => ({
  'aria-describedby': [hint ? id + '-h' : '', error ? id + '-e' : ''].filter(Boolean).join(' ') || undefined,
  'aria-invalid': error ? true : undefined,
})

export function TextField({
  label, hint, error, required, className, value, onChange, ltr, ...rest
}: FieldBase & { value: string; onChange: (v: string) => void; ltr?: boolean } & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  const id = useId()
  return (
    <FieldShell {...{ label, hint, error, required, className, id }}>
      <input {...rest} id={id} value={value} required={required} onChange={(e) => onChange(e.target.value)} className={ltr ? 'ltr' : undefined} {...aria(id, hint, error)} />
    </FieldShell>
  )
}

export function NumberField({
  label, hint, error, required, className, value, onChange, min, max, step, ...rest
}: FieldBase & { value: number | null | undefined; onChange: (v: number | null) => void; min?: number; max?: number; step?: number } & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'min' | 'max' | 'step'>) {
  const id = useId()
  return (
    <FieldShell {...{ label, hint, error, required, className, id }}>
      <input
        {...rest}
        id={id}
        type="number"
        inputMode="decimal"
        value={value ?? ''}
        min={min}
        max={max}
        step={step}
        className="ltr"
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        {...aria(id, hint, error)}
      />
    </FieldShell>
  )
}

export function AreaField({
  label, hint, error, required, className, value, onChange, compact, ...rest
}: FieldBase & { value: string; onChange: (v: string) => void; compact?: boolean } & Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'value' | 'onChange'>) {
  const id = useId()
  return (
    <FieldShell {...{ label, hint, error, required, className, id }}>
      <textarea {...rest} id={id} value={value} className={compact ? 'compact' : undefined} onChange={(e) => onChange(e.target.value)} {...aria(id, hint, error)} />
    </FieldShell>
  )
}

export interface Option {
  value: string
  label: string
  disabled?: boolean
}
export function SelectField({
  label, hint, error, required, className, value, onChange, options, ...rest
}: FieldBase & { value: string; onChange: (v: string) => void; options: Option[] } & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'value' | 'onChange'>) {
  const id = useId()
  return (
    <FieldShell {...{ label, hint, error, required, className, id }}>
      <select {...rest} id={id} value={value} onChange={(e) => onChange(e.target.value)} {...aria(id, hint, error)}>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
    </FieldShell>
  )
}

export function CheckField({ label, hint, checked, onChange, disabled }: { label: ReactNode; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="check-text">
        <span>{label}</span>
        {hint && <span className="field-hint">{hint}</span>}
      </span>
    </label>
  )
}

export function SwitchField({ label, hint, checked, onChange, disabled }: { label: ReactNode; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="switch">
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" aria-hidden="true" />
      <span className="check-text">
        <span className="strong">{label}</span>
        {hint && <span className="field-hint">{hint}</span>}
      </span>
    </label>
  )
}

/** A group of big radio cards. */
export function ChoiceGrid<T extends string>({ legend, value, onChange, options, name }: {
  legend: string
  value: T
  onChange: (v: T) => void
  name: string
  options: { value: T; title: ReactNode; text?: ReactNode; extra?: ReactNode }[]
}) {
  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <legend className="field-label" style={{ marginBlockEnd: '0.5rem' }}>{legend}</legend>
      <div className="choice-grid">
        {options.map((o) => (
          <label key={o.value} className={'choice' + (o.value === value ? ' selected' : '')}>
            <input type="radio" name={name} checked={o.value === value} onChange={() => onChange(o.value)} />
            {o.value === value && <Icon name="check" className="mark" />}
            <span className="strong">{o.title}</span>
            {o.text && <span className="small muted">{o.text}</span>}
            {o.extra}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

/** Editable list of short strings shown as chips (hashtags, pillars...). Enter or comma adds. */
export function TagsField({ label, hint, value, onChange, placeholder, ltr }: { label: ReactNode; hint?: ReactNode; value: string[]; onChange: (v: string[]) => void; placeholder?: string; ltr?: boolean }) {
  const { t } = useI18n()
  const id = useId()
  const [draft, setDraft] = useState('')
  const add = () => {
    const parts = draft.split(/[,،\n]/).map((s) => s.trim()).filter(Boolean)
    if (parts.length) onChange([...value, ...parts.filter((p) => !value.includes(p))])
    setDraft('')
  }
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {value.length > 0 && (
        <ul className="chips" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {value.map((v, i) => (
            <li key={v + i} className="chip">
              <span className={ltr ? 'ltr' : undefined}>{v}</span>
              <button type="button" aria-label={t('common.remove') + ': ' + v} onClick={() => onChange(value.filter((_, j) => j !== i))}>
                <Icon name="close" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <input
          id={id}
          type="text"
          className={ltr ? 'ltr' : undefined}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault()
              add()
            }
          }}
          onBlur={() => draft.trim() && add()}
          aria-describedby={hint ? id + '-h' : undefined}
        />
        <Button size="sm" icon="plus" onClick={add} disabled={!draft.trim()} aria-label={t('common.add')}>
          <span className="sr-only">{t('common.add')}</span>
        </Button>
      </div>
      {hint && <div className="field-hint" id={id + '-h'}>{hint}</div>}
    </div>
  )
}

/** Editable list of longer strings (rules, risks): one textarea per item. */
export function StringListField({ label, hint, value, onChange, addLabel, rows = 2 }: { label: ReactNode; hint?: ReactNode; value: string[]; onChange: (v: string[]) => void; addLabel?: string; rows?: number }) {
  const { t } = useI18n()
  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <legend className="field-label">{label}</legend>
      <div className="list-edit">
        {value.map((v, i) => (
          <div key={i} className="list-item">
            <textarea
              rows={rows}
              className="compact grow"
              value={v}
              aria-label={`${typeof label === 'string' ? label : ''} ${i + 1}`}
              onChange={(e) => onChange(value.map((x, j) => (j === i ? e.target.value : x)))}
              style={{ minHeight: '2.8rem' }}
            />
            <Button variant="ghost" size="sm" iconOnly icon="trash" aria-label={t('common.remove')} onClick={() => onChange(value.filter((_, j) => j !== i))} />
          </div>
        ))}
        <div>
          <Button size="sm" icon="plus" onClick={() => onChange([...value, ''])}>
            {addLabel ?? t('common.add')}
          </Button>
        </div>
      </div>
      {hint && <div className="field-hint">{hint}</div>}
    </fieldset>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { key: T; label: ReactNode; badge?: ReactNode }[]; value: T; onChange: (k: T) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tb) => (
        <button key={tb.key} role="tab" type="button" aria-selected={tb.key === value} onClick={() => onChange(tb.key)}>
          {tb.label}
          {tb.badge}
        </button>
      ))}
    </div>
  )
}

export function Segmented<T extends string>({ options, value, onChange, label }: { options: { key: T; label: ReactNode }[]; value: T; onChange: (k: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={o.key === value} onClick={() => onChange(o.key)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
