---
name: phase-implement
description: Thực hiện một group trong plan.md của một phase AdverTest với vai trò một agent cụ thể (ml-core, attack, backend, worker, frontend...) - lập kế hoạch thực thi, chờ duyệt, code theo từng task, chạy test nghiệm thu, commit, và báo cáo bằng chứng theo validation.md. Dùng skill này bất cứ khi nào người dùng yêu cầu implement, code, làm, triển khai một group, task hoặc phần việc của một phase, hoặc giao việc cho một agent theo spec, kể cả khi họ chỉ nói "làm group 3 phase 1".
---

# Thực hiện một group của phase

## Tương thích Codex

- Khi tài liệu dưới đây nói `AskUserQuestion`, dùng công cụ hỏi lựa chọn của Codex nếu khả dụng; nếu không, hỏi trực tiếp một câu ngắn rồi dừng. Bỏ qua tên trường và giới hạn riêng của công cụ Claude; luôn theo schema công cụ Codex hiện tại.
- Không tự commit, push hoặc merge. Các chỉ dẫn commit bên dưới chỉ áp dụng khi người dùng yêu cầu rõ việc commit.
- Đọc thêm `specs/design.md` cho mọi phần việc liên quan giao diện.

Bạn là **một** agent với phạm vi hẹp. Giá trị của bạn nằm ở chỗ làm đúng phần được giao, không mở rộng, và để lại bằng chứng rõ ràng. Mọi quyết định mà spec chưa nói thuộc về người duyệt, không thuộc về bạn.

## 0. Xác nhận nhiệm vụ

Cần đủ ba thông tin: **phase**, **group** (hoặc danh sách task), **tên agent**. Thiếu thông tin nào thì hỏi bằng `AskUserQuestion`, dùng dữ liệu trong spec để tạo lựa chọn (ví dụ liệt kê các group chưa đánh dấu `[x]` trong `plan.md`, các agent ghi ở đầu `plan.md`).

Từ phần đầu `plan.md` của phase và bảng quyền sở hữu trong `CLAUDE.md`, xác định **danh sách thư mục bạn được sửa**. Nói lại danh sách này cho người dùng ở đầu báo cáo kế hoạch.

## 1. Kiểm tra trước khi làm

- Đọc `CLAUDE.md`, `specs/mission.md`, `specs/tech-stack.md`, và toàn bộ spec của phase.
- Group 0 và các group mà group này phụ thuộc đã merge chưa?
- `git status` sạch, đang ở đúng nhánh hoặc worktree (quy ước tên nhánh: `phaseNN-<agent>`)?

Nếu một điều kiện không thỏa: nêu rõ bằng văn bản điều kiện nào và bằng chứng, rồi hỏi bằng `AskUserQuestion` với các lựa chọn phù hợp, ví dụ "Dừng, chờ điều kiện thỏa (Khuyến nghị)" / "Chỉ làm các task không phụ thuộc" (liệt kê task trong mô tả). Không tự tiếp tục.

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

Sau khi trình bày kế hoạch bằng văn bản, hỏi duyệt bằng `AskUserQuestion`:

- Nếu mục "Điểm cần người duyệt quyết định" có nội dung: hỏi các điểm đó trước (tối đa 3 câu), rồi thêm câu duyệt kế hoạch làm câu cuối trong cùng lần gọi.
- Câu duyệt kế hoạch: `header` "Kế hoạch"; lựa chọn "Duyệt, làm đi" / "Duyệt nhưng sửa một số điểm" (người dùng ghi điểm cần sửa trong câu trả lời tự do) / "Dừng lại".

Chỉ bỏ qua bước hỏi khi người dùng đã nói rõ "kế hoạch đã duyệt" hoặc "làm luôn" trong prompt.

## 3. Implement

1. **Chạy test nghiệm thu liên quan trước**, ghi lại test nào đang fail. Đây là mốc để chứng minh công việc của bạn làm chúng pass.
2. Làm **từng task một** theo thứ tự đã duyệt. Sau mỗi task:
   - chạy test unit và test nghiệm thu liên quan;
   - nếu người dùng đã yêu cầu commit, commit với message `phaseNN(<agent>): <task ngắn gọn>`.
3. Viết test unit cho code của bạn trong thư mục của bạn khi logic không tầm thường.

### Luật cứng (không có ngoại lệ)

- **Không sửa** `specs/`, `contracts/`, `tests/acceptance/`, và mọi thư mục ngoài danh sách được sửa. Lý do: đó là hợp đồng giữa các agent và là tiêu chí nghiệm thu; sửa chúng là tự đổi luật chơi.
- **Không làm yếu test**: không thêm `skip`, `xfail`, `.only`, không nới sai số, không xóa assertion, không bắt ngoại lệ để nuốt lỗi. Test nghiệm thu fail nghĩa là code chưa đúng, hoặc spec có vấn đề; cả hai đều cần người duyệt biết.
- **Không thêm dependency** ngoài `tech-stack.md`.
- **Không mở rộng phạm vi** ngoài `requirements.md`, kể cả khi thấy "tiện thì làm luôn". Ghi ý tưởng vào báo cáo cuối.
- **Không dùng `# type: ignore`, `# noqa`, `eslint-disable`** để vượt qua kiểm tra, trừ khi giải thích lý do cụ thể trong báo cáo.

### Khi nào dừng lại hỏi

Trong các tình huống dưới đây, dừng công việc, giữ phần đã chạy được (chỉ commit nếu người dùng đã yêu cầu), trình bày bối cảnh bằng văn bản, rồi hỏi bằng `AskUserQuestion` theo quy tắc trong `CLAUDE.md`:

| Tình huống | Nội dung câu hỏi |
|---|---|
| Spec không nói rõ và lựa chọn ảnh hưởng tới thiết kế, dữ liệu hay hành vi người dùng thấy | Các phương án cụ thể, khuyến nghị đứng đầu, mô tả hệ quả của từng phương án |
| Test nghiệm thu fail vì lý do ngoài phạm vi group | "Bỏ qua test này, ghi vào báo cáo (Khuyến nghị)" / "Dừng group chờ xử lý" / (nếu hợp lý) phương án khác |
| Sửa cùng một lỗi 3 lần chưa được | Trước tiên viết báo cáo chẩn đoán (triệu chứng, bằng chứng như log và giá trị in ra, giả thuyết); sau đó hỏi chọn giữa 2–3 hướng xử lý, mô tả kèm rủi ro |
| Plan có task ghi "dừng và báo" (ví dụ hết thời gian thử phương án) và điều kiện đã xảy ra | Các phương án mà spec nêu (ví dụ "Kích hoạt phương án dự phòng Faster R-CNN" / "Thử thêm 1 ngày") |

Riêng khi **cần đổi contract**: không hỏi bằng công cụ mà dùng skill `contract-proposal`, vì quyết định đó cần một văn bản đề xuất đầy đủ.

Nếu câu trả lời là một quyết định thiết kế, ghi nó vào mục "Quyết định nên ghi vào spec" trong báo cáo cuối để người duyệt đưa vào spec.

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
