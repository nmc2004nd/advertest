import type { ModelSummary } from '@/contracts/api'
import type { Me } from '@/contracts/schemas'

/**
 * Người xem được xóa, lưu trữ, kiểm lại, thêm class mapping cho model không: người đăng ký model
 * hoặc admin (luật sở hữu ở `backend/app/services/model_admin.py`, đề xuất contract 002).
 */
export function canManageModel(model: ModelSummary, me: Me | undefined): boolean {
  if (!me) return false
  return me.roles.includes('admin') || (model.owner_id != null && model.owner_id === me.id)
}
