# Validation: Phase 8 — Protocol, review và report

> Test trong `tests/acceptance/phase_08/` và `frontend/e2e/phase_08/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Đây là phase hiện thực hóa các nguyên tắc chống gian lận, nên mỗi luật có ít nhất một test cố tình vi phạm nó.

## Automated Tests

### Chung
- [x] `make check` pass, bao gồm test nghiệm thu các phase trước (bảng ma trận quyền Phase 4 đã cập nhật `review.comment`).
- [x] `make contracts` không tạo thay đổi; mock mới validate được.
- [x] `make test-db` chạy test nghiệm thu Phase 5–8 chung phiên; test email Phase 5 không phụ thuộc ngày. Phase 7 và 8 dựng DB bằng `DROP OWNED BY` rồi `upgrade head`: migration không xóa dữ liệu thật khi downgrade, nên `downgrade base` sau Phase 6 vướng run trỏ tới spec của 0006 (người dùng chốt ở Group 7, 2026-10-02).

### Protocol — `test_protocols.py`
- [x] Reviewer tạo protocol → `active`, version 1, có `audit_log`.
- [x] Engineer hoặc admin tạo protocol → `403`.
- [x] Tạo version mới → bản ghi mới; nội dung version cũ không đổi (so sánh hash); version cũ chuyển `retired`; tạo version từ bản không phải mới nhất → `409`.
- [x] Không có endpoint nào sửa nội dung một version đã tạo.
- [x] Tiêu chí tham chiếu attack không có trong `required_attacks`, `min_breaking_point` với attack quét lưới, hoặc patch ở chế độ tìm ngưỡng → `422`.
- [x] Attack spec không tồn tại hoặc `spec_sha256` không khớp → `422`.
- [x] Protocol `retired` không chọn được khi tạo experiment mới; experiment cũ gắn protocol đó vẫn gửi duyệt được.

### Tuân thủ khi tạo — `test_compliance.py`
- [x] Thiếu attack bắt buộc, sai `spec_sha256`, sai `mode` → `422` kèm mục `compliance` tương ứng không thỏa.
- [x] Quét lưới thiếu một level bắt buộc → `422`; thêm level ngoài protocol → cho phép.
- [x] Tìm ngưỡng với ngưỡng khác protocol, dải hẹp hơn, `tol > max_tol`, hoặc `bootstrap_samples` dưới mức của protocol → `422`.
- [x] Protocol có attack bắt buộc vượt `MAX_RUNS` (quét lưới cộng `max_points`) → `422`; `max_drop_at_level` bỏ qua run tập con.
- [x] Slice nhỏ hơn `min_slice_size` → `422`.
- [x] Model không hỗ trợ gradient với attack bắt buộc cần gradient → `422`.
- [x] Ước lượng trả `compliance[]` giống với kết quả kiểm tra khi tạo.

### Gửi duyệt và khóa — `test_submit_lock.py`
- [x] Experiment gắn `dev-open` → gửi duyệt `409`.
- [x] Experiment chưa `completed` hoặc đã `cancelled` → `409`.
- [x] Run bắt buộc `failed` hoặc `stopped_limit` mà không có giải trình → `422`; có giải trình → thành công.
- [x] Run `skipped` do `cached` hoặc `early_stop` không cần giải trình.
- [x] Có run `git_dirty = true` và `forbid_dirty_runs = true` → `409`.
- [x] Người khác gửi duyệt experiment không phải của mình → `403`.
- [x] Sau khi gửi: hủy, gửi lại, thêm run, sửa bất kỳ trường nào của experiment → `409`; bình luận vẫn được.
- [x] Gửi duyệt tạo email cho mọi reviewer `active` trừ người tạo.
- [x] Case bắt buộc ở `hidden_unanonymized` → gửi duyệt `409`.

### Nhận review và tách quyền — `test_review_separation.py`
- [x] Người dùng có cả role engineer và reviewer: không thấy experiment của mình trong hàng đợi; nhận review experiment của mình → `403`.
- [x] Ghi trực tiếp vào DB `reviews` hoặc `experiments.review_assignee_id` với người review là người tạo → trigger từ chối.
- [x] Reviewer thứ hai nhận experiment đang được nhận → `409`.
- [x] Reviewer không phải người đang nhận ghi verdict hoặc ra quyết định → `403` (trước cả kiểm tra trường nhập của nghiệp vụ, ví dụ thiếu `inconclusive_justification` khi có tiêu chí chưa kết luận). Body sai schema của contract (thiếu `conclusion`; `approve` thiếu `mitigation` hoặc `model_verdict`; verdict `safety_relevant` thiếu `mitigation`) là `422` của framework, kiểm trước mọi thứ (người dùng chốt ở Group 7, 2026-10-02).
- [x] Engineer và admin (không có role reviewer) ra quyết định → `403`.
- [x] Trả lại review → trạng thái `submitted_for_review`, người khác nhận được.

### Verdict — `test_verdicts.py`
- [x] Ghi verdict hai lần cho một case → hai version; version mới nhất là hiện hành; version cũ vẫn đọc được.
- [x] `safety_relevant` không có `mitigation` → `422`.
- [x] Sau quyết định: ghi verdict, bình luận, gọi lại `submit` kèm giải trình → `409` qua API; ghi trực tiếp vào DB (`case_verdicts`, `review_comments`, `run_explanations`) → trigger từ chối.
- [x] Bình luận khi experiment `completed` (chưa gửi) → `409`; target không thuộc experiment → `422`; admin → `403`.
- [x] `UPDATE`/`DELETE` trên `case_verdicts`, `review_comments`, `run_explanations` bằng `advertest_app` → bị từ chối.
- [x] Case bắt buộc = top-N theo `severity_score` của mỗi attack bắt buộc, thứ tự xác định.

### Tiêu chí — `test_criteria.py`
- [x] `max_drop_at_level`: dưới ngưỡng → `pass`; trên ngưỡng → `fail`; không có run `completed` ở level hoặc run `partial` → `inconclusive`.
- [x] `min_breaking_point`: cận dưới `bracket` ≥ level → `pass`; `not_reached` → `pass`; điểm gãy < level → `fail`; `below_min` → `fail`; level trong `bracket`, `near_threshold`, `stopped_limit`, `failed`, hoặc khoảng tin cậy chứa level → `inconclusive`.
- [x] `class_filter` được áp dụng đúng.
- [x] `max_drop_at_level` ở level `skipped` do `early_stop`: dùng đại lượng của run kích hoạt; `detail` ghi rõ.

### Quyết định — `test_decision.py`
- [x] `approve` khi thiếu verdict cho case bắt buộc hoặc protocol `dev` → `409` kèm `checklist` chỉ rõ mục thiếu; `checklist` chỉ gồm mục trạng thái.
- [x] `approve` thiếu `conclusion`, `mitigation` hoặc `model_verdict` → `422`.
- [x] Có tiêu chí `inconclusive` mà thiếu `inconclusive_justification` → `422`.
- [x] `approve` đủ điều kiện → `approved`; `reviews` lưu `criteria_results` và `checklist` tại thời điểm đó; có `audit_log`; có email cho engineer.
- [x] `changes_requested` và `reject` chỉ cần `conclusion`; experiment vào trạng thái cuối tương ứng.
- [x] `approve` với `model_verdict = does_not_meet` được chấp nhận (chấp nhận bài test, model không đạt).
- [x] Nhân bản experiment `changes_requested` → experiment mới có `cloned_from` đúng.

### Report — `test_report.py`
- [x] Chấp nhận → report được sinh, `status = ready`; `ReportSnapshot` validate được.
- [x] `json_sha256` và `pdf_sha256` khớp hash của file trong MinIO.
- [x] Snapshot chứa **mọi** run của experiment, kể cả `failed`, `skipped`, `stopped_limit`, `cancelled`, kèm lý do và giải trình.
- [x] Snapshot chứa experiment liên quan: tạo thêm 2 experiment cùng protocol, model, dataset version (một `completed` không gửi duyệt, một `cancelled`) và 1 experiment `dev-open` cùng model, dataset version trước khi chấp nhận → cả ba xuất hiện trong mục Lịch sử, bản `dev-open` có nhãn "dev"; experiment khác model không xuất hiện.
- [x] Snapshot chứa đủ các lưu ý bắt buộc ở mục 2 và cảnh báo `git_dirty` nếu có (khi protocol cho phép).
- [x] Ảnh case trong report đều có `anonymization.applied = true`.
- [x] PDF có chân trang với mã report và "BẢN CHÍNH THỨC" trên mọi trang (kiểm tra bằng trích xuất văn bản).
- [x] Tải hai lần → cùng hash; mỗi lần tải có `audit_log` `report.downloaded`.
- [x] Engineer và admin (không có `report.export`) gọi endpoint tải → `403`; xem report trong ứng dụng → được, không có URL tải.
- [x] Ép lỗi khi render → thử lại 3 lần, `status = failed`, experiment vẫn `approved`; sinh lại → `ready`, `report_id` không đổi.
- [x] Dòng `reports` đã `ready`: `UPDATE` bằng `advertest_app` → trigger từ chối; `DELETE` → bị từ chối.
- [x] Report ở `generating` khi API khởi động lại → được sinh tiếp tới `ready`.
- [x] Snapshot có lưu ý eps tính trên ảnh letterbox float (không lượng tử 8-bit).
- [x] Report không thể được sinh cho experiment chưa `approved` (không có endpoint nào cho phép).
- [x] `/verify/{report_id}` không cần đăng nhập, chỉ trả `VerifyInfo` (không tên người, không nội dung); mã không tồn tại → `404`.

### Audit — `test_audit_phase08.py`
- [x] Mỗi action trong `requirements.md` tạo đúng một dòng `audit_log` với actor và entity đúng khi thực hiện luồng đầy đủ.

### Frontend — unit
- [x] Wizard: chọn protocol → attack bắt buộc xuất hiện và không xóa được; ngưỡng bị khóa.
- [x] Nút "Chấp nhận" bị khóa khi `checklist` còn mục chưa thỏa, và hiển thị lý do.
- [x] Phím tắt verdict gửi đúng giá trị; `?` mở bảng phím tắt.
- [x] Trang xác minh tính SHA-256 đúng trên file mẫu, và không gửi request nào chứa nội dung file (kiểm tra bằng chặn mạng trong test).

### Frontend — E2E (Playwright, 3 viewport)
- [x] Trọn luồng trên fixture: reviewer A tạo protocol → engineer tạo experiment với protocol (attack bắt buộc điền sẵn) → chạy xong → gửi duyệt (kèm giải trình nếu cần) → reviewer A nhận, review đủ case bắt buộc bằng phím tắt (desktop) hoặc vuốt và bottom sheet (điện thoại), ghi kết luận, chấp nhận → report `ready` → reviewer tải PDF → mở `/verify/:id`, chọn file vừa tải → "Khớp".
- [x] Sửa 1 byte của file đã tải → trang xác minh báo "Không khớp".
- [x] Luồng yêu cầu sửa: reviewer chọn "Yêu cầu sửa" → engineer thấy quyết định và nút "Nhân bản để sửa" → wizard mở với cấu hình cũ.
- [x] Engineer không thấy nút tải report; trang report hiển thị "BẢN CHÍNH THỨC".
- [x] Người dùng có cả role engineer và reviewer không thấy experiment của mình trong hàng đợi review.
- [x] Ở viewport 390px: không trang nào của phase này cuộn ngang; khung quyết định và form verdict dùng được bằng thao tác chạm.

## Manual Checks

- [x] Tạo một protocol thật cho KITTI (ví dụ: PGD L∞ quét lưới eps 2/4/8, tìm ngưỡng PGD L2 với sụt 20% (mỗi attack một chế độ, chốt ở Group 0), fog severity 1–5, tiêu chí `max_drop_at_level` và `min_breaking_point`); chạy trọn luồng với hai tài khoản trên laptop.
- [x] Đọc toàn bộ PDF: đủ 9 mục, số liệu khớp với giao diện, biểu đồ rõ, ảnh đã làm mờ, lưu ý bắt buộc đầy đủ, tiếng Việt hiển thị đúng dấu.
- [x] Mở PDF và trang xác minh trên điện thoại thật.
- [x] **Thử gian lận** bằng tài khoản engineer và ghi kết quả vào `CHANGELOG.md`:
  - [x] gọi trực tiếp API ra quyết định, ghi verdict, tải report;
  - [x] sửa experiment sau khi gửi duyệt;
  - [x] gửi duyệt với run chạy từ code chưa commit;
  - [x] tạo experiment bỏ bớt attack bắt buộc hoặc giảm level;
  - [x] chạy lại nhiều lần rồi chỉ gửi duyệt lần đẹp nhất, kiểm tra report có liệt kê các lần khác;
  - [x] sửa file report rồi xác minh.
- [x] Đọc lại email gửi reviewer và engineer: đúng nội dung, không chứa ảnh hay dữ liệu dataset.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [x] Toàn bộ Manual Checks đã thực hiện; mọi thử nghiệm gian lận đều bị chặn.
- [x] Người duyệt đã chấp nhận thay đổi contract, ma trận quyền và `tech-stack.md`.
- [x] Câu hỏi mở đã có câu trả lời.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 8 được đánh dấu hoàn thành.
