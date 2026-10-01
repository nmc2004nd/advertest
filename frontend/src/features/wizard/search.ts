/**
 * Cấu hình tự tìm ngưỡng trong wizard (requirements.md Phase 7, mục Frontend và API; plan task
 * 24): giá trị mặc định, schema `zod` cùng luật với backend (`experiment_config.py`) để báo lỗi
 * ngay cạnh ô nhập, chuyển qua lại với `SearchConfig` của contract.
 */
import { z } from 'zod'

import type { components } from '@/contracts/api'

export type SearchConfig = components['schemas']['SearchConfig']
type PrimaryParam = components['schemas']['PrimaryParam']
export type ThresholdKind = SearchConfig['threshold_kind']

export interface SearchDraft {
  thresholdKind: ThresholdKind
  /** Trong (0, 1]; giao diện hiển thị %. */
  threshold: number
  classFilter: string | null
  lo: number
  hi: number
  /** Chỉ dùng với tham số liên tục; rời rạc vẫn gửi `(hi − lo) / 256` vì contract bắt buộc. */
  tol: number
  coarseN: number
  subsetSize: number
  bootstrapSamples: number
}

export const THRESHOLD_KINDS: { kind: ThresholdKind; label: string; hint: string }[] = [
  {
    kind: 'relative_drop',
    label: 'Mức sụt tương đối',
    hint: 'mAP@0.5 giảm bao nhiêu phần trăm so với ảnh sạch.',
  },
  {
    kind: 'absolute_drop',
    label: 'Mức sụt tuyệt đối',
    hint: 'mAP@0.5 giảm bao nhiêu điểm phần trăm (không lớn hơn mAP ảnh sạch).',
  },
  {
    kind: 'attack_success_rate',
    label: 'Tỷ lệ tấn công thành công',
    hint: 'Tỷ lệ object detect đúng trên ảnh sạch bị mất hoặc sai class sau biến đổi.',
  },
]

export const DEFAULT_THRESHOLD = 0.2
export const DEFAULT_COARSE_N = 4
export const DEFAULT_SUBSET_SIZE = 100
export const DEFAULT_BOOTSTRAP = 200
export const SMALL_SUBSET = 20

/** `tol` mặc định = (hi − lo) / 256 (kickoff Phase 7). */
export function defaultTol(lo: number, hi: number): number {
  return (hi - lo) / 256
}

/** Mặc định: dải của spec, `relative_drop` 20%; tập con tối đa bằng số ảnh của slice (API từ chối
 * tập con lớn hơn slice; kế hoạch Group 5). */
export function defaultSearch(param: PrimaryParam, sliceSize: number | null): SearchDraft {
  return {
    thresholdKind: 'relative_drop',
    threshold: DEFAULT_THRESHOLD,
    classFilter: null,
    lo: param.min,
    hi: param.max,
    tol: defaultTol(param.min, param.max),
    coarseN: DEFAULT_COARSE_N,
    subsetSize: Math.max(2, Math.min(DEFAULT_SUBSET_SIZE, sliceSize ?? DEFAULT_SUBSET_SIZE)),
    bootstrapSamples: DEFAULT_BOOTSTRAP,
  }
}

export function isDiscrete(param: PrimaryParam): boolean {
  return param.type === 'discrete' && (param.values?.length ?? 0) > 0
}

/** Schema của form: lỗi gắn đúng tên trường của `SearchDraft`. */
export function searchSchema(
  param: PrimaryParam,
  sliceSize: number | null,
  targetClasses: string[] | null,
) {
  const discrete = isDiscrete(param)
  const values = param.values ?? []
  return z
    .object({
      thresholdKind: z.enum(['relative_drop', 'absolute_drop', 'attack_success_rate']),
      threshold: z
        .number({ message: 'Nhập ngưỡng' })
        .gt(0, 'Ngưỡng phải lớn hơn 0%')
        .lte(1, 'Ngưỡng tối đa 100%'),
      classFilter: z.string().min(1).nullable(),
      lo: z.number({ message: 'Nhập cận dưới' }),
      hi: z.number({ message: 'Nhập cận trên' }),
      tol: z.number({ message: 'Nhập độ chính xác' }).gt(0, 'Độ chính xác phải lớn hơn 0'),
      coarseN: z
        .number({ message: 'Nhập số điểm quét thô' })
        .int('Số điểm quét thô là số nguyên')
        .min(3, 'Số điểm quét thô từ 3 đến 8')
        .max(8, 'Số điểm quét thô từ 3 đến 8'),
      subsetSize: z
        .number({ message: 'Nhập kích thước tập con' })
        .int('Kích thước tập con là số nguyên')
        .min(2, 'Tập con tối thiểu 2 ảnh'),
      bootstrapSamples: z
        .number({ message: 'Nhập số mẫu bootstrap' })
        .int('Số mẫu bootstrap là số nguyên')
        .min(0, 'Số mẫu bootstrap từ 0 đến 1000')
        .max(1000, 'Số mẫu bootstrap từ 0 đến 1000'),
    })
    .superRefine((value, ctx) => {
      const range = `[${param.min}, ${param.max}]${param.unit ? ` ${param.unit}` : ''}`
      for (const name of ['lo', 'hi'] as const) {
        const level = value[name]
        if (level < param.min || level > param.max) {
          ctx.addIssue({ code: 'custom', path: [name], message: `Ngoài dải của spec ${range}` })
        } else if (discrete && !values.includes(level)) {
          ctx.addIssue({ code: 'custom', path: [name], message: `Chỉ nhận ${values.join(', ')}` })
        }
      }
      if (value.lo >= value.hi) {
        ctx.addIssue({ code: 'custom', path: ['hi'], message: 'Cận trên phải lớn hơn cận dưới' })
      } else if (!discrete && value.tol >= value.hi - value.lo) {
        ctx.addIssue({
          code: 'custom',
          path: ['tol'],
          message: 'Độ chính xác phải nhỏ hơn độ rộng dải',
        })
      }
      if (sliceSize !== null && value.subsetSize > sliceSize) {
        ctx.addIssue({
          code: 'custom',
          path: ['subsetSize'],
          message: `Tập con tối đa bằng số ảnh của slice (${sliceSize})`,
        })
      }
      if (
        value.classFilter !== null &&
        targetClasses !== null &&
        !targetClasses.includes(value.classFilter)
      ) {
        ctx.addIssue({
          code: 'custom',
          path: ['classFilter'],
          message: `${value.classFilter} không phải class đích của mapping`,
        })
      }
    })
}

export type SearchField = keyof SearchDraft

/** Lỗi theo trường (thông điệp đầu tiên của mỗi trường); rỗng khi hợp lệ. */
export function searchErrors(
  draft: SearchDraft,
  param: PrimaryParam,
  sliceSize: number | null,
  targetClasses: string[] | null,
): Partial<Record<SearchField, string>> {
  const parsed = searchSchema(param, sliceSize, targetClasses).safeParse(draft)
  if (parsed.success) return {}
  const errors: Partial<Record<SearchField, string>> = {}
  for (const issue of parsed.error.issues) {
    const field = issue.path[0] as SearchField
    errors[field] ??= issue.message
  }
  return errors
}

/** Đường dẫn trường của lỗi 422 (`attacks.<i>.search.<tên>`) theo tên trường trong form. */
export const SERVER_FIELD: Record<SearchField, string> = {
  thresholdKind: 'threshold_kind',
  threshold: 'threshold',
  classFilter: 'class_filter',
  lo: 'lo',
  hi: 'hi',
  tol: 'tol',
  coarseN: 'coarse_n',
  subsetSize: 'subset_size',
  bootstrapSamples: 'bootstrap_samples',
}

/** Body `SearchConfig`. Tham số rời rạc: form giữ `tol = (hi − lo) / 256` khi đổi dải. */
export function toSearchConfig(draft: SearchDraft): SearchConfig {
  return {
    threshold_kind: draft.thresholdKind,
    threshold: draft.threshold,
    lo: draft.lo,
    hi: draft.hi,
    tol: draft.tol,
    coarse_n: draft.coarseN,
    subset_size: draft.subsetSize,
    class_filter: draft.classFilter,
    bootstrap_samples: draft.bootstrapSamples,
  }
}

export function fromSearchConfig(config: SearchConfig): SearchDraft {
  return {
    thresholdKind: config.threshold_kind,
    threshold: config.threshold,
    classFilter: config.class_filter ?? null,
    lo: config.lo,
    hi: config.hi,
    tol: config.tol,
    coarseN: config.coarse_n,
    subsetSize: config.subset_size,
    bootstrapSamples: config.bootstrap_samples,
  }
}

/** Class đích của mapping (giá trị khác null của `classes`), không trùng, sắp xếp. */
export function targetClassesOf(classes: Record<string, string | null> | undefined): string[] {
  return [...new Set(Object.values(classes ?? {}).filter((c): c is string => c !== null))].sort()
}
