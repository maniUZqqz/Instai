// Shapes of the InstAI API (instai/*/api.py). Only the fields the UI uses are listed.

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface Job {
  id: number
  kind: string
  resource: string
  title: string
  status: JobStatus
  payload: Record<string, unknown>
  result: Record<string, any>
  progress: number
  progress_text: string
  priority: number
  attempts: number
  max_attempts: number
  cancel_requested: boolean
  error: string
  error_code: string
  waiting_reason: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_sec: number | null
  gpu_seconds: number
  estimated_sec: number | null
  page: number | null
  episode: number | null
}

export type EpisodeState =
  | 'draft' | 'planned' | 'scripting' | 'script_review' | 'storyboarding' | 'asset_generation' | 'animation' | 'assembly'
  | 'quality_review' | 'ready_for_approval' | 'approved' | 'scheduled' | 'published' | 'failed' | 'cancelled'

// The forward order of the state machine (instai/story/states.py ORDER).
export const STATE_ORDER: EpisodeState[] = [
  'draft', 'planned', 'scripting', 'script_review', 'storyboarding', 'asset_generation', 'animation', 'assembly',
  'quality_review', 'ready_for_approval', 'approved', 'scheduled', 'published',
]

export type FormatKey = 'anime_whatif' | 'recurring_character' | 'concept_explainer' | 'custom' | string

export interface FormatDef {
  key: FormatKey
  label_fa: string
  label_en: string
  description_fa: string
  needs: string[]
  default_techniques: string[]
  default_series: { episodes: number; episode_length_sec: number }
  policy: { original_default: boolean; fan_notice: boolean; sourced: boolean; synthetic_presenter_only: boolean }
  idea_hint_fa: string
}
export interface StyleDef {
  key: string
  label_fa: string
  prompt: string
}
export interface Formats {
  formats: FormatDef[]
  styles: StyleDef[]
  presets: Record<string, { label_fa: string; note_fa: string }>
  notices: { fan: string; explainer: string; presenter: string }
  profile_defaults: Record<ProfileKind, Record<string, any>>
  techniques: string[]
}

export type ProfileKind = 'identity' | 'strategy' | 'visual' | 'audio' | 'production' | 'publishing'
export const PROFILE_KINDS: ProfileKind[] = ['identity', 'strategy', 'visual', 'audio', 'production', 'publishing']

export interface Notice {
  key: string
  text: string
}

export interface PageBrief {
  id: number
  name: string
  handle: string
  format: FormatKey
  format_label: string
  languages: string[]
  idea: string
  automation_level: 'manual' | 'assisted' | 'automatic'
  status: 'active' | 'archived'
  created_at: string
  updated_at: string
  series_count: number
  episode_count: number
  episodes_approved: number
}

export interface Reference {
  id: number
  character: number
  kind: string
  label: string
  asset: number | null
  asset_url: string | null
  approved: boolean
  notes: string
}

export interface CharacterVoice {
  engine?: string
  voice_id?: string
  language?: string
  reference_asset?: string | number
  [k: string]: unknown
}

export interface Character {
  id: number
  page: number
  name: string
  role: string
  profile: string
  personality: string
  appearance: string
  abilities: string
  motivations: string
  voice: CharacterVoice
  is_original: boolean
  franchise: string
  approved: boolean
  references: Reference[]
}

export interface PageDetail extends PageBrief {
  profiles: Record<ProfileKind, Record<string, any>>
  characters: Character[]
  notices: Notice[]
}

export interface ProfileTemplate {
  id: number
  kind: ProfileKind
  name: string
  data: Record<string, any>
}

export interface Arc {
  id: number
  series: number
  index: number
  title: string
  summary: string
  goal: string
  cliffhanger: string
}

export interface EpisodeBrief {
  id: number
  series: number
  number: number
  title: string
  logline: string
  goal: string
  cliffhanger: string
  arc: number | null
  arc_index: number | null
  duration_sec: number
  state: EpisodeState
  state_label: string
  has_script: boolean
  updated_at: string
  error: string
  series_title?: string
}

export interface SeriesBrief {
  id: number
  page: number
  title: string
  premise: string
  branch_point: string
  alternative_timeline: string
  content_rules: string[]
  is_fan_content: boolean
  franchise: string
  target_episodes: number
  status: string
  created_at: string
  episode_count: number
  format: FormatKey
  notices: Notice[]
}
export interface SeriesDetail extends SeriesBrief {
  arcs: Arc[]
  episodes: EpisodeBrief[]
}

export interface ScriptBlock {
  id?: number
  speaker: string
  text: string
  emotion: string
}
export interface Script {
  title?: string
  hook?: string
  language?: string
  blocks: ScriptBlock[]
  cta?: string
}
export interface ScriptChecks {
  word_count: number
  est_duration_sec: number
  target_sec: number
  wps: number
  warnings: string[]
  ok: boolean
}

export interface ShotEstimate {
  gpu_seconds: number
  cpu_seconds: number
  notes: string[]
}
export interface Shot {
  id: number
  scene: number
  index: number
  description: string
  image_prompt: string
  negative_prompt: string
  technique: string
  camera: { move?: string; intensity?: number }
  duration_sec: number
  narration: string
  speaker: string
  sfx: string
  transition: string
  seed: number | null
  approved: boolean
  status: string
  last_error: string
  estimate: ShotEstimate
  keyframe: { id: number; url: string; approved: boolean; provenance: Record<string, any> } | null
  narration_asset: { id: number; url: string; duration_sec: number | null } | null
  clip: { id: number; url: string } | null
}
export interface Scene {
  id: number
  index: number
  title: string
  summary: string
  location: string
  approved: boolean
  characters: string[]
  shots: Shot[]
}

export interface ModeEstimate {
  gpu_seconds: number
  gpu_minutes: number
  cpu_seconds: number
  total_minutes: number
}
export interface EpisodeEstimate {
  source: 'planning_estimate' | 'measured'
  shots: number
  modes: Record<string, ModeEstimate>
  duration_sec: number
  video_shots: number
}

export interface VideoAsset {
  id: number
  role: 'preview' | 'final'
  url: string
  duration_sec: number | null
  width: number | null
  height: number | null
  fps: number | null
  codec: string
  loudness_lufs: number | null
  size_bytes: number
  created_at: string
}

export interface QcCheck {
  name: string
  level: 'ok' | 'warn' | 'fail' | 'info'
  value: unknown
  message: string
}

export interface Source {
  id: number
  title: string
  url: string
  publisher: string
  extract: string
  claim: string
  stance: string
  verified: boolean
  added_by: string
  episode?: number | null
  series?: number | null
}

export interface ResearchClaim {
  claim: string
  stance: 'established' | 'contested' | 'speculative'
  source_ids: number[]
  explanation: string
  unsupported: boolean
}
export interface Research {
  topic?: string
  queries?: string[]
  claims?: ResearchClaim[]
  analogies?: string[]
  visual_metaphors?: string[]
  caveats?: string[]
  unsupported_count?: number
  at?: string
}

export interface Episode extends EpisodeBrief {
  series_title: string
  page: number
  page_format: FormatKey
  language: string
  script: Script | Record<string, never>
  script_checks: Partial<ScriptChecks>
  scenes: Scene[]
  estimate: EpisodeEstimate
  qc: { checks?: QcCheck[]; ok?: boolean; asset_id?: number; mode?: string }
  research: Research
  notes: string
  failed_state: string
  allowed_next: { state: EpisodeState; label: string }[]
  videos: VideoAsset[]
  cover_url: string | null
  sources: Source[]
  jobs: Job[]
  stale: { keyframes_preview?: number; keyframes_final?: number; narration?: number; shots?: number }
}

export interface EpisodeEvent {
  id: number
  from: string
  to: string
  to_label: string
  reason: string
  actor: string
  at: string
}
export interface EpisodeVersion {
  id: number
  kind: 'script' | 'storyboard'
  note: string
  created_at: string
  data: any
}

export interface MemoryEntry {
  id: number
  subject: string
  text: string
  status: string
  episode: number | null
}
export type MemoryKind = 'fact' | 'character_state' | 'relationship' | 'timeline' | 'open_thread' | 'episode_summary' | 'future_goal'
export interface Memory {
  entries: Record<MemoryKind, MemoryEntry[]>
  digest: Record<string, unknown>
}

export interface Publication {
  id: number
  episode: number
  episode_title: string
  episode_number: number
  target: number | null
  caption: string
  hashtags: string[]
  scheduled_at: string | null
  status: 'draft' | 'exported' | 'scheduled' | 'published' | 'failed'
  ai_label: boolean
  package_url: string | null
  cover_url: string | null
  external_url: string
  created_at: string
  episode_state: EpisodeState
}

export interface GpuInfo {
  present: boolean
  name: string | null
  total_mb: number | null
  used_mb: number | null
  utilization: number | null
  busy_job: number | null
  busy_reason: string
}

export interface Dashboard {
  pages: PageBrief[]
  active_jobs: Job[]
  recent_episodes: (EpisodeBrief & { page: number; page_name: string; series_title: string })[]
  upcoming_publications: { id: number; episode: number; episode_title: string; scheduled_at: string; status: string }[]
  needs_action: { type: 'episode_failed' | 'job_failed' | 'ready_for_approval'; episode?: number; job?: number; title: string; error?: string }[]
  gpu: GpuInfo
  worker_alive: boolean
  demo_mode: boolean
  provider: string
}

export interface MonitorWorker {
  name: string
  pid: number
  alive: boolean
  last_seen: string | null
  current_jobs: unknown[]
  info: Record<string, any>
}
export interface Monitor {
  active: Job[]
  recent: Job[]
  workers: MonitorWorker[]
  gpu: { name: string; total_mb: number; used_mb: number; free_mb: number; driver: string; utilization: number; temperature: number; processes: { pid: number; name: string; used_mb: number }[] } | null
  gpu_holder: number | null
  gpu_busy_reason: string
  worker_alive: boolean
}

export interface JobLogLine {
  id: number
  at: string
  level: string
  message: string
}

export interface ProviderInfo {
  id: 'fake' | 'ollama' | 'openai'
  label: string
  resource: string
  licence: string
  note: string
  active: boolean
  ok: boolean
  detail: string
  models: string[]
  model: string
}
export interface SettingsPayload {
  values: Record<string, string>
  api_key: { set: boolean; hint: string }
  providers: ProviderInfo[]
  demo_mode: boolean
  enums: Record<string, string[]>
  paths: Record<string, string>
}

export interface ModelRow {
  id: string
  name: string
  role: string
  licence: string
  commercial: 'yes' | 'conditional' | 'no' | 'unknown'
  verified: string | null
  vram: string
  package: string | null
  notes: string
  excluded?: boolean
  decision?: boolean
  installed: boolean | null
}
export interface PackageInfo {
  title: string
  default: boolean
  licence: string
  licence_verified: boolean
  size: number
  items: number
  installed: number
  complete: boolean
  note: string
}
export interface WorkflowInfo {
  id: string
  title: string
  kind: string
  vram_gb: number | null
  licence: string
  licence_status: string
  expected_seconds: number | null
  estimate_source: string
  notes: string
  available: boolean | null
  missing: string[]
}
export interface ModelsPayload {
  models: ModelRow[]
  packages: Record<string, PackageInfo>
  workflows: WorkflowInfo[]
  checked_on: string
}

export interface HardwareItem {
  id: string
  label: string
  status: 'ok' | 'warn' | 'missing' | 'error'
  detail: string
  data: Record<string, any>
  hint: string
}
export interface Hardware {
  checked_at: string
  items: HardwareItem[]
  summary: Record<string, number>
  machine: { os: string; cpu: string; ram_gb: number; gpu: string | null; vram_gb: number | null; driver: string | null }
}

export interface BenchResult {
  step: string
  candidate: string
  status: 'ok' | 'skipped' | 'failed'
  seconds: number | null
  vram_peak_mb: number | null
  message: string
  details: Record<string, any>
}
export interface BenchRun {
  id: number
  status: string
  created_at: string
  finished_at: string | null
  machine: Record<string, any>
  options: Record<string, any>
  results: BenchResult[]
}
export interface BenchPayload {
  latest: BenchRun | null
  runs: { id: number; status: string; created_at: string }[]
}

// What the strategist proposes (instai/agents/schemas.py STRATEGY and SERIES_PLAN).
export interface Strategy {
  positioning: string
  audience_insight: string
  tone_guidelines: string
  content_pillars: { title: string; description: string }[]
  series_ideas: { title: string; premise: string; branch_point?: string; episodes?: number }[]
  characters?: { name: string; role: string; personality?: string; appearance?: string; is_original?: boolean }[]
  posting_plan: { per_week: number; best_times?: string[]; episode_length_sec?: number }
  hashtags: string[]
  risks?: string[]
}
export interface SeriesPlan {
  title: string
  premise: string
  branch_point?: string
  alternative_timeline?: string
  content_rules?: string[]
  arcs: { title: string; summary: string; goal?: string; cliffhanger?: string }[]
  episodes: { number: number; arc?: number; title: string; logline: string; goal?: string; cliffhanger?: string; duration_sec?: number }[]
}

export interface HistoryEvent {
  id: number
  episode: number
  episode_number: number
  series_title: string
  from: string
  to: string
  to_label: string
  reason: string
  actor: string
  at: string
}
