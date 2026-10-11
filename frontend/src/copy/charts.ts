/**
 * Đoạn "Cách đọc" của từng biểu đồ trong tab Kết quả (requirements.md Phase R3, Kết quả và insight):
 * 2–4 câu về trục, màu, đường ngưỡng.
 */
export const HOW_TO_READ = 'Cách đọc'

export const READING = {
  curves:
    'Trục hoành là level của attack (bật trục chuẩn hóa thì là % dải cho phép), trục tung là mAP@0.5 sau tấn công, từ 0 đến 1. Đường nét đứt nằm ngang là mAP trên ảnh sạch; khoảng cách từ đường đó xuống điểm dữ liệu là mức sụt. Hình thoi rỗng màu đỏ là run dừng giữa chừng: metric chỉ tính trên phần ảnh đã xử lý.',
  ranking:
    'Mỗi cột là diện tích dưới đường mức sụt của một attack (auc_drop, từ 0 đến 1). Cột càng dài thì attack gây hại càng nhiều trên toàn dải cường độ. Attack chưa đủ dữ liệu không có cột nhưng vẫn có trong bảng.',
  breakpoints:
    'Mỗi cột là điểm gãy của một attack, tính bằng % dải tham số của spec. Cột càng ngắn thì model gãy càng sớm. Nhãn "> 100%" nghĩa là model chưa gãy trong dải tìm kiếm.',
  matrix:
    'Mỗi hàng là một attack quét lưới, mỗi cột là một phần tư dải cường độ của attack đó. Số trong ô là mức sụt mAP@0.5 tương đối lớn nhất của các level trong dải; nền đỏ càng đậm thì sụt càng nhiều, ô viền đỏ là sụt từ 30% trở lên. Ô gạch chéo là dải chưa có level nào được chạy.',
} as const

export const NOT_RUN = 'Chưa chạy'
export const NO_RESULT_TITLE = 'Chưa có run nào có kết quả'
export const NO_RESULT_BODY =
  'Kết luận, điểm yếu và ma trận độ bền hiện khi có ít nhất một run có metric. Theo dõi tiến độ ở tab Tổng quan.'
export const PARTIAL_LABEL = 'Kết quả một phần'
export const WEAKNESS_NOTE =
  'Điểm yếu là gợi ý để review, không thay cho tiêu chí đạt của protocol.'
