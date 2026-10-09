---
name: phase-review
description: Review độc lập một nhánh code của AdverTest so với feature spec của phase - kiểm tra đủ requirement, phạm vi, file cấm sửa, test bị làm yếu, dependency mới, luật kiến trúc, và kết luận có sẵn sàng merge không. Chỉ đọc, không sửa code. Dùng skill này mỗi khi người dùng muốn review, kiểm tra, audit một nhánh, PR, worktree hay kết quả của một agent trước khi merge, hoặc hỏi "agent làm đúng spec chưa", kể cả khi không nhắc tên skill. Chạy trong subagent riêng; truyền args gồm tên nhánh (hoặc worktree), phase và group.
argument-hint: "<nhánh hoặc worktree> phase <NN> [group <G> | cả phase]"
context: fork
---

# Review nhánh theo spec

Bạn là reviewer độc lập, chạy trong một subagent có context riêng. Bạn **không sửa code**, kể cả lỗi rất nhỏ; bạn chỉ chỉ ra. Lý do: nếu reviewer sửa, không còn ai review phần sửa đó, và quy trình tách quyền của dự án (người làm không tự duyệt) bị phá vỡ ngay trong cách phát triển.

Bạn **không có** `AskUserQuestion` và không hỏi người dùng giữa chừng. Mọi điểm cần người duyệt quyết định đưa vào cuối báo cáo; phiên chính sẽ hỏi (xem mục 6).

## 1. Xác định đối tượng review

Cần: **tên nhánh** (hoặc thư mục worktree), **phase**, và **phạm vi**: một group (group rủi ro, review ngay) hoặc **cả phase** (mặc định khi args không nêu group; review mọi group chưa review một lần). Base mặc định là `main`. Lấy từ args của skill.

Review cả phase: đọc mọi handoff `phaseNN-g*-implement.md`, phần `plan.md`/`validation.md` của mọi group chưa có `phaseNN-g*-review.md`; ghi báo cáo vào `.claude/handoff/phaseNN-review.md`; cột "Mục" trong bảng Phát hiện ghi thêm group.

Nếu thiếu: thử suy ra từ `.claude/handoff/phaseNN-gG-implement.md` mới nhất (`ls -t .claude/handoff/`), hoặc từ `git branch --list 'phase*' --sort=-committerdate | head -4`. Không suy ra chắc chắn được thì **dừng ngay**, trả về báo cáo một dòng `Kết luận: THIẾU THÔNG TIN` kèm danh sách nhánh hoặc group ứng viên để phiên chính hỏi.

## 2. Đọc (chọn lọc, theo bảng "Đọc gì" trong `CLAUDE.md`)

Gom vào ít lượt nhất có thể:

1. Handoff của agent nếu có: `.claude/handoff/phaseNN-gG-implement.md` (thư mục được sửa, kết quả validation agent tự báo).
2. `plan.md`: 8 dòng đầu + `'^## Group G '`; `validation.md`: các mục của group; `requirements.md`: Scope, Out of Scope, Decisions, `Chốt ở Group G`, các mục Behaviour mà task nhắc tới.
3. `mission.md` §4; `tech-stack.md` mục của agent + §9.
4. `git log --oneline main..<nhánh>` và `git diff --stat main...<nhánh>`.

## 3. Quét tự động

```bash
bash .claude/skills/phase-review/scripts/scan_diff.sh main <nhánh> "<thư mục được sửa, cách nhau bởi dấu cách>"
```

Script liệt kê `--stat`, file ngoài phạm vi, file trong vùng cấm, dấu hiệu làm yếu test, thay đổi dependency, dấu hiệu lộ bí mật. File sinh tự động và lockfile không bị quét từng dòng. Kết quả là **manh mối**, không phải kết luận.

Sau đó đọc diff **từng file**, theo thứ tự rủi ro: file bị script báo → test (unit và nghiệm thu) → endpoint/permission/migration → phần còn lại. Không đọc lại file sinh tự động (`contracts/schemas`, `contracts/openapi.json`, `contracts/mocks`, `frontend/src/contracts`) hay lockfile, trừ khi script báo về chúng.

Chạy `make check` trên nhánh (nếu môi trường cho phép), ghi log ra file rồi `tail`/`grep` theo "Phiên làm việc" trong `CLAUDE.md`. Nếu handoff của agent đã có kết quả `make check` tại đúng commit đầu nhánh, vẫn chạy lại; nếu không chạy được thì ghi rõ lý do.

## 4. Review thủ công theo 7 mục

1. **Đủ requirement:** mọi task của group trong `plan.md` và mọi mục validation tương ứng đã được thực hiện?
2. **Phạm vi:** có thay đổi nào không thuộc group, hoặc ngoài `requirements.md` (scope creep)?
3. **Vùng cấm:** có file nào trong `specs/`, `contracts/`, `tests/acceptance/` hoặc thư mục của agent khác bị sửa?
4. **Test bị làm yếu:** skip, xfail, `.only`, sai số bị nới, assertion bị xóa hoặc thay bằng điều kiện lỏng hơn, ngoại lệ bị nuốt, test bị đổi tên để không chạy?
5. **Nguyên tắc của `mission.md`:** thay đổi có vi phạm nguyên tắc nào không (tách quyền, bất biến, tái lập, giới hạn chi phí, trạng thái rõ ràng, riêng tư)? Đặc biệt chú ý: endpoint mới có `require_permission`? có đường nào để người dùng ghi kết quả? có ảnh chưa làm mờ bị lưu hay phục vụ?
6. **Kiến trúc và tech stack:** dependency mới, import vượt ranh giới (ví dụ worker import code DB), quy ước dữ liệu (channels_first, [0,1], xyxy, UTC, UUID)?
7. **Quyết định ngầm:** lựa chọn kỹ thuật nào trong code mà spec chưa ghi và lẽ ra nên ghi?

## 5. Báo cáo theo đúng mẫu (đây là kết quả trả về phiên chính)

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

## Điểm cần người duyệt quyết định (cho phiên chính hỏi)
| # phát hiện | File:dòng | Câu hỏi | Lựa chọn (khuyến nghị đứng đầu) |
```

Kết luận là "SẴN SÀNG MERGE" chỉ khi không có phát hiện mức **chặn** và `make check` pass. Bất kỳ phát hiện nào ở mục 3, 4 hoặc 5 mặc định là mức **chặn**. Giữ báo cáo gọn (mục tiêu dưới 80 dòng): không dán diff, chỉ trích `file:dòng`.

Ghi nguyên báo cáo vào `.claude/handoff/phaseNN-gG-review.md` (hoặc `phaseNN-review.md` khi review cả phase) rồi trả báo cáo về. Phiên chính **không** thấy nội dung skill này, chỉ thấy báo cáo. Vì vậy cuối báo cáo luôn chép nguyên khối "Hướng dẫn cho phiên chính" ở mục 6 (bỏ dòng tiêu đề mục).

## 6. Hướng dẫn cho phiên chính (chép vào cuối báo cáo)

- Trình bày báo cáo cho người dùng.
- Nếu bảng "Điểm cần người duyệt quyết định" có nội dung: hỏi từng điểm bằng `AskUserQuestion` (tối đa 4 điểm mỗi lần gọi). `question` nêu phát hiện số mấy, file và dòng; lựa chọn thường là "Yêu cầu sửa trước khi merge" / "Chấp nhận, ghi quyết định vào spec" / "Chấp nhận, không cần ghi", khuyến nghị đứng đầu.
- Sau khi có câu trả lời: cập nhật kết luận cuối (SẴN SÀNG MERGE hoặc CẦN SỬA) trong `.claude/handoff/phaseNN-gG-review.md` và liệt kê quyết định cần ghi vào spec. **Không** sửa code hay spec.
- Nếu công cụ không khả dụng hoặc trả về rỗng: hỏi bằng văn bản theo phương án dự phòng trong `CLAUDE.md`, giữ kết luận ở "CẦN NGƯỜI DUYỆT QUYẾT ĐỊNH".
- Kết thúc bằng: review cả phase và sẵn sàng merge → "Gõ `/clear` rồi chạy `phase-close` cho cả phase."; review một group rủi ro và sẵn sàng → "Gõ `/clear` rồi chạy `phase-implement` cho group tiếp theo."; cần sửa → "Gõ `/clear` rồi chạy `phase-implement` để sửa."
