import { useCallback } from 'react'
import type { Job } from '../api/types'
import { LocalJob } from '../pages/series/dev/common'
import { Notice } from '../components/ui'
import { useI18n } from '../i18n'

/** Persian first, English second: `L('فارسی', 'English')`. The texts of the studio pipeline screens live next to the code that shows them. */
export function usePL() {
  const { lang, f } = useI18n()
  const L = useCallback((fa: string, en: string) => (lang === 'fa' ? fa : en), [lang])
  /** A server row with `<key>_fa` / `<key>_en` (or `fa` / `en`). */
  const pick = useCallback(<T extends Record<string, unknown>>(row: T, key = ''): string => {
    const a = (row[key ? `${key}_fa` : 'fa'] as string | undefined) ?? ''
    const b = (row[key ? `${key}_en` : 'en'] as string | undefined) ?? ''
    return lang === 'fa' ? a || b : b || a
  }, [lang])
  /** Numbers in the post numbering follow the language (Persian digits in Persian). */
  const n = useCallback((v: number | string | null | undefined) => (v === null || v === undefined ? '' : lang === 'fa' ? f.num(Number(v)) : String(v)), [lang, f])
  return { L, pick, n, lang, f }
}

export function JobLine({ job, offline }: { job: Job | null; offline?: boolean }) {
  if (!job) return null
  return <LocalJob job={job} offline={offline} />
}

export function ErrorLine({ text }: { text: string | null | undefined }) {
  return text ? <Notice tone="err">{text}</Notice> : null
}

export const STAGE_TONE: Record<string, 'neutral' | 'ok' | 'warn' | 'err' | 'info'> = { empty: 'neutral', draft: 'warn', approved: 'ok', stale: 'err' }

export function download(url: string, name: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
}
