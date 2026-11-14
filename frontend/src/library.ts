import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import type { Library, StylePreset, TemplatesPayload, ThemePreset } from './api/types'
import { useI18n, type Lang } from './i18n'

// The style / theme library and the development templates, fetched once per visit and refetched after the owner changes them.
let libCache: Promise<Library> | null = null
let tplCache: Promise<TemplatesPayload> | null = null
const listeners = new Set<() => void>()

export function invalidateLibrary() {
  libCache = null
  tplCache = null
  listeners.forEach((f) => f())
}

function useCached<T>(get: () => Promise<T>, reset: () => void) {
  const [data, setData] = useState<T | undefined>()
  const [error, setError] = useState<unknown>(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const on = () => setTick((n) => n + 1)
    listeners.add(on)
    return () => {
      listeners.delete(on)
    }
  }, [])
  useEffect(() => {
    let alive = true
    get()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => {
        reset()
        if (alive) setError(e)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick])
  const reload = useCallback(() => invalidateLibrary(), [])
  return { data, error, reload }
}

export function useLibrary() {
  const r = useCached<Library>(
    () => (libCache ??= api.get<Library>('/library')),
    () => (libCache = null),
  )
  return {
    ...r,
    style: (key: string): StylePreset | undefined => r.data?.styles.find((s) => s.key === key),
    theme: (key: string): ThemePreset | undefined => r.data?.themes.find((t) => t.key === key),
  }
}

export function useTemplates() {
  const r = useCached<TemplatesPayload>(
    () => (tplCache ??= api.get<TemplatesPayload>('/templates')),
    () => (tplCache = null),
  )
  return { ...r, byKey: (key: string) => r.data?.templates.find((t) => t.key === key) }
}

/** Name / description of a library item or template in the interface language (falls back to the other language). */
export function nm(x: { name_fa: string; name_en: string } | undefined, lang: Lang): string {
  if (!x) return ''
  return (lang === 'fa' ? x.name_fa || x.name_en : x.name_en || x.name_fa) || ''
}
export function desc(x: { description_fa: string; description_en: string } | undefined, lang: Lang): string {
  if (!x) return ''
  return (lang === 'fa' ? x.description_fa || x.description_en : x.description_en || x.description_fa) || ''
}
export function vocab(list: { key: string; fa: string; en: string }[] | undefined, key: string, lang: Lang): string {
  const v = list?.find((x) => x.key === key)
  return v ? (lang === 'fa' ? v.fa : v.en) : key
}

/** The picture of a style card: the GPU-made sample when there is one, else the built-in swatch drawing. */
export function styleImage(s: Pick<StylePreset, 'thumbnail_url' | 'preview_url'>): string | null {
  return s.thumbnail_url || s.preview_url || null
}

// Words that are no part of any name ("PS2 style"); letters and digits of the Arabic and Persian alphabets are unified, as on the server.
const FILLER = new Set(['style', 'styles', 'look', 'looks', 'like', 'سبک', 'استایل'])
export function fold(text: string): string {
  return (text || '')
    .toLowerCase()
    .replace(/\u064a/g, '\u06cc')
    .replace(/\u0643/g, '\u06a9')
    .replace(/\u200c/g, ' ')
    .replace(/-/g, ' ')
    .replace(/[\u0660-\u0669\u06f0-\u06f9]/g, (c) => String(c.charCodeAt(0) - (c.charCodeAt(0) >= 0x06f0 ? 0x06f0 : 0x0660)))
}
/** Does a style answer this search? Every word must be in its names, descriptions, tags or search-only names. */
export function styleMatches(s: StylePreset, q: string): boolean {
  let words = fold(q).split(/\s+/).filter(Boolean)
  words = words.filter((w) => !FILLER.has(w)).length ? words.filter((w) => !FILLER.has(w)) : words
  if (!words.length) return true
  const hay = fold([s.name_fa, s.name_en, s.description_fa, s.description_en, ...(s.tags ?? []), ...(s.search_terms ?? []), s.key.replace(/_/g, ' '), s.known_as ?? ''].join(' '))
  return words.every((w) => hay.includes(w))
}

/** A CSS gradient made from a palette (swatch of a style / theme card). */
export function paletteGradient(p: string[] | undefined): string {
  const c = (p ?? []).slice(0, 5)
  if (c.length === 0) return 'linear-gradient(135deg, #d0d7ea, #8d9bd0)'
  if (c.length === 1) return c[0]
  return `linear-gradient(135deg, ${c.map((x, i) => `${x} ${Math.round((i / (c.length - 1)) * 100)}%`).join(', ')})`
}

export function useLang() {
  return useI18n().lang
}

/** The subtitle look of a theme in the shape the visual profile (and the renderer) uses. */
export function schemaSubtitle(th: ThemePreset) {
  const ty = th.typography
  return { font: 'Vazirmatn', size: ty.subtitle_size, color: ty.subtitle_color, outline: ty.subtitle_outline, position: ty.subtitle_position }
}
