// Shapes of the studio API (instai/styles, instai/studio). Re-exported from types.ts.
import type { Job, SeriesBrief, Source } from './types'

// ---------------------------------------------------------------- style & theme library (instai/styles)
export interface Typography {
  title_weight: string
  title_case: string
  title_animation: string
  subtitle_color: string
  subtitle_outline: string
  subtitle_position: string
  subtitle_box_opacity: number
  subtitle_size: number
}
export interface StylePreset {
  key: string
  kind: 'style'
  builtin: boolean
  based_on: string
  origin: string
  name_fa: string
  name_en: string
  description_fa: string
  description_en: string
  realism: string
  family: string
  animation: string
  fps_feel: number
  image_positive: string
  image_negative: string
  video_positive: string
  video_negative: string
  palette: string[]
  lighting: string
  mood: string
  techniques: string[]
  sample_prompt: string
  theme_key: string
  tags: string[]
  thumbnail_asset: number | null
  thumbnail_url?: string | null
  notes: string
}
export interface ThemePreset {
  key: string
  kind: 'theme'
  builtin: boolean
  based_on: string
  origin: string
  name_fa: string
  name_en: string
  description_fa: string
  description_en: string
  palette: string[]
  lighting: string
  mood: string
  prompt_fragment: string
  negative_fragment: string
  tags: string[]
  typography: Typography
  notes: string
}
export interface VocabItem {
  key: string
  fa: string
  en: string
  order?: number
}
export interface Library {
  styles: StylePreset[]
  themes: ThemePreset[]
  realism: VocabItem[]
  families: VocabItem[]
  animations: VocabItem[]
  techniques: string[]
  palette_roles: string[]
  typography: { title_weights: string[]; title_cases: string[]; title_animations: string[]; subtitle_positions: string[] }
}

// ---------------------------------------------------------------- development templates and the development room (instai/studio)
export type StepKind = 'source' | 'research' | 'brainstorm' | 'profile' | 'map' | 'timeline' | 'factcheck' | 'bible' | 'composition' | 'gate'
export type StepStatus = 'todo' | 'active' | 'review' | 'done' | 'skipped'
export interface TemplateStep {
  key: string
  kind: StepKind
  title_fa: string
  title_en: string
  help_fa: string
  help_en: string
  params: { lens?: string; board?: string; count?: number; mode?: string; gate?: boolean }
}
export interface DevTemplate {
  key: string
  base_format: string
  builtin: boolean
  needs_source: boolean
  name_fa: string
  name_en: string
  description_fa: string
  description_en: string
  default_series: { episodes: number; episode_length_sec: number }
  steps: TemplateStep[]
}
export interface TemplatesPayload {
  templates: DevTemplate[]
  step_kinds: StepKind[]
  lenses: { key: string; fa: string; en: string }[]
  formats: string[]
}
export interface DevStepState extends TemplateStep {
  status: StepStatus
  auto_approved: boolean
  approved_at: string | null
  needs_human: boolean
  has_content: boolean
  data: any
  counts?: { total: number; approved: number; rejected: number }
}
export interface Idea {
  id: number
  series: number
  board: string
  title: string
  logline: string
  why: string
  details: Record<string, string>
  tags: string[]
  author: 'ai' | 'human' | 'merged' | 'refined'
  status: 'proposed' | 'liked' | 'approved' | 'rejected' | 'merged'
  rating: number
  parent: number | null
  notes: string
  language: string
  position: number
}
export interface ResearchDocT {
  id: number
  kind: 'canon' | 'topic'
  title: string
  content: Record<string, any>
  status: string
  language: string
  meta: Record<string, any>
  updated_at: string
}
export interface BibleCharacter {
  name: string
  role: string
  appearance: string
  personality: string
  motivations: string
  abilities: string
  is_original: boolean
}
export interface BibleData {
  title: string
  logline: string
  premise: string
  tone: string
  branch_point: string
  alternative_timeline: string
  visual_notes: string
  world_rules: string[]
  themes: string[]
  content_rules: string[]
  characters: BibleCharacter[]
  arcs: { title: string; summary: string; goal: string; cliffhanger: string }[]
  episode_count: number
  episode_length_sec: number
}
export interface Bible {
  data: BibleData
  status: 'draft' | 'approved'
  version: number
  approved_at: string | null
  exists: boolean
}
export interface SourceCandidate {
  provider: string
  id: string
  title: string
  title_romaji?: string
  title_native?: string
  year: number | null
  format: string
  episodes: number | null
  status: string
  genres: string[]
  description: string
  cover_url: string
  url: string
  score: number
  match?: number
  lang?: string
}
export interface SourceSearchResult {
  candidates: SourceCandidate[]
  errors: { provider: string; message: string }[]
  tried: string[]
}
export interface Development {
  series: SeriesBrief
  template: Pick<DevTemplate, 'key' | 'name_fa' | 'name_en' | 'base_format' | 'needs_source' | 'builtin'>
  steps: DevStepState[]
  ideas: Record<string, Idea[]>
  research: Record<string, ResearchDocT>
  sources: Source[]
  bible: Bible
  source: Partial<SourceCandidate> & { manual?: boolean; notes?: string; fandom_wiki?: string }
  look: { style_key: string; realism: string; theme_key: string; style_name_fa: string; style_name_en: string; inherited: boolean }
  languages: string[]
  dev_status: 'none' | 'developing' | 'approved'
  dev_approved_at: string | null
  automation_level: 'manual' | 'assisted' | 'automatic'
  running_jobs: Job[]
  has_plan: boolean
}

// ---------------------------------------------------------------- pre-production (instai/studio/preprod)
export type StageKey = 'script' | 'storyboard' | 'animatic' | 'design' | 'casting' | 'gate'
export interface StageRow {
  key: StageKey
  status: 'todo' | 'ready' | 'stale' | 'approved' | 'auto'
  required: boolean
  approved_at: string | null
  blocking?: string[]
}
export interface DesignSheet {
  id: number
  episode: number | null
  character: number | null
  kind: 'character' | 'expression' | 'background' | 'prop' | 'colour_script'
  subject: string
  prompt: string
  negative: string
  notes: string
  palette: string[]
  approved: boolean
  status: string
  last_error: string
  author: 'ai' | 'human'
  image_url: string | null
}
export interface VoiceOption {
  id: string
  engine: string
  voice: string
  label: string
  voice_label?: string
  language: string
  installed: boolean
  commercial?: string
  commercial_ok?: boolean
  tags: string[]
}
export interface CastingRow {
  character: number
  name: string
  role: string
  personality: string
  engine: string
  voice_id: string
  has_voice: boolean
  language: string
  by_language: Record<string, { engine: string; voice_id: string }>
}
export interface Retake {
  id: number
  episode: number
  shot: number | null
  scope: string
  reason: string
  status: 'open' | 'done' | 'cancelled'
  created_at: string
  shot_label: string
}
export interface StudioPayload {
  report: { stages: StageRow[]; studio_mode: boolean; gate_approved: boolean; blocking: string[] }
  animatic: {
    status: 'missing' | 'fresh' | 'stale'
    asset: { id: number; url: string; duration_sec: number | null; width: number | null; height: number | null; scratch_audio: string; stills: Record<string, number> } | null
    built_with?: string[]
  }
  design_sheets: DesignSheet[]
  casting: CastingRow[]
  voices: VoiceOption[]
  retakes: Retake[]
  translations: Record<string, { at: string; provider: string; model: string; shots: number }>
  languages: string[]
}

// ---------------------------------------------------------------- text model choice (production.llm)
export interface LlmSpec {
  provider: string
  model: string
}
export interface LlmConfig {
  default: LlmSpec
  fallback: LlmSpec
  groups: Record<string, LlmSpec>
}
