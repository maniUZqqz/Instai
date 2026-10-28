import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fa as faBase } from './fa'
import { en as enBase } from './en'

export type Lang = 'fa' | 'en'
// Keys are checked by tests/test_i18n.py (every t('...') used in the sources exists in both languages).
export type Key = string
export type Params = Record<string, string | number>

// Each workstream drops its own dictionary into src/i18n/packs/*.ts (exports `fa` and `en`); they are merged here without editing this file.
type Pack = { fa?: Record<string, string>; en?: Record<string, string> }
const packs = Object.values(import.meta.glob('./packs/*.ts', { eager: true })) as Pack[]
const fa: Record<string, string> = Object.assign({}, faBase, ...packs.map((p) => p.fa ?? {}))
const en: Record<string, string> = Object.assign({}, enBase, ...packs.map((p) => p.en ?? {}))

const LS_LANG = 'instai.lang'

function readLang(): Lang {
  try {
    return localStorage.getItem(LS_LANG) === 'en' ? 'en' : 'fa'
  } catch {
    return 'fa'
  }
}

// Module-level language so code outside React (the API client) can also produce messages in the right language.
let current: Lang = readLang()

export function currentLang(): Lang {
  return current
}

function locale(lang: Lang): string {
  return lang === 'fa' ? 'fa-IR' : 'en-US'
}

/** Look a key up in the active dictionary; English falls back to Persian, then to the key itself. */
export function translate(key: string, params?: Params): string {
  const own = current === 'en' ? en[key] : undefined
  let s = own ?? fa[key] ?? key
  if (params) {
    const nf = new Intl.NumberFormat(locale(current))
    s = s.replace(/\{(\w+)\}/g, (_, k: string) => {
      const v = params[k]
      return v === undefined ? '' : typeof v === 'number' ? nf.format(v) : v
    })
  }
  return s
}

function toDate(v: string | number | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === '') return null
  const d = v instanceof Date ? v : new Date(v)
  return Number.isNaN(d.getTime()) ? null : d
}

export function makeFormatters(lang: Lang) {
  const loc = locale(lang)
  const nf = new Intl.NumberFormat(loc)
  const nf1 = new Intl.NumberFormat(loc, { maximumFractionDigits: 1 })
  const cal = lang === 'fa' ? `${loc}-u-ca-persian` : loc
  const dateF = new Intl.DateTimeFormat(cal, { year: 'numeric', month: 'long', day: 'numeric' })
  const dateTimeF = new Intl.DateTimeFormat(cal, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  const timeF = new Intl.DateTimeFormat(loc, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const rel = new Intl.RelativeTimeFormat(loc, { numeric: 'auto' })
  const tr = (key: string, p?: Params) => {
    const own = lang === 'en' ? en[key] : undefined
    let s = own ?? fa[key] ?? key
    if (p) s = s.replace(/\{(\w+)\}/g, (_, k: string) => (p[k] === undefined ? '' : String(p[k])))
    return s
  }
  return {
    num: (n: number | null | undefined, digits = 0): string => {
      if (n === null || n === undefined || Number.isNaN(n)) return '—'
      return digits === 0 ? nf.format(n) : digits === 1 ? nf1.format(n) : new Intl.NumberFormat(loc, { maximumFractionDigits: digits }).format(n)
    },
    percent: (fraction: number | null | undefined): string => (fraction === null || fraction === undefined ? '—' : nf.format(Math.round(fraction * 100)) + (lang === 'fa' ? '٪' : '%')),
    date: (v: string | number | Date | null | undefined): string => {
      const d = toDate(v)
      return d ? dateF.format(d) : '—'
    },
    dateTime: (v: string | number | Date | null | undefined): string => {
      const d = toDate(v)
      return d ? dateTimeF.format(d) : '—'
    },
    time: (v: string | number | Date | null | undefined): string => {
      const d = toDate(v)
      return d ? timeF.format(d) : '—'
    },
    ago: (v: string | number | Date | null | undefined): string => {
      const d = toDate(v)
      if (!d) return '—'
      const sec = Math.round((d.getTime() - Date.now()) / 1000)
      const abs = Math.abs(sec)
      if (abs < 45) return rel.format(0, 'second')
      if (abs < 3600) return rel.format(Math.round(sec / 60), 'minute')
      if (abs < 86400) return rel.format(Math.round(sec / 3600), 'hour')
      return rel.format(Math.round(sec / 86400), 'day')
    },
    /** "۲ دقیقه و ۳۰ ثانیه" */
    duration: (secs: number | null | undefined): string => {
      if (secs === null || secs === undefined || Number.isNaN(secs)) return '—'
      let s = Math.max(0, Math.round(secs))
      if (s < 60) return tr('unit.sec_n', { n: nf.format(s) })
      if (s < 3600) {
        const m = Math.floor(s / 60)
        s -= m * 60
        return s ? tr('unit.min_sec', { m: nf.format(m), s: nf.format(s) }) : tr('unit.min_n', { n: nf.format(m) })
      }
      const h = Math.floor(s / 3600)
      const m = Math.round((s - h * 3600) / 60)
      return m ? tr('unit.hour_min', { h: nf.format(h), m: nf.format(m) }) : tr('unit.hour_n', { n: nf.format(h) })
    },
    bytes: (n: number | null | undefined): string => {
      if (n === null || n === undefined) return '—'
      if (n >= 1e9) return nf1.format(n / 1e9) + ' ' + tr('unit.gb')
      if (n >= 1e6) return nf1.format(n / 1e6) + ' ' + tr('unit.mb')
      return nf1.format(n / 1e3) + ' ' + tr('unit.kb')
    },
    mb: (n: number | null | undefined): string => (n === null || n === undefined ? '—' : n >= 1024 ? nf1.format(n / 1024) + ' ' + tr('unit.gb') : nf.format(n) + ' ' + tr('unit.mb')),
  }
}

export type Formatters = ReturnType<typeof makeFormatters>

type I18n = {
  lang: Lang
  dir: 'rtl' | 'ltr'
  setLang: (l: Lang) => void
  t: (key: Key, params?: Params) => string
  /** For keys built at run time (e.g. `state.${s}`); returns `fallback` or the key when missing. */
  tr: (key: string, fallback?: string, params?: Params) => string
  f: Formatters
}

const Ctx = createContext<I18n | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current)
  const setLang = useCallback((l: Lang) => {
    current = l
    try {
      localStorage.setItem(LS_LANG, l)
    } catch {
      /* storage blocked: the choice just lasts for this visit */
    }
    setLangState(l)
    // also remembered by the server, so a new browser (or cleared storage) opens in the same language
    fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ui_language: l }) }).catch(() => undefined)
  }, [])
  useEffect(() => {
    let stored: string | null = null
    try {
      stored = localStorage.getItem(LS_LANG)
    } catch {
      /* ignore */
    }
    if (stored) return
    fetch('/api/settings')
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        const v = s?.values?.ui_language
        if (v === 'en' && current !== 'en') {
          current = 'en'
          setLangState('en')
        }
      })
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr'
  }, [lang])
  const value = useMemo<I18n>(
    () => ({
      lang,
      dir: lang === 'fa' ? 'rtl' : 'ltr',
      setLang,
      t: (key, params) => translate(key, params),
      tr: (key, fallback, params) => {
        const has = (current === 'en' && key in en) || key in fa
        return has ? translate(key, params) : fallback ?? key
      },
      f: makeFormatters(lang),
    }),
    [lang, setLang],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const v = useContext(Ctx)
  if (!v) throw new Error('I18nProvider missing')
  return v
}
