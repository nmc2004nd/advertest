import type { PerturbationImageKind } from '@/contracts/api'

/** Nhãn ảnh thứ ba theo loại (requirements.md Phase 6, Frontend: trình xem case). */
export const THIRD_IMAGE_LABEL: Record<PerturbationImageKind, string> = {
  amplified_noise: 'Nhiễu khuếch đại',
  difference: 'Vùng khác biệt',
  patch_location: 'Vị trí patch',
}
