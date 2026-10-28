import { useCallback } from 'react'
import { useI18n } from '../i18n'
import { labEn, labFa, type LabKey } from './i18n'

export type SParams = Record<string, string | number>

/**
 * Translation hook of the Production lab screens. The only coupling to the app's i18n system is `useI18n()` (language, direction and the
 * number/date formatters); the texts live in ./i18n.ts so a change of the main dictionary mechanism cannot break them.
 */
export function useL() {
  const { lang, dir, f } = useI18n()
  const s = useCallback(
    (key: LabKey, params?: SParams): string => {
      let text: string = (lang === 'en' ? labEn[key] : labFa[key]) ?? labFa[key] ?? key
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
