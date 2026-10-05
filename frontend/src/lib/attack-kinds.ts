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
