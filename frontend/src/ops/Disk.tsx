import { useConfirm } from '../components/feedback'
import { Notice } from '../components/ui'
import { useI18n } from '../i18n'
import type { Catalog } from './types'

const GB = 1024 ** 3

/** What a download of `need` bytes to this PC means for its disk: does it fit (with the spare the server insists on), and is it big enough to ask «are you sure?». */
export function diskState(cat: Catalog, need: number, local: boolean) {
  const free = cat.free_bytes ?? null
  const spare = cat.spare_bytes ?? 2 * GB
  const big = cat.big_bytes ?? 2 * GB
  const known = local && free !== null && need > 0
  return { free, spare, big, fits: !known || need + spare <= (free as number), large: local && need >= big }
}

/** The free space of this PC's disk, and - when the chosen download would not fit - a plain warning (the server refuses it too). */
export function DiskNote({ cat, need, local }: { cat: Catalog; need: number; local: boolean }) {
  const { t, f } = useI18n()
  const d = diskState(cat, need, local)
  if (!local || d.free === null) return null
  if (!d.fits) return <Notice tone="warn" icon="alert">{t('ops.dl.no_room', { need: f.bytes(need), free: f.bytes(d.free), spare: f.bytes(d.spare) })}</Notice>
  return <p className="small muted" data-testid="disk-free">{t('ops.dl.free_space', { x: f.bytes(d.free) })}</p>
}

/** «این دانلود X گیگابایت است…» before a big download starts. Resolves true when the owner says go (or when nothing needs asking). */
export function useBigDownloadConfirm(cat: Catalog) {
  const { t, f } = useI18n()
  const confirm = useConfirm()
  return async (need: number, local: boolean): Promise<boolean> => {
    const d = diskState(cat, need, local)
    if (!d.large) return true
    return confirm({ message: t('ops.dl.big_confirm', { size: f.bytes(need), free: d.free === null ? '—' : f.bytes(d.free) }), confirmLabel: t('ops.dl.go') })
  }
}
