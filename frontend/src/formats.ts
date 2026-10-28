import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { FormatDef, Formats } from './api/types'
import { useI18n } from './i18n'

// The format registry (formats, styles, presets, notices, profile defaults, techniques) is fetched once per visit.
let cache: Promise<Formats> | null = null

export function useFormats() {
  const { lang } = useI18n()
  const [data, setData] = useState<Formats | undefined>()
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    let alive = true
    cache ??= api.get<Formats>('/formats')
    cache
      .then((d) => alive && setData(d))
      .catch((e) => {
        cache = null
        if (alive) setError(e)
      })
    return () => {
      alive = false
    }
  }, [])
  const byKey = (key: string): FormatDef | undefined => data?.formats.find((f) => f.key === key)
  return {
    data,
    error,
    byKey,
    formatLabel: (key: string, fallback?: string) => {
      const f = byKey(key)
      return f ? (lang === 'fa' ? f.label_fa : f.label_en) : fallback ?? key
    },
    styleLabel: (key: string) => data?.styles.find((s) => s.key === key)?.label_fa ?? key,
  }
}

// Techniques with a render path today (mirrors instai/story/costs.py IMPLEMENTED). Others fall back to a still image with camera motion.
export const IMPLEMENTED_TECHNIQUES = ['still_kenburns', 'parallax_25d', 'wan_i2v']
export const CAMERA_MOVES = ['static', 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down']
export const WEEKDAYS = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']
export const EXPLAINER = 'concept_explainer'
export const ANIME = 'anime_whatif'
