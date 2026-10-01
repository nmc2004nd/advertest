import type { RunStatus, RunView } from '@/contracts/api'

/** Một điểm (một run) trên đường cong của một attack. */
export interface CurvePoint {
  runId: string
  level: number
  status: RunStatus
  /** mAP@0.5 sau tấn công; null khi run không có metric. */
  map50: number | null
  asr: number | null
  relativeDrop: number | null
  /** Metric chỉ tính trên phần ảnh đã xử lý (run `stopped_limit`). */
  partial: boolean
  /** Bỏ qua do dừng sớm: model đã sụp ở level thấp hơn (Phase 6). */
  earlyStop: boolean
}

export interface AttackCurve {
  attackSpecId: string
  name: string
  version: number
  paramName: string
  paramUnit: string
  /** `primary_param.max` của spec (đề xuất contract 003): trục chuẩn hóa `level / paramMax`. */
  paramMax: number
  points: CurvePoint[]
}

/** Gom run theo attack (thứ tự xuất hiện), điểm sắp theo level; giữ cả run không có metric
 * để bảng số liệu đủ mọi run. */
export function buildCurves(runs: RunView[]): AttackCurve[] {
  const curves = new Map<string, AttackCurve>()
  for (const run of runs) {
    let curve = curves.get(run.attack_spec_id)
    if (!curve) {
      curve = {
        attackSpecId: run.attack_spec_id,
        name: run.attack_spec.name,
        version: run.attack_spec.version,
        paramName: run.attack_spec.param_name,
        paramUnit: run.attack_spec.param_unit,
        paramMax: run.attack_spec.param_max,
        points: [],
      }
      curves.set(run.attack_spec_id, curve)
    }
    curve.points.push({
      runId: run.run_id,
      level: run.level,
      status: run.status,
      map50: run.metrics?.attacked.map50 ?? null,
      asr: run.metrics?.attack_success_rate ?? null,
      relativeDrop: run.metrics?.relative_drop ?? null,
      partial: run.metrics?.partial ?? false,
      earlyStop: run.status_reason?.code === 'early_stop',
    })
  }
  for (const curve of curves.values()) curve.points.sort((a, b) => a.level - b.level)
  return [...curves.values()]
}

/** Điểm vẽ được (có metric) của một đường. */
export function plotted(curve: AttackCurve, metric: 'map50' | 'asr'): CurvePoint[] {
  return curve.points.filter((p) => p[metric] !== null)
}

export function formatMetric(value: number | null): string {
  return value === null ? '—' : value.toFixed(3)
}

export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

/** Vị trí trên trục hoành: level gốc, hoặc % dải cho phép (`level / max`, như bảng xếp hạng). */
export function axisValue(curve: AttackCurve, level: number, normalized: boolean): number {
  return normalized ? (level / curve.paramMax) * 100 : level
}
