// Shapes of the Production lab API (workers, voices, rigs). Mirrors instai/jobs/api_workers.py, instai/production/api_voices.py, api_rigs.py.

export interface SpeedRow {
  avg: number
  n: number
}

export interface Device {
  name: string
  id?: number
  local: boolean
  enabled: boolean
  online: boolean
  busy: boolean
  caps: string[]
  vram_total_mb: number
  vram_free_mb: number
  speed: Record<string, SpeedRow>
  gpu_name?: string
}

export interface BenchReport {
  at?: string
  image?: { cold: number; warm: number; workflow?: string; size?: string; steps?: number } | null
  tts?: Record<string, { seconds: number; audio_seconds: number }>
  skipped?: Record<string, string>
}

export interface WorkerRow {
  id: number
  name: string
  enabled: boolean
  online: boolean
  last_seen: string | null
  address: string
  gpu_name: string
  vram_total_mb: number
  vram_free_mb: number
  capabilities: string[]
  models: Record<string, unknown>
  measured: { avg?: Record<string, SpeedRow>; bench?: BenchReport }
  info: Record<string, unknown>
  busy: boolean
  current_task: number | null
  created_at: string
  tasks?: RemoteTaskRow[]
}

export interface LanStatus {
  running: boolean
  enabled: boolean
  port: number
  addresses: string[]
  error: string
}

export interface RemoteTaskRow {
  id: number
  kind: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  worker: string
  progress: number
  progress_text: string
  seconds: number | null
  error: string
  created_at: string
  job: number | null
}

export interface WorkersOverview {
  devices: Device[]
  workers: WorkerRow[]
  lan: LanStatus
  recent_tasks: RemoteTaskRow[]
}

export interface PairingInfo {
  code: string
  expires_at: string
  valid_minutes: number
  port: number
  addresses: string[]
  urls: string[]
  lan: LanStatus
}

// ---------------------------------------------------------------- voices
export interface WarningText {
  en: string
  fa: string
}

export interface VoiceOption {
  id: string
  label: string
  gender: string
  language: string
}

export interface EngineInfo {
  id: string
  label: string
  available: boolean
  detail: string
  resource: string
  languages: string[]
  online: boolean
  needs_reference: boolean
  licence: string
  commercial: 'yes' | 'unknown' | 'no' | 'n/a'
  badge: string
  warning: string | null
  warning_text: WarningText | null
  default_voice: string
  voices: VoiceOption[]
}

export interface ServiceInfo {
  id: string
  label: string
  status: 'down' | 'loading' | 'ready' | 'error'
  installed: boolean
  missing: string[]
  licence: string
  commercial: string
  package: string
  url: string
  vram_mb: number
  managed: boolean
}

export interface AudioStatus {
  id: string
  label: string
  status: string
  detail: string
  data: { engine: string; kind: string; licence: string; resource: string }
}

export interface EnginesPayload {
  language: string
  engines: EngineInfo[]
  services: ServiceInfo[]
  audio: AudioStatus[]
  consent_templates: { fa: string; en: string }
  auto_note: string
}

export interface VoiceCast {
  id: number
  character: number
  language: string
  engine: string
  voice_id: string
  reference: number | null
  speed: number
  licence: { engine: string; commercial: string; badge: string; warning: string | null; warning_text: WarningText | null } | null
}

export interface VoiceRef {
  id: number
  character: number
  language: string
  label: string
  person_name: string
  consent_given: boolean
  consented_at: string | null
  purpose: string
  audio_url: string | null
  duration_sec: number | null
}

export interface CharacterVoices {
  character: { id: number; name: string; page: number }
  languages: string[]
  casts: VoiceCast[]
  refs: VoiceRef[]
}

export interface VoicePreviewResult {
  asset_id: number
  url: string
  engine: string
  seconds: number
  licence: { engine: string; commercial: string; badge: string; warning: string | null; warning_text: WarningText | null }
}

// ---------------------------------------------------------------- rigs
export interface RigPart {
  image: string
  pivot: [number, number]
  pos: [number, number]
  z: number
  parent: string | null
  group: string | null
  state: string | null
  url: string | null
}

export interface RigCompleteness {
  mouth_shapes: string[]
  missing_mouth_shapes: string[]
  has_arms: boolean
  has_legs: boolean
  has_blink: boolean
  parts: number
  ok: boolean
}

export interface Rig {
  id: number
  character: number
  version: number
  name: string
  source: string
  approved: boolean
  notes: string
  created_at: string
  sheet_asset: number | null
  size: [number, number] | null
  anchor: [number, number] | null
  parts: Record<string, RigPart>
  completeness: RigCompleteness | null
}

export interface MotionInfo {
  name: string
  duration: number
  loop: boolean
  base: boolean
  parts: string[]
}

export interface CharacterLite {
  id: number
  name: string
  page: number
  role?: string
  references?: { id: number; kind: string; label: string; asset: number | null; asset_url: string | null }[]
}

export interface PageLite {
  id: number
  name: string
  languages: string[]
}
