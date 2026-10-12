import { Compass, Gauge, type LucideIcon, Microscope, ShieldCheck, Zap } from 'lucide-react'

/** Ô icon trước tiêu đề thẻ chọn (class `tile` với `--tile-bg`/`--tile-fg`). */
export interface CardLook {
  icon: LucideIcon
  tile: string
}

export const MODE_ICON: Record<'exploration' | 'official', CardLook> = {
  exploration: { icon: Compass, tile: '[--tile-bg:#e0f2fe] [--tile-fg:#0369a1]' },
  official: { icon: ShieldCheck, tile: '[--tile-bg:#dcfce7] [--tile-fg:#15803d]' },
}

/** Icon của preset theo key (seed `experiment_presets.json`); key mới dùng icon chung. */
export const PRESET_ICON: Record<string, CardLook> = {
  fast: { icon: Zap, tile: '[--tile-bg:#fce7f3] [--tile-fg:#be185d]' },
  standard: { icon: Gauge, tile: '[--tile-bg:#f5f3ff] [--tile-fg:#6d28d9]' },
  deep: { icon: Microscope, tile: '[--tile-bg:#ffedd5] [--tile-fg:#c2410c]' },
}
