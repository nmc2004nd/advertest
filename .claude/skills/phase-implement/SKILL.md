---
name: phase-implement
description: Thực hiện một group trong plan.md của một phase AdverTest với vai trò một agent cụ thể (ml-core, attack, backend, worker, frontend...) - lập kế hoạch thực thi, chờ duyệt, code theo từng task, chạy test nghiệm thu, commit, và báo cáo bằng chứng theo validation.md. Dùng skill này bất cứ khi nào người dùng yêu cầu implement, code, làm, triển khai một group, task hoặc phần việc của một phase, hoặc giao việc cho một agent theo spec, kể cả khi họ chỉ nói "làm group 3 phase 1".
---

# Thực hiện một group của phase

Bạn là **một** agent với phạm vi hẹp. Giá trị của bạn nằm ở chỗ làm đúng phần được giao, không mở rộng, và để lại bằng chứng rõ ràng. Mọi quyết định mà spec chưa nói thuộc về người duyệt, không thuộc về bạn.

## 0. Xác nhận nhiệm vụ

Cần đủ ba thông tin: **phase**, **group** (hoặc danh sách task), **tên agent**. Thiếu thì hỏi.

Từ phần đầu `plan.md` của phase và bảng quyền sở hữu trong `CLAUDE.md`, xác định **danh sách thư mục bạn được sửa**. Nói lại danh sách này cho người dùng ở đầu báo cáo kế hoạch.

## 1. Kiểm tra trước khi làm

- Đọc `CLAUDE.md`, `specs/mission.md`, `specs/tech-stack.md`, và toàn bộ spec của phase.
- Group 0 và các group mà group này phụ thuộc đã merge chưa? Chưa thì dừng và báo.
- `git status` sạch, đang ở đúng nhánh hoặc worktree (quy ước tên nhánh: `phaseNN-<agent>`). Không đúng thì dừng và báo.

## 2. Lập kế hoạch thực thi (chưa sửa file nào)

Báo cáo theo mẫu:

```markdown
# Kế hoạch: Phase NN — Group G — agent <tên>

Thư mục được sửa: <danh sách>

## Các bước
1. <task trong plan.md> → file sẽ tạo/sửa → cách kiểm tra ngay sau bước này
...

## Test nghiệm thu sẽ pass sau group này
- tests/acceptance/phase_NN/<file>::<test>

## Rủi ro và cách phát hiện sớm
## Điểm cần người duyệt quyết định (nếu có)
```

Dừng chờ duyệt. Chỉ bỏ qua bước chờ khi người dùng đã nói rõ "kế hoạch đã duyệt" hoặc "làm luôn".

## 3. Implement

1. **Chạy test nghiệm thu liên quan trước**, ghi lại test nào đang fail. Đây là mốc để chứng minh công việc của bạn làm chúng pass.
2. Làm **từng task một** theo thứ tự đã duyệt. Sau mỗi task:
   - chạy test unit và test nghiệm thu liên quan;
   - commit với message `phaseNN(<agent>): <task ngắn gọn>`.
3. Viết test unit cho code của bạn trong thư mục của bạn khi logic không tầm thường.

### Luật cứng (không có ngoại lệ)

- **Không sửa** `specs/`, `contracts/`, `tests/acceptance/`, và mọi thư mục ngoài danh sách được sửa. Lý do: đó là hợp đồng giữa các agent và là tiêu chí nghiệm thu; sửa chúng là tự đổi luật chơi.
- **Không làm yếu test**: không thêm `skip`, `xfail`, `.only`, không nới sai số, không xóa assertion, không bắt ngoại lệ để nuốt lỗi. Test nghiệm thu fail nghĩa là code chưa đúng, hoặc spec có vấn đề; cả hai đều cần người duyệt biết.
- **Không thêm dependency** ngoài `tech-stack.md`.
- **Không mở rộng phạm vi** ngoài `requirements.md`, kể cả khi thấy "tiện thì làm luôn". Ghi ý tưởng vào báo cáo cuối.
- **Không dùng `# type: ignore`, `# noqa`, `eslint-disable`** để vượt qua kiểm tra, trừ khi giải thích lý do cụ thể trong báo cáo.

### Khi nào dừng lại hỏi

- Spec không nói rõ và lựa chọn có ảnh hưởng tới thiết kế, dữ liệu hay hành vi người dùng thấy.
- Cần đổi contract → dùng skill `contract-proposal`, rồi dừng.
- Test nghiệm thu fail vì lý do nằm ngoài phạm vi group của bạn.
- Sửa cùng một lỗi 3 lần chưa được → dừng sửa, viết báo cáo chẩn đoán: triệu chứng, bằng chứng (log, giá trị in ra), giả thuyết, 2 hướng xử lý kèm rủi ro.
- Plan có task ghi "dừng và báo" (ví dụ giới hạn thời gian thử phương án) và điều kiện đã xảy ra.

## 4. Báo cáo kết quả

Chạy mọi mục Automated Tests trong `validation.md` thuộc phạm vi group, cộng `make check`. Báo cáo theo mẫu:

```markdown
# Kết quả: Phase NN — Group G — agent <tên>

## Validation
| Mục validation | Lệnh | Kết quả | Ghi chú |

## Test nghiệm thu: trước → sau
<số fail trước, số fail sau, test nào còn fail và vì sao>

## File đã thay đổi
<git diff --stat main>

## Lệch so với kế hoạch
<điều gì khác so với kế hoạch đã duyệt và lý do>

## Việc cho người duyệt
- Manual check cần làm: ...
- Ý tưởng ngoài phạm vi (không làm): ...
- Quyết định nên ghi vào spec: ...
```

Không tuyên bố "xong" nếu còn mục validation fail. Nêu thẳng mục nào fail.
