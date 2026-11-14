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

/** Persian names of the internal keys that the server sends as plain English words (stick-figure options, colour-key roles, colour names, expressions, ending types).
 *  A key that is not listed is shown as it is, so a new option never disappears - but every key the server can send today has a name here (a test in tests/test_ui_words.py checks). */
const WORDS_FA: Record<string, string> = {
  none: 'هیچ', round: 'گرد', tall: 'بلند', wide: 'پهن', dots: 'نقطه‌ای', sleepy: 'خواب‌آلود',
  cap: 'کلاه کپ', beanie: 'کلاه بافتنی', headband: 'سربند', tophat: 'کلاه شاپو', hood: 'کلاه کاپشن',
  tuft: 'تک‌تار', spikes: 'سیخ‌سیخی', bob: 'کوتاه', ponytail: 'دم‌اسبی',
  scarf: 'شال‌گردن', tie: 'کراوات', bowtie: 'پاپیون',
  glasses: 'عینک', backpack: 'کوله‌پشتی', mask: 'ماسک',
  torch: 'مشعل', phone: 'گوشی', key: 'کلید', bat: 'چوب بیسبال', sign: 'تابلو', map: 'نقشه',
  neutral: 'خنثی', happy: 'شاد', laugh: 'خنده', sad: 'غمگین', angry: 'عصبانی', scared: 'ترسیده', surprised: 'متعجب', smirk: 'پوزخند',
  limbs: 'دست و پا', head: 'سر', outline: 'خط دور', hat: 'کلاه', hair: 'مو', neck: 'شال یا کراوات', extra: 'وسیلهٔ اضافه', prop: 'وسیلهٔ دست',
  ink: 'مشکی', red: 'قرمز', blue: 'آبی', green: 'سبز', amber: 'کهربایی', violet: 'بنفش', pink: 'صورتی', teal: 'فیروزه‌ای', orange: 'نارنجی', grey: 'خاکستری', white: 'سفید', paper: 'کاغذی', brown: 'قهوه‌ای',
  good: 'خوب', bad: 'بد', secret: 'مخفی',
  ambience: 'فضا', foley: 'فولی', sfx: 'افکت', music: 'موسیقی', silence: 'سکوت',
  warm_dusk: 'غروب گرم', cold_night: 'شب سرد', high_contrast: 'کنتراست بالا', faded: 'رنگ‌رفته', vivid: 'زنده و پررنگ', desaturated: 'کم‌اشباع', tension: 'تنش',
}

/** `word(lang, 'beanie')` -> «کلاه بافتنی» in Persian, «beanie» in English; `colour 2` -> «رنگ ۲». Unknown keys come back unchanged. */
export function word(lang: string, key: string, num?: (v: number) => string): string {
  if (lang !== 'fa') return key
  const m = /^colour (\d+)$/.exec(key)
  if (m) return `رنگ ${num ? num(Number(m[1])) : m[1]}`
  return WORDS_FA[key] ?? key
}
