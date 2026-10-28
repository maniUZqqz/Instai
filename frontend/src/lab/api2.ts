// Shapes of the Production lab API, round 2: comparison, retake, mix, automation, publishing, notifications, consistency.
// Mirrors instai/production/api_hero.py, api_post.py, api_auto.py and instai/publishing/api.py.

export interface AssetLite {
  id: number
  kind: string
  role: string
  url: string
  mime: string
  size_bytes: number
  duration_sec: number | null
  width: number | null
  height: number | null
  fps: number | null
  provenance: Record<string, any>
}

// ---------------------------------------------------------------- comparison
export interface AnimeCandidate {
  id: string
  label: string
  workflow: string
  pack: string
  licence: string
  commercial: string
  note: string
  needs: string[]
  available: boolean
  missing: string[]
  expected_seconds: number
  estimate: boolean
}

export interface CompareClip {
  id: number
  still_index: number
  seed: number
  candidate: string
  status: 'queued' | 'done' | 'failed' | 'skipped'
  seconds: number | null
  device: string
  error: string
  url: string | null
}

export interface Comparison {
  id: number
  page: number | null
  name: string
  prompt: string
  seeds: number[]
  candidates: string[]
  status: string
  winner: string
  counts: Record<string, number>
  created_at: string
  stills: AssetLite[]
  clips?: CompareClip[]
}

export interface ProductionConfig {
  page: number
  anime_model: string
  default_technique: string
  gpu_minutes_per_week: number
  api_usd_per_week: number
  render_windows: RenderWindow[]
  utc_offset_minutes: number
  music_enabled: boolean
  auto_publish_enabled: boolean
  auto_publish_confirmed_at: string | null
}

export interface EpisodeBrief {
  id: number
  series: number
  series_title: string
  number: number
  title: string
  state: string
  state_label: string
}

// ---------------------------------------------------------------- retake
export interface RetakeVerify {
  duration: number
  expected_duration: number
  duration_error: number
  frames: number
  expected_frames: number
  fps: number
  size: string
  has_audio: boolean
  ok: boolean
}

export interface VideoRetake {
  id: number
  episode: number
  source_asset: number
  start_sec: number
  end_sec: number
  prompt: string
  audio_mode: 'keep' | 'mute' | 'replace' | 'cut'
  status: 'queued' | 'running' | 'done' | 'failed'
  result: AssetLite | null
  seam: {
    verify?: RetakeVerify
    seam?: { start?: number; end?: number }
    colour?: { before: number; after: number }
    device?: string
    workflow?: string
    segments?: number
    gpu_seconds?: number
    mode?: string
    qc_error?: string
    audio_asset?: number
  }
  error: string
  created_at: string
}

export interface EpisodeVideo {
  id: number
  role: 'preview' | 'final'
  url: string
  duration_sec: number | null
  width: number | null
  height: number | null
}

// ---------------------------------------------------------------- mix
export interface MixTrackRow {
  id: number
  episode: number
  shot: number | null
  kind: 'music' | 'sfx' | 'ambience'
  label: string
  prompt: string
  start_sec: number
  end_sec: number | null
  gain_db: number
  duck: boolean
  fade_in: number
  fade_out: number
  status: 'planned' | 'generating' | 'ready' | 'failed'
  error: string
  asset: AssetLite | null
}

// ---------------------------------------------------------------- automation
export interface RenderWindow {
  days: string[]
  start: string
  end: string
}

export interface AutomationInfo {
  page: number
  level: 'manual' | 'assisted' | 'automatic'
  levels: string[]
  usage: { week_start: string; gpu_minutes: number; api_usd: number; gpu_budget: number; api_budget: number }
  gpu_minutes_per_week: number
  api_usd_per_week: number
  render_windows: RenderWindow[]
  utc_offset_minutes: number
  window_open_now: boolean
  next_window: string
  publishing: { per_week: number; days: string[]; time: string; next_slots: string[] }
  auto_publish: { enabled: boolean; confirmed_at: string | null; confirm_text: string; can_post_now: boolean; why_not: string; feature_flag: boolean }
  explain: Record<string, string>
}

export interface ScheduleInfo {
  slots: string[]
  scheduled: { id: number; episode: number; title: string; scheduled_at: string | null; status: string }[]
}

export interface Requirement {
  key: string
  ok: boolean
  text: string
}

export interface PublishTargetRow {
  id: number
  page: number
  platform: string
  handle: string
  mode: 'manual' | 'api'
  enabled: boolean
  config: Record<string, any>
  adapter: string
  adapter_label: string
  requirements: Requirement[]
  ready: boolean
}

export interface PublicationRow {
  id: number
  episode: number
  episode_title: string
  episode_number: number
  target: number | null
  caption: string
  scheduled_at: string | null
  status: string
  package_url: string | null
  episode_state: string
}

export interface NotificationRow {
  id: number
  kind: string
  level: 'info' | 'ok' | 'warn' | 'error'
  title: string
  body: string
  link: string
  page: number | null
  episode: number | null
  read: boolean
  created_at: string
}

export interface NotificationsPayload {
  unread: number
  items: NotificationRow[]
}

// ---------------------------------------------------------------- consistency
export interface LoraRow {
  id: number
  character: number
  status: 'queued' | 'training' | 'trained' | 'failed'
  lora_file: string
  params: Record<string, any>
  before: { similarity?: number | null; per_prompt?: number[] }
  after: { similarity?: number | null; per_prompt?: number[]; delta?: number | null; helped?: boolean }
  seconds: number | null
  error: string
  approved: boolean
  created_at: string
}

export interface ShotRenderRow {
  id: number
  shot: number
  technique: string
  status: string
  device: string
  seconds: number | null
  qc: { drift?: number | null; sheet?: number | null; ok?: boolean; notes?: string[]; thresholds?: { drift: number; sheet: number } }
  params: Record<string, any>
  error: string
  asset: AssetLite | null
}
