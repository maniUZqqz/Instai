import { useEffect, useId, useState } from 'react'
import { useQuery } from '../hooks'
import { useI18n } from '../i18n'
import type { OpsConfig, When } from './types'

/** "When should this download happen?": now / at a time (next 03:30) / inside the night window (the saved window, default 02:00-07:00).
 *  Always reports an explicit choice through `onChange` (also once at start), so "now" really means now even when the saved default is the night. */
export function ScheduleField({ onChange, initial }: { onChange: (w: When) => void; initial?: When['mode'] }) {
  const { t } = useI18n()
  const name = useId()
  const cfg = useQuery<OpsConfig>('/ops/config')
  const [mode, setMode] = useState<'now' | 'at' | 'window'>(initial === 'at' || initial === 'window' ? initial : 'now')
  const [time, setTime] = useState('03:30')
  const [seeded, setSeeded] = useState(initial !== undefined)
  useEffect(() => {
    if (!seeded && cfg.data) {
      setMode(cfg.data.download_mode === 'window' ? 'window' : 'now')
      setSeeded(true)
    }
  }, [cfg.data, seeded])
  useEffect(() => {
    onChange(mode === 'at' ? { mode: 'at', time } : mode === 'window' ? { mode: 'window' } : { mode: 'now' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, time])
  const win = cfg.data?.download_window ?? '02:00-07:00'
  const opt = (m: 'now' | 'at' | 'window', label: string, extra?: React.ReactNode) => (
    <label className="check" key={m}>
      <input type="radio" name={name} checked={mode === m} onChange={() => setMode(m)} />
      <span className="check-text">
        {label} {extra}
      </span>
    </label>
  )
  return (
    <fieldset className="stack-sm" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="strong small">{t('ops.sched.legend')}</legend>
      {opt('now', t('ops.sched.now'))}
      {opt(
        'at',
        t('ops.sched.at'),
        <input type="time" value={time} onChange={(e) => { setTime(e.target.value || '03:30'); setMode('at') }} aria-label={t('ops.sched.at')} className="ltr time-input" />,
      )}
      {opt('window', t('ops.sched.window'), <bdi dir="ltr">{win}</bdi>)}
      <span className="small muted">{mode === 'now' ? t('ops.sched.hint_now') : mode === 'at' ? t('ops.sched.hint_at') : t('ops.sched.hint_window')}</span>
    </fieldset>
  )
}
