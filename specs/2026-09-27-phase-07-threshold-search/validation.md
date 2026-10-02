# Validation: Phase 7 — Tự tìm ngưỡng

> Test trong `tests/acceptance/phase_07/` và `frontend/e2e/phase_07/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Thuật toán được test bằng hàm mức sụt tổng hợp (không cần GPU); luồng đầu cuối chạy trên CPU với fixture.

## Automated Tests

> Group 7 (2026-10-02): test nghiệm thu ở `tests/acceptance/phase_07/` (67 test không cần DB, 39 test `db` với worker CPU thật) và `frontend/e2e/phase_07/`. Mục "Bootstrap không gọi model" chạy với worker thật nên có marker `db`.

### Chung
- [x] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [x] `make contracts` không tạo thay đổi; mock mới validate được.

### Thuật toán — `test_search_algorithm.py` (hàm tổng hợp)
- [x] Hàm đơn điệu tăng, giao ngưỡng tại x* = 6.3 trên dải [0, 32], `tol = 0.5`: trạng thái `found`, `b − a ≤ 0.5`, `a < x* ≤ b`.
- [x] Số điểm đánh giá thực tế ≤ `max_points` tính bởi `bounds.py`, cả khi tập con và toàn slice cho kết quả khác nhau.
- [x] Hàm luôn dưới ngưỡng → `not_reached`, `bracket = [hi, hi]`; luôn trên ngưỡng → `below_min`, `bracket = [lo, lo]`.
- [x] Tập con cho giao ngưỡng tại 6.3 nhưng toàn slice cho 9.1 → giai đoạn xác nhận dịch khoảng lên và kết quả cuối chứa 9.1.
- [x] Trường hợp đối xứng: toàn slice giao ngưỡng thấp hơn tập con → dịch khoảng xuống, kết quả cuối đúng.
- [x] Hàm có một đoạn giảm quá 0.02 trong các điểm thô → trạng thái `non_monotonic`, vẫn có `breaking_point`.
- [x] Hàm đơn điệu giao ngưỡng tại x* = 0.3 trên [0, 32] với `tol` mặc định 0.125: `found`, `a < 0.3 ≤ b`, `b − a ≤ 0.125`.
- [x] Tham số rời rạc (severity 1–5), giao ngưỡng giữa 3 và 4 → `bracket = [3, 4]`, `breaking_point = 4`.
- [x] `lo = 0` với eps: điểm 0 có `synthetic = true`, không tạo run.
- [x] Trạng thái tuần tự hóa ở mọi giai đoạn, khôi phục rồi chạy tiếp cho kết quả giống hệt lần chạy liền mạch.
- [x] Slice có ít hơn `subset_size` ảnh → không có điểm `subset` nào, không có giai đoạn xác nhận riêng.

### Tập con — `test_subset.py`
- [x] Cùng seed cho cùng tập con, không phụ thuộc thứ tự `image_ids` đầu vào; khác seed cho tập khác.
- [x] `eval_image_ids_sha256` của run tập con khác run toàn slice cùng level; fingerprint vì vậy khác nhau.
- [x] Run toàn slice có `eval_image_ids_sha256` null và vắng trong JSON; fingerprint của manifest mốc Phase 5/6 không đổi.

### Đại lượng ngưỡng và bootstrap — `test_threshold_bootstrap.py`
- [x] Ba loại ngưỡng, có và không có `class_filter`, cho giá trị đúng trên số liệu dựng sẵn.
- [x] mAP sạch bằng 0 với `relative_drop` → tìm kiếm kết thúc `failed` kèm `message`.
- [x] `attack_success_rate` (có hoặc không `class_filter`) khi không còn object được detect đúng trên ảnh sạch → `failed` kèm `message`.
- [x] Bootstrap cùng seed cho cùng khoảng tin cậy; `bootstrap_samples = 0` → `drop_ci` và `confidence_interval` là null.
- [x] Khoảng tin cậy của mỗi điểm chứa giá trị điểm; độ rộng > 0 khi dữ liệu có biến thiên.
- [x] Dựng tình huống `d(b)` chỉ vượt ngưỡng rất ít → `near_threshold = true`; vượt xa → `false`.
- [x] Bootstrap không gọi model (spy trên estimator).

### Luồng đầu cuối — `test_search_e2e_backend.py` (worker CPU, fixture)
- [x] Experiment PGD L∞ tìm ngưỡng (`relative_drop` 0.2, dải 0–16, `tol = 2`, `subset_size = 3`) chạy xong; `SearchResult` validate được, `points_used ≤ max_points`.
- [x] Mỗi điểm có run tương ứng với `scope`, `search_order` đúng; quỹ đạo trong `SearchResult` khớp các run.
- [x] Experiment có cả attack quét lưới và tìm ngưỡng: quét lưới chạy trước.
- [x] Đã có run quét lưới toàn slice ở một level; điểm tìm kiếm toàn slice cùng level được `skipped` (`cached`).
- [x] Giới hạn thời gian nhỏ → `SearchResult.status = stopped_limit` với `bracket` là khoảng hiện có.
- [x] Ngắt worker giữa giai đoạn chia đôi → worker mới tiếp tục đúng giai đoạn, không đánh giá lại điểm đã có; `drop_ci` của điểm toàn slice chạy ở phiên trước vẫn có (đề xuất contract 001).
- [x] `SearchResult` tạm thời được cập nhật sau mỗi điểm.
- [x] Hủy experiment giữa giai đoạn tìm kiếm → `SearchResult.status = stopped_limit`, experiment `cancelled`, `bracket` là khoảng hiện có.
- [x] Lỗi không phục hồi khi chạy một điểm (estimator giả ném lỗi) → `SearchResult.status = failed` kèm `message`; attack khác trong experiment vẫn có kết quả.
- [x] Run động có `ordinal` lớn hơn mọi run quét lưới; attack tìm ngưỡng không có run nào bị `skipped` với lý do `early_stop`.
- [x] `attack_ranking` không chứa attack tìm ngưỡng, kể cả khi attack đó có run toàn slice.

### API — `test_search_api.py`
- [x] `mode = search` với `adv_patch` → `422 not_supported_yet`.
- [x] `lo ≥ hi`, `tol ≤ 0`, `tol ≥ hi − lo`, `coarse_n` ngoài 3–8, `subset_size` ngoài miền (dưới 2 hoặc lớn hơn số ảnh slice), ngưỡng ngoài miền, `class_filter` không phải class đích → `422` với đường dẫn trường đúng.
- [x] Ước lượng `searches[]`, `max_total_seconds`, `max_exceeds_limit` đúng công thức trong `requirements.md`; `total_seconds` và `exceeds_limit` không đổi khi thêm attack tìm ngưỡng; experiment chỉ có attack tìm ngưỡng có `runs` rỗng.
- [x] Số run quét lưới cộng Σ `max_points` vượt 50 → `422` ở `attacks`.
- [x] `progress.images_total` của experiment tìm ngưỡng tăng khi worker tạo run động; `queue.ahead_seconds` của experiment xếp sau tính phần `max_seconds` còn lại (experiment `queued` phía trước: cả `max_seconds`; experiment đang chạy không đứng trước, như Phase 5).
- [x] `class_filter` dạng danh sách → `422`.
- [x] Worker tạo run động với level ngoài `[lo, hi]` → `422`; vượt `max_points` → `422`; cho attack không ở chế độ tìm kiếm → `422`; worker không dừng experiment khi nhận các `422` này.
- [x] Token của target khác gọi endpoint tạo run động → `403`.
- [x] `artifact-url` `GET runs/<run_id>/predictions.json` của run đã kết thúc trong experiment đang lease → URL; `PUT`/`DELETE` hoặc khóa khác của run đã kết thúc → `409`; run trúng cache có `predictions_key` trỏ tới bản sao trong thư mục của chính nó (đề xuất contract 001).
- [x] `POST /runs/{id}/skip` cho run của attack tìm ngưỡng → `422`.
- [x] Migration `0008` lên và xuống được; bảng mới được `GRANT` cho `advertest_app` (`test_every_table_is_granted_to_app` pass).

### Frontend — unit và E2E (Playwright, 3 viewport)

> Câu kết luận theo trạng thái, nhãn của biểu đồ so sánh, thẻ `failed`/`stopped_limit` chỉ có trong mock: kiểm bằng Vitest (`frontend/src/components/charts/`). Các mục còn lại: `frontend/e2e/phase_07/search.spec.ts` với backend và worker thật.
- [x] Schema `zod` của form tìm ngưỡng từ chối đúng các trường hợp mà backend từ chối.
- [x] Câu kết luận đúng cho từng trạng thái trong mock.
- [x] Wizard điền `tol` mặc định bằng (hi − lo)/256; cảnh báo khi `subset_size` dưới 20.
- [x] Engineer tạo experiment tìm ngưỡng cho PGD trên fixture; bước 6 hiển thị "tối đa"; khi chạy, dòng tiến độ tìm kiếm cập nhật; khi xong, thẻ tóm tắt và biểu đồ quỹ đạo hiển thị.
- [x] Công tắc tìm ngưỡng của `adv_patch` bị khóa và có giải thích.
- [x] Biểu đồ so sánh hiển thị `not_reached` là "> {hi/max}%" ("> 100%" khi tìm trên toàn dải của spec; quyết định Group 6) và `below_min` là "≤ mức nhỏ nhất".
- [x] Thẻ `failed` hiển thị `message`; thẻ `stopped_limit` hiển thị khoảng hiện có.
- [x] Nháp wizard lưu theo định dạng trước Phase 7 mở được; attack là quét lưới, không mất trường nào.
- [x] Ở viewport 390px: chỉ hiện thẻ tóm tắt; chạm mở biểu đồ toàn màn hình; không cuộn ngang.

## Manual Checks

- [ ] Trên KITTI 300 ảnh: tìm ngưỡng PGD L∞ với `relative_drop` 0.2, dải 0–32, `tol` mặc định (0.125). So với đường cong quét lưới PGD L∞ ở Phase 5/6: điểm gãy nằm trong khoảng mà đường cong quét lưới cắt ngưỡng 20%.
- [ ] Ghi số điểm thực tế đã dùng, thời gian thực tế so với chi phí tối đa hiển thị.
- [ ] Tìm ngưỡng `fog` (rời rạc) với ngưỡng 0.2; kết quả hợp lý với kết quả quét lưới severity 1–5.
- [ ] Tìm ngưỡng với `class_filter = person` và so với toàn bộ class; ghi nhận khác biệt.
- [ ] So sánh điểm gãy trên tập con (100 ảnh) với kết quả cuối: ghi mức lệch để trả lời câu hỏi mở về `subset_size`.
- [ ] Đo thời gian bootstrap 200 mẫu trên worker.
- [ ] Xem thẻ tóm tắt và biểu đồ quỹ đạo trên điện thoại thật.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; kết quả so sánh với quét lưới đã ghi vào `CHANGELOG.md`.
- [ ] Người duyệt đã chấp nhận thay đổi contract.
- [ ] Câu hỏi mở đã có câu trả lời; giá trị mặc định đã điều chỉnh nếu cần.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 7 được đánh dấu hoàn thành.
