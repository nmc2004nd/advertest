/**
 * Kết quả tự tìm ngưỡng (requirements.md Phase 7, Frontend: tab Kết quả, mục "Điểm gãy"): câu kết
 * luận theo trạng thái, dòng tiến độ, số liệu quỹ đạo và so sánh điểm gãy giữa các attack.
 */
import type {
  AttackSpec,
  ExperimentDetail,
  RunView,
  SearchResult,
  SearchStage,
  SearchStatus,
  TrajectoryPoint,
} from '@/contracts/api'

type SearchConfig = NonNullable<ExperimentDetail['config']['attacks'][number]['search']>
type ThresholdKind = SearchResult['threshold_kind']

/** Thông tin spec cần để hiển thị (tên, tham số, đơn vị, `max` để chuẩn hóa). */
export interface SpecInfo {
  name: string
  paramName: string
  paramUnit: string
  paramMax: number
}

/** Một attack tìm ngưỡng của experiment: cấu hình, kết quả mới nhất (null khi chưa có điểm). */
export interface SearchAttack {
  attackSpecId: string
  spec: SpecInfo | null
  config: SearchConfig
  result: SearchResult | null
}

export const STAGE_LABEL: Record<SearchStage, string> = {
  coarse: 'quét thô',
  bisect_subset: 'chia đôi trên tập con',
  confirm: 'xác nhận trên toàn slice',
  bisect_full: 'chia đôi trên toàn slice',
  done: 'xong',
}

export const THRESHOLD_KIND_LABEL: Record<ThresholdKind, string> = {
  relative_drop: 'Mức sụt tương đối',
  absolute_drop: 'Mức sụt tuyệt đối',
  attack_success_rate: 'Tỷ lệ tấn công thành công',
}

export const NEAR_THRESHOLD = 'Sát ngưỡng'
export const NON_MONOTONIC = 'Không đơn điệu, cần xem kỹ'
/** Nhãn `not_reached`: "> {hi/max}%" (bằng "> 100%" khi tìm trên toàn dải của spec; review Group 6
 * #1). Không biết `max` của spec thì nói theo dải tìm kiếm. */
export function notReachedLabel(hi: number, max: number | undefined): string {
  return max ? `> ${formatPercentValue((hi / max) * 100)}` : 'Không gãy trong dải tìm kiếm'
}
export const BELOW_MIN_LABEL = '≤ mức nhỏ nhất'

/** Spec theo id: ưu tiên `RunView.attack_spec` (đúng phiên bản đã chạy), không có run thì lấy từ
 * catalog. */
export function specInfoMap(runs: RunView[], catalog: AttackSpec[]): Map<string, SpecInfo> {
  const map = new Map<string, SpecInfo>()
  for (const spec of catalog) {
    map.set(spec.id, {
      name: spec.name,
      paramName: spec.primary_param.name,
      paramUnit: spec.primary_param.unit,
      paramMax: spec.primary_param.max,
    })
  }
  for (const run of runs) {
    map.set(run.attack_spec_id, {
      name: run.attack_spec.name,
      paramName: run.attack_spec.param_name,
      paramUnit: run.attack_spec.param_unit,
      paramMax: run.attack_spec.param_max,
    })
  }
  return map
}

/** Attack tìm ngưỡng theo thứ tự trong cấu hình, ghép kết quả mới nhất. */
export function searchAttacks(
  experiment: ExperimentDetail,
  specs: Map<string, SpecInfo>,
): SearchAttack[] {
  const results = new Map((experiment.search_results ?? []).map((r) => [r.attack_spec_id, r]))
  return experiment.config.attacks.flatMap((a) =>
    a.mode === 'search' && a.search
      ? [
          {
            attackSpecId: a.attack_spec_id,
            spec: specs.get(a.attack_spec_id) ?? null,
            config: a.search,
            result: results.get(a.attack_spec_id) ?? null,
          },
        ]
      : [],
  )
}

/** Id attack quét lưới của cấu hình (đường cong và xếp hạng Phase 6 chỉ gồm các attack này). */
export function gridAttackIds(experiment: ExperimentDetail): Set<string> {
  return new Set(
    experiment.config.attacks.filter((a) => a.mode === 'grid').map((a) => a.attack_spec_id),
  )
}

export function attackName(attack: Pick<SearchAttack, 'attackSpecId' | 'spec'>): string {
  return attack.spec?.name ?? `Attack ${attack.attackSpecId.slice(0, 8)}`
}

/** Số gọn cho câu kết luận, tooltip, tiến độ: 4 chữ số có nghĩa, bỏ số 0 thừa (review Group 6 #2). */
export function formatNumber(value: number): string {
  return String(Number(value.toPrecision(4)))
}

/** Giá trị chính xác cho bảng số liệu (level chia đôi như 1.0625 giữ nguyên); chỉ bỏ nhiễu dấu
 * phẩy động. */
export function formatExact(value: number): string {
  return String(Number(value.toPrecision(12)))
}

/** Phần trăm (giá trị đã nhân 100), 1 chữ số thập phân, bỏ số 0 thừa: 100 → "100%", 1.5625 → "1.6%". */
function formatPercentValue(value: number): string {
  return `${String(Number(value.toFixed(1)))}%`
}

/** Đơn vị hiển thị; bỏ khi trùng tên tham số (fog: `severity ≈ 3`, không lặp "severity"). */
export function displayUnit(spec: SpecInfo | null): string {
  if (!spec || spec.paramUnit === spec.paramName) return ''
  return spec.paramUnit
}

/** Giá trị kèm đơn vị: `1/255` viết thành `6.5/255`, đơn vị khác viết sau dấu cách. */
export function formatLevel(value: number, unit: string): string {
  if (unit.startsWith('1/')) return `${formatNumber(value)}/${unit.slice(2)}`
  return unit ? `${formatNumber(value)} ${unit}` : formatNumber(value)
}

/** Khoảng kèm đơn vị: `0–32/255`. */
export function formatRange(lo: number, hi: number, unit: string): string {
  const range = `${formatNumber(lo)}–${formatNumber(hi)}`
  if (unit.startsWith('1/')) return `${range}/${unit.slice(2)}`
  return unit ? `${range} ${unit}` : range
}

function percent(value: number): string {
  return `${formatNumber(value * 100)}%`
}

/** "Ngưỡng: mức sụt tương đối 20% (class person)". */
export function thresholdText(
  config: Pick<SearchConfig, 'threshold_kind' | 'threshold' | 'class_filter'>,
): string {
  const scope = config.class_filter ? ` (class ${config.class_filter})` : ''
  return `Ngưỡng: ${THRESHOLD_KIND_LABEL[config.threshold_kind].toLowerCase()} ${percent(config.threshold)}${scope}`
}

/** Câu kết luận của thẻ tóm tắt theo trạng thái (đủ 6 trạng thái, đang chạy, chưa có điểm). */
export function conclusion(attack: SearchAttack): string {
  const { result, config } = attack
  const unit = displayUnit(attack.spec)
  const param = attack.spec?.paramName ?? 'level'
  if (!result) return 'Chưa có điểm nào.'
  const [a, b] = result.bracket
  const status: SearchStatus | null = result.status
  if (status === null) return `Đang tìm: khoảng hiện tại ${formatRange(a, b, unit)}.`
  const atBreak = () => {
    const ci = result.confidence_interval
    const point = `Gãy tại ${param} ≈ ${formatLevel(result.breaking_point ?? b, unit)}`
    return ci ? `${point}, KTC 95%: ${formatRange(ci[0], ci[1], unit)}` : point
  }
  switch (status) {
    case 'found':
    case 'non_monotonic':
      return atBreak()
    case 'not_reached':
      return `Không gãy trong dải ${formatRange(config.lo, config.hi, unit)}`
    case 'below_min':
      return `Gãy ngay ở mức nhỏ nhất (${param} = ${formatLevel(config.lo, unit)})`
    case 'stopped_limit':
      return `Dừng do giới hạn trước khi kết luận: khoảng hiện có ${formatRange(a, b, unit)}`
    case 'failed':
      return result.message ?? 'Tìm ngưỡng thất bại.'
  }
}

/** Dòng tiến độ khi đang chạy: "Điểm 5 / tối đa 13 · khoảng hiện tại [4, 8] · giai đoạn: …". */
export function progressText(result: SearchResult | null): string | null {
  if (!result || result.stage === 'done') return null
  const [a, b] = result.bracket
  return (
    `Điểm ${result.points_used} / tối đa ${result.max_points} · ` +
    `khoảng hiện tại [${formatNumber(a)}, ${formatNumber(b)}] · ` +
    `giai đoạn: ${STAGE_LABEL[result.stage]}`
  )
}

/** Nhãn trục tung của quỹ đạo theo loại ngưỡng (kèm class khi lọc). */
export function dropLabel(result: Pick<SearchResult, 'threshold_kind' | 'class_filter'>): string {
  const scope = result.class_filter ? ` (class ${result.class_filter})` : ''
  return `${THRESHOLD_KIND_LABEL[result.threshold_kind]}${scope}`
}

/** Điểm quỹ đạo theo thứ tự đánh giá. */
export function trajectoryRows(result: SearchResult): TrajectoryPoint[] {
  return [...result.trajectory].sort((x, y) => x.order - y.order)
}

export interface ComparisonRow {
  attackSpecId: string
  name: string
  status: SearchStatus | null
  /** Độ dài cột (% dải: level / max của spec); null khi không vẽ cột. */
  value: number | null
  label: string
}

/**
 * So sánh điểm gãy chuẩn hóa về % dải của spec (`level / max`, cùng quy ước trục chuẩn hóa Phase
 * 6), tăng dần: càng nhỏ càng dễ gãy. `not_reached` "> 100%", `below_min` "≤ mức nhỏ nhất";
 * trạng thái khác không có cột.
 */
export function comparisonRows(attacks: SearchAttack[]): ComparisonRow[] {
  // Khóa sắp xếp: NaN là không có cột (xếp cuối, giữ thứ tự cấu hình).
  const keyed = attacks.map((attack): [ComparisonRow, number] => {
    const { result, spec, config } = attack
    const status = result?.status ?? null
    const row = { attackSpecId: attack.attackSpecId, name: attackName(attack), status }
    const label = (value: number | null) => (value === null ? '—' : formatPercentValue(value))
    const max = spec?.paramMax
    const scaled = (level: number) => (max ? (level / max) * 100 : null)
    switch (status) {
      case 'found':
      case 'non_monotonic': {
        const value = scaled(result?.breaking_point ?? 0)
        return [{ ...row, value, label: label(value) }, value ?? Number.POSITIVE_INFINITY]
      }
      case 'not_reached':
        // Cột dài tới cận trên của dải tìm kiếm: điểm gãy (nếu có) nằm sau đó.
        return [
          { ...row, value: scaled(config.hi), label: notReachedLabel(config.hi, max) },
          Number.POSITIVE_INFINITY,
        ]
      case 'below_min':
        return [
          { ...row, value: scaled(config.lo), label: BELOW_MIN_LABEL },
          Number.NEGATIVE_INFINITY,
        ]
      case 'stopped_limit':
        return [{ ...row, value: null, label: 'Dừng do giới hạn: chưa có điểm gãy' }, Number.NaN]
      case 'failed':
        return [{ ...row, value: null, label: 'Thất bại' }, Number.NaN]
      case null:
        return [{ ...row, value: null, label: result ? 'Đang tìm' : 'Chưa có điểm' }, Number.NaN]
    }
  })
  const ranked = keyed.filter(([, key]) => !Number.isNaN(key)).sort((x, y) => x[1] - y[1])
  const rest = keyed.filter(([, key]) => Number.isNaN(key))
  return [...ranked, ...rest].map(([row]) => row)
}
