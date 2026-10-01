import type { AttackKind } from '@/contracts/api'

/** Tên nhóm attack (requirements.md Phase 6, Frontend: wizard bước 4 và bảng xếp hạng). */
export const ATTACK_KIND_LABEL: Record<AttackKind, string> = {
  attack: 'Tấn công',
  corruption: 'Biến đổi điều kiện',
  occlusion: 'Che khuất',
}

/** Thứ tự nhóm cố định. */
export const ATTACK_KINDS: AttackKind[] = ['attack', 'corruption', 'occlusion']
