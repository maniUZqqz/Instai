// Shapes of the platform API (instai/ops/api.py): the processing queue, the computers' report, scheduled downloads, the version.

export interface Explain {
  code: string
  known: boolean
  what_fa: string
  what_en: string
  advice_fa: string
  advice_en: string
}

export interface NodeBrief {
  key: string
  name: string
  name_en: string
  kind: 'local' | 'worker'
  enabled: boolean
  online: boolean
  last_seen: string | null
  worker_id: number | null
  host: string
}

export interface QueueSummary {
  running: number
  queued: number
  waiting_node: number
  waiting_service: number
  scheduled: number
  waiting_turn: number
  waiting: number
  offline_nodes: string[]
}

export type QueueState =
  | 'running' | 'waiting_gpu' | 'waiting_node' | 'waiting_service' | 'retry' | 'waiting_turn' | 'window' | 'scheduled'
  | 'succeeded' | 'failed' | 'cancelled'

export interface QueueRow {
  id: number
  kind: string
  title_fa: string
  title_en: string
  for_fa: string
  for_en: string
  status: string
  state: QueueState
  state_fa: string
  state_en: string
  waiting_reason: string
  wait_code: string
  waiting_since: string | null
  position: number | null
  node: string
  attempts: number
  max_attempts: number
  deferrals: number
  progress: number
  resource: string
  created_at: string
  run_after: string | null
  window: string
  started_at: string | null
  finished_at: string | null
  duration_sec: number | null
  queue_wait_sec: number | null
  error: string
  explain: Explain | null
  can_cancel: boolean
  can_retry: boolean
  can_run_now: boolean
  is_download: boolean
  // only on /downloads/queue
  title?: string
  target?: string
  packages?: string[]
}

export interface QueueData {
  summary: QueueSummary
  nodes: NodeBrief[]
  active: QueueRow[]
  recent: QueueRow[]
}

export interface Stats {
  n: number
  avg: number | null
  median: number | null
  p95: number | null
  max: number | null
}

export interface KindRow {
  kind: string
  title_fa: string
  title_en: string
  total: number
  succeeded: number
  failed: number
  cancelled: number
  active: number
  duration: Stats
  wait: Stats
}

export interface TaskRow {
  kind: string
  total: number
  succeeded: number
  failed: number
  cancelled: number
  lost: number
  duration: Stats
}

export interface Current {
  at: string
  gpu_util: number | null
  gpu_temp: number | null
  vram_used_mb: number | null
  vram_total_mb: number | null
  ram_used_mb: number | null
  ram_total_mb: number | null
  disk_free_gb: number | null
  disk_total_gb: number | null
}

export interface SeriesPoint {
  at: string
  gpu_util: number | null
  gpu_temp: number | null
  vram_pct: number | null
  ram_pct: number | null
  disk_free_gb: number | null
}

export interface Seg {
  start: string
  end: string
  minutes: number
  version: string
}

export interface NodeReport extends NodeBrief {
  version: string
  gpu_name: string
  first_seen: string | null
  uptime_pct: number | null
  online_minutes: number
  sessions: Seg[]
  current: Current | null
  series: SeriesPoint[]
  jobs: { total: number; succeeded: number; failed: number; cancelled: number; active: number; duration: Stats; wait: Stats; gpu_seconds: number; deferrals: number }
  by_kind: KindRow[]
  tasks: TaskRow[]
}

export interface ErrorGroup extends Explain {
  count: number
  last_at: string | null
  kinds: { kind: string; count: number }[]
  sample: string
  job: number | null
}

export interface DownloadRow {
  id: number
  title: string
  title_fa: string
  title_en: string
  status: string
  state: string
  state_fa: string
  state_en: string
  progress: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_sec: number | null
  window: string
  target: string
  wait: number | null
  error: string
  explain: Explain | null
}

export interface ReportData {
  range: { from: string; to: string; days: number }
  generated_at: string
  nodes: NodeReport[]
  totals: { jobs: number; succeeded: number; failed: number; cancelled: number; active: number; waiting: number; deferrals: number; duration: Stats; wait: Stats; gpu_seconds: number }
  errors: ErrorGroup[]
  downloads: DownloadRow[]
  versions: { main: string; workers: Record<string, string> }
}

export interface LogRow {
  source: 'job' | 'event'
  at: string
  level: string
  node: string
  job: number | null
  kind: string
  title_fa: string
  title_en: string
  message: string
  text_fa?: string
  text_en?: string
  explain: Explain | null
}

export interface OpsConfig {
  download_mode: 'now' | 'window'
  download_window: string
  max_wait_hours: number
  retention_days: number
}

export type When = { mode: 'now' | 'default' } | { mode: 'at'; time: string } | { mode: 'window'; window?: string }

export interface CatalogItem {
  id: string
  title: string
  group: string
  offer: boolean
  curated?: boolean
  size: number
  missing_size: number
  complete: boolean
  default: boolean
  licence: string
}

export interface CuratedFile {
  id: string
  title: string
  kind: string
  size: number
  sha256: string
  folder: string
  name: string
  repo: string
  revision: string
  path: string
  license: string
  url: string
  mirror: string
  installed: boolean
  reused: boolean
  where: string
}

export interface CuratedPackage {
  id: string
  title: string
  group: 'image' | 'control' | 'upscale' | 'video' | 'voice'
  commercial: 'yes' | 'conditional' | 'no' | 'unknown'
  needs_confirm: boolean
  licence: string
  licence_url: string
  vram: string
  why: { fa?: string; en?: string }
  note: { fa?: string; en?: string }
  checked: string
  files: CuratedFile[]
  needs: string[]
  size: number
  missing_size: number
  installed: number
  reused: number
  complete: boolean
}

export interface Catalog {
  packages: CatalogItem[]
  curated?: CuratedPackage[]
  ollama: { model: string; fa: string; en: string; gb: number }[]
  targets: { id: string; name: string; name_en: string; online: boolean; can_download?: boolean }[]
  config: OpsConfig
}

export interface VersionInfo {
  name: string
  version: string
  commit: string
}

export interface ChangelogEntry {
  version: string
  date: string
  title: { fa: string; en: string }
  items: { fa: string; en: string }[]
}
