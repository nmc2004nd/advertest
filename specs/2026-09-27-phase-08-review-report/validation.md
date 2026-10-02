# Validation: Phase 8 — Protocol, review và report

> Test trong `tests/acceptance/phase_08/` và `frontend/e2e/phase_08/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Đây là phase hiện thực hóa các nguyên tắc chống gian lận, nên mỗi luật có ít nhất một test cố tình vi phạm nó.

## Automated Tests

### Chung
- [ ] `make check` pass, bao gồm test nghiệm thu các phase trước (bảng ma trận quyền Phase 4 đã cập nhật `review.comment`).
- [ ] `make contracts` không tạo thay đổi; mock mới validate được.

### Protocol — `test_protocols.py`
- [ ] Reviewer tạo protocol → `active`, version 1, có `audit_log`.
- [ ] Engineer hoặc admin tạo protocol → `403`.
- [ ] Tạo version mới → bản ghi mới; nội dung version cũ không đổi (so sánh hash).
- [ ] Không có endpoint nào sửa nội dung một version đã tạo.
- [ ] Tiêu chí tham chiếu attack không có trong `required_attacks`, `min_breaking_point` với attack quét lưới, hoặc patch ở chế độ tìm ngưỡng → `422`.
- [ ] Protocol `retired` không chọn được khi tạo experiment mới; experiment cũ gắn protocol đó vẫn gửi duyệt được.

### Tuân thủ khi tạo — `test_compliance.py`
- [ ] Thiếu attack bắt buộc, sai `spec_sha256`, sai `mode` → `422` kèm mục `compliance` tương ứng không thỏa.
- [ ] Quét lưới thiếu một level bắt buộc → `422`; thêm level ngoài protocol → cho phép.
- [ ] Tìm ngưỡng với ngưỡng khác protocol, dải hẹp hơn, `tol > max_tol`, hoặc `bootstrap_samples` dưới mức của protocol → `422`.
- [ ] Protocol có attack bắt buộc vượt `MAX_RUNS` (quét lưới cộng `max_points`) → `422`; `max_drop_at_level` bỏ qua run tập con.
- [ ] Slice nhỏ hơn `min_slice_size` → `422`.
- [ ] Model không hỗ trợ gradient với attack bắt buộc cần gradient → `422`.
- [ ] Ước lượng trả `compliance[]` giống với kết quả kiểm tra khi tạo.

### Gửi duyệt và khóa — `test_submit_lock.py`
- [ ] Experiment gắn `dev-open` → gửi duyệt `409`.
- [ ] Experiment chưa `completed` hoặc đã `cancelled` → `409`.
- [ ] Run bắt buộc `failed` hoặc `stopped_limit` mà không có giải trình → `422`; có giải trình → thành công.
- [ ] Run `skipped` do `cached` hoặc `early_stop` không cần giải trình.
- [ ] Có run `git_dirty = true` và `forbid_dirty_runs = true` → `409`.
- [ ] Người khác gửi duyệt experiment không phải của mình → `403`.
- [ ] Sau khi gửi: hủy, gửi lại, thêm run, sửa bất kỳ trường nào của experiment → `409`; bình luận vẫn được.
- [ ] Gửi duyệt tạo email cho mọi reviewer `active` trừ người tạo.

### Nhận review và tách quyền — `test_review_separation.py`
- [ ] Người dùng có cả role engineer và reviewer: không thấy experiment của mình trong hàng đợi; nhận review experiment của mình → `403`.
- [ ] Ghi trực tiếp vào DB `reviews` hoặc `experiments.review_assignee_id` với người review là người tạo → trigger từ chối.
- [ ] Reviewer thứ hai nhận experiment đang được nhận → `409`.
- [ ] Reviewer không phải người đang nhận ghi verdict hoặc ra quyết định → `403`.
- [ ] Engineer và admin (không có role reviewer) ra quyết định → `403`.
- [ ] Trả lại review → trạng thái `submitted_for_review`, người khác nhận được.

### Verdict — `test_verdicts.py`
- [ ] Ghi verdict hai lần cho một case → hai version; version mới nhất là hiện hành; version cũ vẫn đọc được.
- [ ] `safety_relevant` không có `mitigation` → `422`.
- [ ] Sau quyết định: ghi verdict, bình luận, giải trình → `409` qua API; ghi trực tiếp vào DB → trigger từ chối.
- [ ] `UPDATE`/`DELETE` trên `case_verdicts`, `review_comments`, `run_explanations` bằng `advertest_app` → bị từ chối.
- [ ] Case bắt buộc = top-N theo `severity_score` của mỗi attack bắt buộc, thứ tự xác định.

### Tiêu chí — `test_criteria.py`
- [ ] `max_drop_at_level`: dưới ngưỡng → `pass`; trên ngưỡng → `fail`; không có run `completed` ở level hoặc run `partial` → `inconclusive`.
- [ ] `min_breaking_point`: cận dưới `bracket` ≥ level → `pass`; `not_reached` → `pass`; điểm gãy < level → `fail`; `below_min` → `fail`; level trong `bracket`, `near_threshold`, `stopped_limit`, `failed`, hoặc khoảng tin cậy chứa level → `inconclusive`.
- [ ] `class_filter` được áp dụng đúng.

### Quyết định — `test_decision.py`
- [ ] `approve` khi thiếu verdict cho case bắt buộc → `409` kèm `checklist` chỉ rõ mục thiếu.
- [ ] `approve` thiếu `conclusion`, `mitigation` hoặc `model_verdict` → `422`.
- [ ] Có tiêu chí `inconclusive` mà thiếu `inconclusive_justification` → `422`.
- [ ] `approve` đủ điều kiện → `approved`; `reviews` lưu `criteria_results` và `checklist` tại thời điểm đó; có `audit_log`; có email cho engineer.
- [ ] `changes_requested` và `reject` chỉ cần `conclusion`; experiment vào trạng thái cuối tương ứng.
- [ ] `approve` với `model_verdict = does_not_meet` được chấp nhận (chấp nhận bài test, model không đạt).
- [ ] Nhân bản experiment `changes_requested` → experiment mới có `cloned_from` đúng.

### Report — `test_report.py`
- [ ] Chấp nhận → report được sinh, `status = ready`; `ReportSnapshot` validate được.
- [ ] `json_sha256` và `pdf_sha256` khớp hash của file trong MinIO.
- [ ] Snapshot chứa **mọi** run của experiment, kể cả `failed`, `skipped`, `stopped_limit`, `cancelled`, kèm lý do và giải trình.
- [ ] Snapshot chứa experiment liên quan: tạo thêm 2 experiment cùng protocol, model, dataset version (một `completed` không gửi duyệt, một `cancelled`) trước khi chấp nhận → cả hai xuất hiện trong mục Lịch sử.
- [ ] Snapshot chứa đủ các lưu ý bắt buộc ở mục 2 và cảnh báo `git_dirty` nếu có (khi protocol cho phép).
- [ ] Ảnh case trong report đều có `anonymization.applied = true`.
- [ ] PDF có chân trang với mã report và "BẢN CHÍNH THỨC" trên mọi trang (kiểm tra bằng trích xuất văn bản).
- [ ] Tải hai lần → cùng hash; mỗi lần tải có `audit_log` `report.downloaded`.
- [ ] Engineer và admin (không có `report.export`) gọi endpoint tải → `403`; xem report trong ứng dụng → được, không có URL tải.
- [ ] Ép lỗi khi render → thử lại 3 lần, `status = failed`, experiment vẫn `approved`; sinh lại → `ready`.
- [ ] Report không thể được sinh cho experiment chưa `approved` (không có endpoint nào cho phép).
- [ ] `/verify/{report_id}` không cần đăng nhập, chỉ trả `VerifyInfo` (không tên người, không nội dung); mã không tồn tại → `404`.

### Audit — `test_audit_phase08.py`
- [ ] Mỗi action trong `requirements.md` tạo đúng một dòng `audit_log` với actor và entity đúng khi thực hiện luồng đầy đủ.

### Frontend — unit
- [ ] Wizard: chọn protocol → attack bắt buộc xuất hiện và không xóa được; ngưỡng bị khóa.
- [ ] Nút "Chấp nhận" bị khóa khi `checklist` còn mục chưa thỏa, và hiển thị lý do.
- [ ] Phím tắt verdict gửi đúng giá trị; `?` mở bảng phím tắt.
- [ ] Trang xác minh tính SHA-256 đúng trên file mẫu, và không gửi request nào chứa nội dung file (kiểm tra bằng chặn mạng trong test).

### Frontend — E2E (Playwright, 3 viewport)
- [ ] Trọn luồng trên fixture: reviewer A tạo protocol → engineer tạo experiment với protocol (attack bắt buộc điền sẵn) → chạy xong → gửi duyệt (kèm giải trình nếu cần) → reviewer A nhận, review đủ case bắt buộc bằng phím tắt (desktop) hoặc vuốt và bottom sheet (điện thoại), ghi kết luận, chấp nhận → report `ready` → reviewer tải PDF → mở `/verify/:id`, chọn file vừa tải → "Khớp".
- [ ] Sửa 1 byte của file đã tải → trang xác minh báo "Không khớp".
- [ ] Luồng yêu cầu sửa: reviewer chọn "Yêu cầu sửa" → engineer thấy quyết định và nút "Nhân bản để sửa" → wizard mở với cấu hình cũ.
- [ ] Engineer không thấy nút tải report; trang report hiển thị "BẢN CHÍNH THỨC".
- [ ] Người dùng có cả role engineer và reviewer không thấy experiment của mình trong hàng đợi review.
- [ ] Ở viewport 390px: không trang nào của phase này cuộn ngang; khung quyết định và form verdict dùng được bằng thao tác chạm.

## Manual Checks

- [ ] Tạo một protocol thật cho KITTI (ví dụ: PGD L∞ quét lưới eps 2/4/8, tìm ngưỡng PGD với sụt 20%, fog severity 1–5, tiêu chí `max_drop_at_level` và `min_breaking_point`); chạy trọn luồng với hai tài khoản trên laptop.
- [ ] Đọc toàn bộ PDF: đủ 9 mục, số liệu khớp với giao diện, biểu đồ rõ, ảnh đã làm mờ, lưu ý bắt buộc đầy đủ, tiếng Việt hiển thị đúng dấu.
- [ ] Mở PDF và trang xác minh trên điện thoại thật.
- [ ] **Thử gian lận** bằng tài khoản engineer và ghi kết quả vào `CHANGELOG.md`:
  - [ ] gọi trực tiếp API ra quyết định, ghi verdict, tải report;
  - [ ] sửa experiment sau khi gửi duyệt;
  - [ ] gửi duyệt với run chạy từ code chưa commit;
  - [ ] tạo experiment bỏ bớt attack bắt buộc hoặc giảm level;
  - [ ] chạy lại nhiều lần rồi chỉ gửi duyệt lần đẹp nhất, kiểm tra report có liệt kê các lần khác;
  - [ ] sửa file report rồi xác minh.
- [ ] Đọc lại email gửi reviewer và engineer: đúng nội dung, không chứa ảnh hay dữ liệu dataset.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; mọi thử nghiệm gian lận đều bị chặn.
- [ ] Người duyệt đã chấp nhận thay đổi contract, ma trận quyền và `tech-stack.md`.
- [ ] Câu hỏi mở đã có câu trả lời.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 8 được đánh dấu hoàn thành.
