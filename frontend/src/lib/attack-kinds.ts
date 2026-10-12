import {
  CloudFog,
  Contrast,
  Crosshair,
  type LucideIcon,
  Repeat,
  Shuffle,
  Snowflake,
  SquareDashed,
  Sticker,
  ThermometerSnowflake,
  Wind,
  Zap,
} from 'lucide-react'

import type { AttackKind } from '@/contracts/api'

/** Tên nhóm attack (requirements.md Phase 6, Frontend: wizard bước 4 và bảng xếp hạng). */
export const ATTACK_KIND_LABEL: Record<AttackKind, string> = {
  attack: 'Tấn công',
  corruption: 'Biến đổi điều kiện',
  occlusion: 'Che khuất',
}

/** Thứ tự nhóm cố định. */
export const ATTACK_KINDS: AttackKind[] = ['attack', 'corruption', 'occlusion']

/**
 * Một câu đời thường cho từng attack trong catalog (theo tên spec), để người mới hiểu attack đó
 * mô phỏng điều gì ngoài đời. Spec mới chưa có câu mô tả thì chỉ hiện tên.
 */
export const ATTACK_PLAIN: Record<string, string> = {
  fgsm: 'Thêm nhiễu rất nhỏ theo một bước gradient. Nhanh, hợp để dò điểm yếu đầu tiên.',
  pgd_linf: 'Nhiễu tinh vi lặp nhiều bước, mỗi điểm ảnh lệch không quá eps. Mạnh hơn FGSM.',
  pgd_l2: 'Như PGD nhưng giới hạn tổng độ lệch của cả ảnh, nhiễu trải đều hơn.',
  adv_patch: 'Một miếng dán in được, đặt lên ảnh để đánh lừa model. Gần với tấn công ngoài đời.',
  contrast: 'Ảnh mất tương phản như trời âm u hoặc ngược sáng.',
  fog: 'Sương mù làm mờ vật ở xa.',
  frost: 'Kính camera bám sương giá.',
  motion_blur: 'Ảnh nhòe do xe hoặc camera đang chuyển động.',
  snow: 'Tuyết rơi che một phần khung hình.',
  bbox_occlusion: 'Một vật che khuất một phần đối tượng, như người đứng sau cột đèn.',
}

/** Cách thuật toán hoạt động và rủi ro ngoài đời mà nó mô phỏng (1–2 câu mỗi ý). */
export interface AttackExplain {
  how: string
  risk: string
}

export const ATTACK_EXPLAIN: Record<string, AttackExplain> = {
  fgsm: {
    how: 'Tính gradient của hàm mất mát theo ảnh một lần, rồi đẩy mỗi điểm ảnh lệch đúng eps theo hướng làm model sai nhiều nhất.',
    risk: 'Người biết rõ model chèn nhiễu mắt thường không thấy vào luồng ảnh camera.',
  },
  pgd_linf: {
    how: 'Lặp nhiều bước FGSM nhỏ; sau mỗi bước kéo ảnh về lại trong khoảng ±eps quanh ảnh gốc.',
    risk: 'Kẻ tấn công có thời gian tối ưu nhiễu: kịch bản xấu nhất với nhiễu nhỏ trên từng điểm ảnh.',
  },
  pgd_l2: {
    how: 'Như PGD L∞ nhưng giới hạn độ dài (chuẩn L2) của cả vector nhiễu, nên nhiễu có thể dồn vào vài vùng ảnh.',
    risk: 'Nhiễu tập trung cục bộ, giống vết bẩn hay phản chiếu được tính toán sẵn.',
  },
  adv_patch: {
    how: 'Huấn luyện một miếng dán trên slice huấn luyện riêng để model sai nhiều nhất, rồi dán vào ảnh.',
    risk: 'Miếng dán in ra giấy dán lên biển báo, thân xe hay áo: tấn công vật lý ngoài đời.',
  },
  fog: {
    how: 'Phủ một lớp sương lên ảnh; severity càng cao lớp sương càng dày và ảnh càng mất tương phản.',
    risk: 'Sương mù, mưa phùn làm mờ người và xe ở xa.',
  },
  snow: {
    how: 'Vẽ các lớp hạt tuyết nhòe theo hướng rơi và làm sáng ảnh, mật độ tăng theo severity.',
    risk: 'Tuyết rơi, bụi bay che khuất một phần khung hình.',
  },
  frost: {
    how: 'Trộn ảnh với ảnh chụp lớp băng giá thật; severity càng cao lớp băng càng đậm.',
    risk: 'Kính chắn gió hoặc ống kính đọng sương, đóng băng.',
  },
  motion_blur: {
    how: 'Làm nhòe ảnh theo một hướng, độ dài vệt nhòe tăng theo severity.',
    risk: 'Xe chạy nhanh, camera rung, tốc độ chụp chậm khi trời tối.',
  },
  contrast: {
    how: 'Kéo mọi điểm ảnh về độ sáng trung bình, thu hẹp khoảng sáng tối theo severity.',
    risk: 'Trời âm u, ngược sáng, đèn pha chói.',
  },
  bbox_occlusion: {
    how: 'Đặt một hình chữ nhật xám bên trong mỗi object, che đúng tỉ lệ diện tích đã chọn.',
    risk: 'Người bị cột đèn, xe khác hay biển quảng cáo che một phần.',
  },
}

/** Ô biểu tượng của từng attack (class `tile` với `--tile-bg`/`--tile-fg`), màu theo nhóm. */
export interface AttackLook {
  icon: LucideIcon
  tile: string
}

const KIND_LOOK: Record<AttackKind, AttackLook> = {
  attack: { icon: Zap, tile: '[--tile-bg:#fce7f3] [--tile-fg:#be185d]' },
  corruption: { icon: CloudFog, tile: '[--tile-bg:#e0f2fe] [--tile-fg:#0369a1]' },
  occlusion: { icon: SquareDashed, tile: '[--tile-bg:#ffedd5] [--tile-fg:#c2410c]' },
}

const NAME_ICON: Record<string, LucideIcon> = {
  fgsm: Zap,
  pgd_linf: Repeat,
  pgd_l2: Crosshair,
  adv_patch: Sticker,
  fog: CloudFog,
  snow: Snowflake,
  frost: ThermometerSnowflake,
  motion_blur: Wind,
  contrast: Contrast,
  bbox_occlusion: SquareDashed,
}

/** Nhóm của các spec trong seed catalog, cho chỗ chỉ có tên attack (bảng run, report). */
const NAME_KIND: Record<string, AttackKind> = {
  fgsm: 'attack',
  pgd_linf: 'attack',
  pgd_l2: 'attack',
  adv_patch: 'attack',
  fog: 'corruption',
  snow: 'corruption',
  frost: 'corruption',
  motion_blur: 'corruption',
  contrast: 'corruption',
  bbox_occlusion: 'occlusion',
}

/**
 * Icon theo tên spec (spec mới: icon của nhóm), màu theo nhóm. Không biết nhóm (chỉ có tên, spec
 * ngoài seed) thì icon chung, màu mặc định của `tile`.
 */
export function attackLook(spec: { name: string; kind?: AttackKind | null }): AttackLook {
  const kind = spec.kind ?? NAME_KIND[spec.name]
  const base = (kind && KIND_LOOK[kind]) || { icon: Shuffle, tile: '' }
  return { icon: NAME_ICON[spec.name] ?? base.icon, tile: base.tile }
}
