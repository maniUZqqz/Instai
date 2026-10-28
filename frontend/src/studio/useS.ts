import { useCallback } from 'react'
import { useI18n } from '../i18n'
import { studioEn, studioFa, type StudioKey } from './i18n'

export type SParams = Record<string, string | number>

/**
 * Translation hook of the Studio screens. The only coupling to the app's i18n system is `useI18n()` (language, direction and the
 * number/date formatters); the texts live in ./i18n.ts so a change of the main dictionary mechanism cannot break them.
 */
export function useS() {
  const { lang, dir, f } = useI18n()
  const s = useCallback(
    (key: StudioKey, params?: SParams): string => {
      let text: string = (lang === 'en' ? studioEn[key] : studioFa[key]) ?? studioFa[key] ?? key
      if (params) {
        text = text.replace(/\{(\w+)\}/g, (_, k: string) => {
          const v = params[k]
          return v === undefined ? '' : typeof v === 'number' ? f.num(v) : String(v)
        })
      }
      return text
    },
    [lang, f],
  )
  return { s, lang, dir, f }
}
