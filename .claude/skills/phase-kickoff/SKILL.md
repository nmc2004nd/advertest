---
name: phase-kickoff
description: Bắt đầu một phase của AdverTest theo quy trình spec-driven development - đọc constitution và feature spec, tóm tắt phase, tìm chỗ mơ hồ, kiểm tra độ phủ requirement → plan → validation và điều kiện tiên quyết, rồi dừng lại hỏi. Dùng skill này mỗi khi người dùng muốn bắt đầu, khởi động, chuẩn bị, "đọc spec", "kickoff" một phase, hỏi "phase tiếp theo là gì", hoặc trước khi giao bất kỳ group nào của một phase mới cho agent, kể cả khi người dùng không nhắc tên skill.
---

# Khởi động một phase

Mục đích: trước khi ai viết code, mọi chỗ mơ hồ trong spec phải được lộ ra và được trả lời **trong spec**, không phải trong chat. Skill này chỉ đọc và hỏi. Nó không viết code và không tự sửa spec.

## 1. Xác định phase

- Nếu người dùng nêu phase (ví dụ "phase 3") hoặc thư mục spec: dùng thư mục `specs/*-phase-NN-*/` tương ứng.
- Nếu không: đọc `specs/roadmap.md`, chọn phase đầu tiên chưa được đánh dấu hoàn thành, và nói rõ bạn đã chọn phase nào.
- Nếu thư mục spec của phase chưa tồn tại: báo cho người dùng và dừng. Việc viết spec mới thuộc về người duyệt.

## 2. Đọc bối cảnh (theo thứ tự)

1. `CLAUDE.md`
2. `specs/mission.md`, `specs/tech-stack.md`, `specs/roadmap.md`
3. `requirements.md`, `plan.md`, `validation.md` của phase
4. Mục của phase ngay trước trong `CHANGELOG.md` (số liệu đo được, quyết định mới)
5. Các file trong `contracts/` mà requirements nhắc tới

Đọc đủ trước khi nhận xét. Nhiều "chỗ mơ hồ" thực ra đã được trả lời ở tech-stack hoặc phase trước.

## 3. Kiểm tra điều kiện tiên quyết

- Các phase mà phase này phụ thuộc (bảng Tổng quan trong `roadmap.md`) đã hoàn thành chưa?
- Group 0 (thay đổi contract của người duyệt) đã merge chưa? Kiểm tra bằng cách tìm các schema/enum/endpoint mà requirements yêu cầu thêm trong `contracts/`.
- Có đề xuất contract nào đang chờ trong `specs/*/contract-proposals/` liên quan tới phase này không?

## 4. Kiểm tra độ phủ (traceability)

Với mỗi requirement có thể kiểm chứng trong `requirements.md` (mỗi quy tắc trong Behaviour, mỗi ràng buộc DB, mỗi quyết định có hệ quả kỹ thuật), tìm:
- task tương ứng trong `plan.md`,
- mục tương ứng trong `validation.md`.

Chỉ báo những dòng **thiếu** một trong hai. Không liệt kê những dòng đã đủ.

## 5. Báo cáo theo đúng mẫu sau, rồi dừng

```markdown
# Kickoff: Phase NN — <tên>

## Tóm tắt (tối đa 5 dòng)
<phase này giao được gì, demo cuối phase là gì>

## Điều kiện tiên quyết
- [x|✗] <phase phụ thuộc> ...
- [x|✗] Group 0 đã merge: <bằng chứng: schema X có trong contracts/...>

## Phân công
| Group | Agent | Thư mục được sửa | Phụ thuộc |

## Chỗ mơ hồ hoặc mâu thuẫn (tối đa 5, quan trọng nhất trước)
1. <mô tả> — trích: <file:mục> — Các phương án: A) ... B) ... — Khuyến nghị: ... vì ...

## Lỗ hổng độ phủ
| Requirement | Thiếu trong plan? | Thiếu trong validation? |

## Rủi ro lớn nhất của phase
<1–3 rủi ro kỹ thuật, cách phát hiện sớm>
```

**Không** viết code, **không** sửa spec ở bước này.

## 6. Hỏi người dùng bằng `AskUserQuestion`

Sau khi báo cáo, hỏi các chỗ mơ hồ bằng công cụ `AskUserQuestion` (theo quy tắc "Cách hỏi người dùng" trong `CLAUDE.md`):

- **Lượt 1:** tối đa 4 câu quan trọng nhất trong danh sách chỗ mơ hồ. Nếu có câu thứ 5, hỏi ở lượt 2.
- Mỗi câu: `header` là chủ đề ngắn (ví dụ "Model", "Fixture", "Tiền tệ"); `question` nêu vấn đề kèm nguồn (ví dụ "requirements.md mục Decisions chưa chốt phiên bản YOLO. Dùng bản nào?"); 2–4 lựa chọn, khuyến nghị đứng đầu có " (Khuyến nghị)", mô tả mỗi lựa chọn nói rõ hệ quả với phase này và phase sau.
- Lỗ hổng độ phủ và điều kiện tiên quyết **không** hỏi bằng công cụ; chúng đã nằm trong báo cáo để người dùng tự xử lý.
- Nếu điều kiện tiên quyết chưa thỏa (phase phụ thuộc chưa xong, Group 0 chưa merge), hỏi thêm một câu: "Tiếp tục kickoff để chuẩn bị trước" hay "Dừng, quay lại sau khi điều kiện thỏa".

Ví dụ một câu hỏi:

```text
header:   Fixture
question: requirements.md Phase 0 chưa chốt nguồn 5 ảnh fixture. Dùng nguồn nào?
options:
  - label: COCO val2017 (Khuyến nghị)
    description: Tải trực tiếp bằng script, CI chạy được; cần ghi giấy phép từng ảnh.
  - label: KITTI
    description: Cùng miền với dữ liệu đánh giá, nhưng cần đăng nhập để tải nên CI không tự tải được.
```

Nếu công cụ không khả dụng hoặc trả về rỗng: hỏi bằng văn bản theo phương án dự phòng trong `CLAUDE.md` và dừng. Không tự chọn thay người dùng.

## 7. Sau khi người dùng trả lời

- Đề xuất thay đổi spec dưới dạng diff cho từng file (requirements, plan, validation), mỗi thay đổi ghi rõ nó đến từ câu trả lời nào.
- Hỏi bằng `AskUserQuestion` một câu: "Áp dụng toàn bộ diff (Khuyến nghị)" / "Chỉ áp dụng một số file" / "Không áp dụng, mình tự sửa". Nếu người dùng chọn một số file, hỏi tiếp bằng `multiSelect` danh sách file.
- Chỉ sửa file spec theo đúng lựa chọn. Khi sửa, chỉ sửa đúng những chỗ đã thống nhất.
- Nếu câu trả lời đòi thay đổi contract: không sửa `contracts/`; ghi chú rằng Group 0 cần cập nhật, hoặc dùng skill `contract-proposal`.
