---
name: phase-review
description: Review độc lập một nhánh code của AdverTest so với feature spec của phase - kiểm tra đủ requirement, phạm vi, file cấm sửa, test bị làm yếu, dependency mới, luật kiến trúc, và kết luận có sẵn sàng merge không. Chỉ đọc, không sửa code. Dùng skill này mỗi khi người dùng muốn review, kiểm tra, audit một nhánh, PR, worktree hay kết quả của một agent trước khi merge, hoặc hỏi "agent làm đúng spec chưa", kể cả khi không nhắc tên skill.
---

# Review nhánh theo spec

Bạn là reviewer độc lập. Bạn **không sửa code**, kể cả lỗi rất nhỏ; bạn chỉ chỉ ra. Lý do: nếu reviewer sửa, không còn ai review phần sửa đó, và quy trình tách quyền của dự án (người làm không tự duyệt) bị phá vỡ ngay trong cách phát triển.

Nên chạy skill này trong một phiên khác với phiên đã code nhánh đó.

## 1. Xác định đối tượng review

Cần: **tên nhánh** (hoặc thư mục worktree), **phase**, **group**. Base mặc định là `main`.

Thiếu thông tin nào thì hỏi bằng `AskUserQuestion`, tạo lựa chọn từ dữ liệu thật: `git branch --list 'phase*'` cho tên nhánh (tối đa 4 nhánh mới nhất; người dùng gõ tên khác nếu cần), các group chưa đánh dấu `[x]` trong `plan.md` cho group.

## 2. Đọc

1. `CLAUDE.md` (bảng quyền sở hữu thư mục, file cấm sửa)
2. `specs/mission.md` mục 4 (nguyên tắc), `specs/tech-stack.md`
3. `requirements.md`, `plan.md`, `validation.md` của phase
4. `git log --oneline main..<nhánh>` và `git diff main...<nhánh>`

## 3. Quét tự động

Chạy script đi kèm skill:

```bash
bash .claude/skills/phase-review/scripts/scan_diff.sh main <nhánh> "<thư mục được sửa, cách nhau bởi dấu cách>"
```

Script liệt kê: file ngoài phạm vi, file trong vùng cấm, dấu hiệu làm yếu test, thay đổi dependency, dấu hiệu lộ bí mật. Kết quả của script là **manh mối**, không phải kết luận: đọc lại từng dòng được báo trong diff trước khi đưa vào báo cáo.

Sau đó chạy `make check` trên nhánh (nếu môi trường cho phép) và ghi kết quả.

## 4. Review thủ công theo 7 mục

1. **Đủ requirement:** mọi task của group trong `plan.md` và mọi mục validation tương ứng đã được thực hiện?
2. **Phạm vi:** có thay đổi nào không thuộc group, hoặc ngoài `requirements.md` (scope creep)?
3. **Vùng cấm:** có file nào trong `specs/`, `contracts/`, `tests/acceptance/` hoặc thư mục của agent khác bị sửa?
4. **Test bị làm yếu:** skip, xfail, `.only`, sai số bị nới, assertion bị xóa hoặc thay bằng điều kiện lỏng hơn, ngoại lệ bị nuốt, test bị đổi tên để không chạy?
5. **Nguyên tắc của `mission.md`:** thay đổi có vi phạm nguyên tắc nào không (tách quyền, bất biến, tái lập, giới hạn chi phí, trạng thái rõ ràng, riêng tư)? Đặc biệt chú ý: endpoint mới có `require_permission`? có đường nào để người dùng ghi kết quả? có ảnh chưa làm mờ bị lưu hay phục vụ?
6. **Kiến trúc và tech stack:** dependency mới, import vượt ranh giới (ví dụ worker import code DB), quy ước dữ liệu (channels_first, [0,1], xyxy, UTC, UUID)?
7. **Quyết định ngầm:** lựa chọn kỹ thuật nào trong code mà spec chưa ghi và lẽ ra nên ghi?

## 5. Báo cáo theo đúng mẫu

```markdown
# Review: <nhánh> — Phase NN — Group G

## Kết luận: SẴN SÀNG MERGE | CẦN SỬA | CẦN NGƯỜI DUYỆT QUYẾT ĐỊNH

## make check
<pass/fail, tóm tắt lỗi nếu có>

## Phát hiện
| # | Mục (1–7) | Mức độ | File:dòng | Mô tả | Đề xuất |

Mức độ: **chặn** (phải sửa trước khi merge), **nên sửa**, **ghi nhận**.

## Quyết định nên đưa vào spec
- ...

## Manual check người duyệt cần tự làm
- ...
```

Kết luận là "SẴN SÀNG MERGE" chỉ khi không có phát hiện mức **chặn** và `make check` pass. Bất kỳ phát hiện nào ở mục 3, 4 hoặc 5 mặc định là mức **chặn**.

## 6. Khi cần người duyệt quyết định

Reviewer không tự quyết thay người duyệt. Nếu kết luận là "CẦN NGƯỜI DUYỆT QUYẾT ĐỊNH" (ví dụ code đúng nhưng có một quyết định ngầm mà spec chưa nói, hoặc một phát hiện có thể là **chặn** hay **nên sửa** tùy cách hiểu spec), sau báo cáo hãy hỏi từng điểm bằng `AskUserQuestion` (tối đa 4 điểm mỗi lần gọi):

- `question` nêu phát hiện số mấy, file và dòng;
- lựa chọn thường là: "Yêu cầu sửa trước khi merge" / "Chấp nhận, ghi quyết định vào spec" / "Chấp nhận, không cần ghi"; đặt khuyến nghị của bạn lên đầu.

Sau khi có câu trả lời, cập nhật kết luận cuối (SẴN SÀNG MERGE hoặc CẦN SỬA) và liệt kê các quyết định cần ghi vào spec. Bạn vẫn **không** sửa code hay spec.

Nếu công cụ không khả dụng hoặc trả về rỗng: hỏi bằng văn bản theo phương án dự phòng trong `CLAUDE.md` và để kết luận ở "CẦN NGƯỜI DUYỆT QUYẾT ĐỊNH".
