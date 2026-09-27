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
1. <mô tả> — trích: <file:mục> — Câu hỏi: <câu hỏi cụ thể, có lựa chọn nếu được>

## Lỗ hổng độ phủ
| Requirement | Thiếu trong plan? | Thiếu trong validation? |

## Rủi ro lớn nhất của phase
<1–3 rủi ro kỹ thuật, cách phát hiện sớm>
```

Sau báo cáo, hỏi người dùng trả lời các câu hỏi. **Không** viết code, **không** sửa spec.

## 6. Sau khi người dùng trả lời

- Đề xuất thay đổi spec dưới dạng diff cho từng file (requirements, plan, validation), để người dùng áp dụng hoặc cho phép bạn áp dụng.
- Chỉ sửa file spec khi người dùng nói rõ cho phép. Khi sửa, chỉ sửa đúng những chỗ đã thống nhất.
- Nếu câu trả lời đòi thay đổi contract: không sửa `contracts/`; ghi chú rằng Group 0 cần cập nhật, hoặc dùng skill `contract-proposal`.
