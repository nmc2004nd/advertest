---
name: phase-close
description: Đóng một group hoặc một phase của AdverTest sau khi đã review và người duyệt đồng ý merge - cập nhật CHANGELOG.md, đánh dấu tiến độ trong plan.md và roadmap.md, kiểm tra definition of done, rồi replan (đề xuất cập nhật spec của các phase sau dựa trên những gì vừa học được). Dùng skill này khi người dùng nói đóng group, đóng phase, cập nhật changelog, đánh dấu hoàn thành, "xong phase", "chuẩn bị merge", hoặc hỏi spec nào cần sửa sau một phase, kể cả khi không nhắc tên skill.
---

# Đóng group hoặc phase

Khi cần người dùng xác nhận hay chọn, dùng `AskUserQuestion` theo quy tắc trong `CLAUDE.md`; nếu công cụ không khả dụng hoặc trả về rỗng, hỏi bằng văn bản và dừng, **không** tự coi là đã xác nhận.

Skill này chỉ được sửa: `CHANGELOG.md` và `changelog/archive/`, các ô đánh dấu `[ ]`/`[x]` trong `plan.md`, `validation.md`, `roadmap.md`.

Đọc theo bảng "Đọc gì" trong `CLAUDE.md`. Nguồn chính là handoff `.claude/handoff/phaseNN-gG-implement.md` và `phaseNN-gG-review.md` (số liệu, kết quả validation, tồn đọng, quyết định); không dựa vào lịch sử chat. Chèn mục mới vào `CHANGELOG.md` bằng `Edit` ngay dưới tiêu đề phase, không Read nguyên file. Nó không sửa code, contract hay nội dung spec. Đề xuất thay đổi spec luôn ở dạng diff chờ duyệt.

Mặc định **đóng một lần cho cả phase** (chế độ 2 rồi chế độ 3), sau khi `phase-review` cả phase báo sẵn sàng merge. Chế độ 1 chỉ dùng khi người dùng muốn merge riêng một group trước (thường là group rủi ro đã review riêng). Khi đóng cả phase, các group chưa có mục changelog được ghi theo mẫu của chế độ 1 bước 2 (gom từ các handoff implement) trước khi viết tổng kết.

## Chế độ 1: Đóng một group (tùy chọn)

Điều kiện: người dùng đã xác nhận nhánh được review (skill `phase-review`) và đồng ý merge. Nếu prompt chưa nói rõ điều này, hỏi bằng `AskUserQuestion`: "Đã review và đồng ý merge" / "Chưa review, dừng lại" (khuyến nghị chạy `phase-review` trước).

1. Đọc `git log --oneline main..<nhánh>`, handoff implement và review của group (hoặc báo cáo người dùng cung cấp).
2. Thêm mục vào `CHANGELOG.md` theo mẫu:

   ```markdown
   ## Phase NN — Group G (<agent>) — YYYY-MM-DD
   ### Thêm
   - ...
   ### Thay đổi
   - ...
   ### Contract
   - (nếu Group 0) thay đổi schema/enum/endpoint, schema_version mới
   ### Quyết định
   - quyết định kỹ thuật mới và file spec đã ghi nhận nó
   ### Số liệu đo được
   - (chỉ số liệu người dùng hoặc báo cáo agent cung cấp, không tự bịa)
   ### Tồn đọng
   - ...
   ```

3. Đánh dấu `[x]` cho các task của group trong `plan.md`.
4. Đánh dấu `[x]` trong `validation.md` **chỉ** với mục Automated Tests có bằng chứng pass (báo cáo của agent hoặc bạn tự chạy lại). Không bao giờ tự đánh dấu Manual Checks.
5. Nếu các task tương ứng trong `roadmap.md` đã đủ, đánh dấu chúng; **chưa** đánh dấu cả phase.
6. Nhắc người dùng lệnh merge phù hợp (ví dụ `git merge --no-ff phaseNN-<agent>`), không tự merge trừ khi được yêu cầu.
7. Xóa handoff của group đã đóng (`rm .claude/handoff/phaseNN-gG-*`) sau khi nội dung đã vào `CHANGELOG.md`. Kết thúc bằng: "Gõ `/clear` trước group tiếp theo."

## Chế độ 2: Đóng cả phase

1. Kiểm tra mọi task của phase đã xong: `grep -c '\[ \]' plan.md` bằng 0 (`phase-implement` đánh dấu khi xong group). Đọc `phaseNN-review.md` (hoặc các `phaseNN-gG-review.md`): mọi review phải có kết luận SẴN SÀNG MERGE. Ghi mục changelog cho các group chưa có mục (mẫu ở chế độ 1 bước 2).
2. Đi qua **Definition of Done** trong `validation.md` từng mục:
   - mục tự động: xác minh bằng bằng chứng hoặc chạy `make check`;
   - Manual Checks và các mục cần người duyệt: hỏi bằng `AskUserQuestion` với `multiSelect: true`, mỗi câu gom tối đa 4 mục kiểm tra liên quan (ví dụ "Kiểm tra trên điện thoại"), `question` là "Những mục nào đã làm và đạt?". Mục không được chọn coi là **chưa đạt**. Cần nhiều câu thì dùng nhiều lượt gọi (tối đa 4 câu mỗi lượt).
   - Với mục yêu cầu **ghi số liệu** (baseline, thời gian, batch size...): công cụ không phù hợp cho số liệu tự do, nên sau khi hỏi xác nhận, yêu cầu người dùng gõ số liệu bằng văn bản theo danh sách bạn liệt kê. Không tự điền số liệu.
3. Chỉ khi mọi mục đã thỏa: thêm mục tổng kết phase vào `CHANGELOG.md` (tiêu đề `### Phase NN — Tổng kết (phase-close) — YYYY-MM-DD`, mục đầu tiên dưới `## Phase NN`, vì kickoff phase sau chỉ đọc mục này), đánh dấu phase hoàn thành trong `roadmap.md`.
   - **Lưu trữ:** chuyển nguyên văn khối `## Phase` của phase đã đóng **trước** phase này ra `changelog/archive/phase-MM.md` (từ dòng tiêu đề tới trước `---` ngăn cách khối kế tiếp), xóa khối đó khỏi `CHANGELOG.md`, thêm một dòng vào đầu danh sách "Lưu trữ". Kiểm tra không mất dòng: số dòng không trống của khối cũ bằng số dòng không trống của file lưu trữ. `CHANGELOG.md` chỉ giữ phase vừa đóng và phase đang làm.
   - Số liệu còn nợ của một phase đã lưu trữ (ví dụ Phase 6, 7 theo `roadmap.md`) thì ghi vào file `changelog/archive/phase-MM.md` tương ứng.
4. Nếu còn mục chưa thỏa: liệt kê và dừng, không đánh dấu phase.

## Chế độ 3: Replan (luôn chạy sau chế độ 2)

Mục đích: spec là nguồn sự thật sống; những gì học được ở phase này phải chảy vào các phase sau trước khi ai đó bắt đầu làm chúng.

1. Đọc mục tổng kết CHANGELOG của phase vừa đóng, mục `Open Questions` của `requirements.md`, mục roadmap của **hai phase kế tiếp**, và spec của chúng (nếu đã có): `Scope`, `Decisions`, `Context` và các mục nhắc tới số liệu hoặc contract vừa đổi (`grep -n` theo từ khóa trước khi đọc).
2. Tìm những chỗ cần cập nhật, ví dụ:
   - số liệu đo được (baseline, thời gian mỗi ảnh, batch size, VRAM) làm thay đổi giá trị mặc định hay giả định;
   - quyết định mới làm sai một giả định của phase sau;
   - contract đã đổi mà spec phase sau vẫn mô tả bản cũ;
   - việc bị đẩy sang backlog cần xuất hiện trong roadmap.
3. Báo cáo:

   ```markdown
   # Replan sau Phase NN

   ## Câu hỏi mở đã được trả lời
   | Câu hỏi | Câu trả lời | Ghi vào đâu |

   ## Đề xuất cập nhật spec
   ### <file>
   <diff>
   Lý do: ...

   ## Rủi ro mới cho các phase sau
   ```

4. Hỏi bằng `AskUserQuestion`: "Áp dụng toàn bộ đề xuất" / "Chọn từng file" / "Không áp dụng". Nếu chọn từng file, hỏi tiếp bằng `multiSelect` danh sách file (tối đa 4 mỗi câu). Chỉ áp dụng đúng phần được chọn.
5. Với mỗi câu hỏi mở đã có câu trả lời nhưng chưa được ghi ở đâu, đề xuất vị trí ghi trong spec; không để câu trả lời chỉ nằm trong chat.
6. Xóa handoff của phase (`rm .claude/handoff/phaseNN-*`). Kết thúc bằng: "Gõ `/clear` rồi chạy `phase-kickoff` cho phase tiếp theo."
