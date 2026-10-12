/** Câu chữ của mục "Nhận xét chi tiết" do LLM viết (tab Kết quả của experiment). */
export const NARRATIVE = {
  title: 'Nhận xét chi tiết',
  badge: 'AI viết',
  disclaimer:
    'AI viết nhận xét này từ số liệu ở trên, chỉ để tham khảo. Nó không thay câu kết luận hay tiêu chí của protocol và không có trong report.',
  intro:
    'Tạo nhận xét để AI phân tích các chỉ số: attack nào làm model sụt nhiều, xu hướng theo level, class yếu và gợi ý bước tiếp theo. Chỉ số liệu được gửi đi, không gửi ảnh.',
  create: 'Tạo nhận xét',
  recreate: 'Tạo lại nhận xét',
  creating: 'Đang viết nhận xét, có thể mất tới một phút…',
  waiting: 'Tạo được nhận xét khi experiment đã chạy xong.',
  findings: 'Phân tích',
  nextSteps: 'Gợi ý bước tiếp theo',
  stale:
    'Số liệu đã thay đổi sau khi nhận xét này được viết (có run mới xong). Tạo lại để nhận xét khớp với kết quả hiện tại.',
  partial: 'Viết từ kết quả một phần',
  meta: (model: string, time: string) => `Viết lúc ${time} bằng ${model}`,
} as const
