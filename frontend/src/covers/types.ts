// Shapes of /api/covers/* (see instai/covers/api.py). Rows that carry text come as `<key>_fa` / `<key>_en` pairs and are read with pick(row, key).
import type { Job } from '../api/types'

export type CFormat = {
  key: string
  title_fa: string
  title_en: string
  platform_fa: string
  platform_en: string
  width: number
  height: number
  aspect: string
  orient: string
  note_fa: string
  note_en: string
  max_kb: number
  margin: number[]
  avoid: { rect: number[]; note_fa: string; note_en: string }[]
}

export type CStyle = {
  key: string
  title_fa: string
  title_en: string
  short_fa: string
  short_en: string
  pattern_fa: string
  pattern_en: string
  mood: string
  font: string
  family: string
  subject: 'none' | 'optional' | 'recommended'
  fields: { key: string; label_fa: string; label_en: string }[]
  formats: string[]
  needs_second: boolean
  tips: { fa: string; en: string }[]
  origin: 'ported' | 'instai'
}

export type CArchetype = {
  style: string
  why_fa: string
  why_en: string
  dos_fa: string[]
  dos_en: string[]
  donts_fa: string[]
  donts_en: string[]
  text_rule_fa: string
  text_rule_en: string
}

export type CMeta = {
  formats: CFormat[]
  default_format: string
  styles: CStyle[]
  moods: { key: string; fa: string; en: string }[]
  fonts: { key: string; label_fa: string; label_en: string }[]
  textures: string[]
  bg_kinds: string[]
  logo_positions: string[]
  limits: Record<string, number>
  max_variants: number
  archetypes: CArchetype[]
  ai: { engine: string; workflow: string; demo: boolean; available: boolean }
  shaping: { raqm: boolean }
}

export type CSubject = {
  asset: number | null
  character: number | null
  expression: string
  mode?: string
  side?: string
  scale?: number
  outline?: boolean
}

export type CSpec = {
  format: string
  style: string
  lang: 'fa' | 'en'
  content: Record<string, string>
  colors: { mood: string; primary: string; secondary: string; accent: string; use_brand: boolean; variation: number }
  font: string
  background: { kind: string; asset: number | null; texture: string; darken: number; blur: number; job: string }
  subject: CSubject & { mode: string; side: string; scale: number; outline: boolean }
  subject2: CSubject
  extra_assets: number[]
  logo: { show: boolean; position: string; asset: number | null }
  accents: { arrow: boolean }
  seed: number
  guides: boolean
}

export type CSubjectRow = {
  id: number
  name: string
  role: string
  source: 'stick' | 'image' | 'keyframe' | 'sheet' | 'none'
  asset_id: number | null
  url: string | null
  locked: boolean
}

export type CContext = {
  target: { page: number; page_name: string; series: number | null; episode: number | null; kind: string }
  context: Record<string, unknown> & { lang: 'fa' | 'en'; channel: string }
  spec: CSpec
  subjects: CSubjectRow[]
  look: { style_key: string; theme_key: string; own: boolean; palette: string[]; font: string }
  latest: CCover[]
}

export type CWarning = {
  code: string
  fa: string
  en: string
}

export type CVariant = {
  index: number
  letter: string
  id: number
  asset: number
  url?: string
  width?: number
  height?: number
  size_bytes?: number
  variation: number
  mood?: string
  note_fa?: string
  note_en?: string
}

export type CCover = {
  id: number
  kind: string
  page: number
  series: number | null
  series_title: string
  episode: number | null
  episode_number: number | null
  episode_title: string
  parent: number | null
  format: string
  style: string
  status: 'draft' | 'rendering' | 'waiting_bg' | 'ready' | 'failed'
  bg_state: 'procedural' | 'ai' | 'waiting' | 'demo' | 'off'
  chosen: number
  asset: { id: number; url: string; width: number | null; height: number | null } | null
  bg: { id: number; url: string } | null
  variants: CVariant[]
  warnings: CWarning[]
  error: string
  note: string
  created_at: string
  updated_at: string
  in_use: boolean
  spec?: CSpec
}

export type CIdea = {
  id: string
  title: string
  subtitle: string
  kicker: string
  style: string
  source: 'ai' | 'rules'
  formula_label_fa: string
  formula_label_en: string
  concept_fa: string
  concept_en: string
  style_title_fa: string
  style_title_en: string
  mood: string
  spec_patch: { format: string; style: string; content: Record<string, string>; colors: { mood: string } }
}

export type CIdeas = {
  via: 'ai' | 'rules' | 'mixed'
  message_fa: string
  message_en: string
  ideas: CIdea[]
  ai: { tried: boolean; ok: boolean; label: string; reason_fa: string; reason_en: string }
}

export type CPreview = {
  image: string
  width: number
  height: number
  full: [number, number]
  warnings: CWarning[]
  guides: { safe: number[]; avoid: { rect: number[]; note_fa: string; note_en: string }[] }
  background: { kind: string; has_picture: boolean }
  info: { subjects: { source: string }[] }
}

export type CMakeResponse = {
  job: Job
  cover: CCover
}

export type CoverTarget = {
  page: number
  episode?: number | null
  series?: number | null
  kind?: 'episode' | 'series' | 'season' | 'banner'
}
