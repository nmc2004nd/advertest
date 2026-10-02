# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Phase 7 — Tự tìm ngưỡng

**Trạng thái:** ✅ hoàn thành 2026-10-02, còn tồn đọng (số liệu manual check chưa ghi, hai câu hỏi mở; người dùng cho phép đóng phase). Group 0–7 đã merge.

### Replan sau Phase 7 — 2026-10-02
- Câu hỏi mở của Phase 7 chưa có câu trả lời (chờ số liệu manual check); giữ giá trị mặc định.
- Phase 8 `requirements.md`: `min_breaking_point` so level với cả `bracket` (level trong khoảng → `inconclusive`); `required_attacks` dạng tìm ngưỡng thêm `min_bootstrap_samples` (mặc định 200) và tuân thủ đòi `bootstrap_samples` không thấp hơn (chặn né KTC); `max_drop_at_level` chỉ dùng run toàn slice; protocol phải vừa `MAX_RUNS` (quét lưới cộng `max_points`); Context Phase 7 (run tập con trong report, nhãn "> {hi/max}%", số điểm và số mẫu bootstrap trong report). `validation.md` Phase 8 sửa và thêm mục tương ứng.
- `roadmap.md`: Phase 8 thêm sửa migration 0006 và test email phụ thuộc ngày; Phase 9 thêm giữ chỗ ngân sách theo `max_total_seconds`.
- Người dùng chấp nhận toàn bộ đề xuất.

### Phase 7 — Tổng kết (phase-close) — 2026-10-02
- **Giao được:** tự tìm ngưỡng theo attack (quét thô trên tập con → chia đôi → xác nhận và dịch khoảng trên toàn slice; 6 trạng thái; level 0 tổng hợp; chạy tiếp từ `SearchResult` sau gián đoạn); `max_points` tính trước, chi phí tối đa trong ước lượng, trần `MAX_RUNS = 50` tính cả `max_points`; ba loại ngưỡng, có hoặc không `class_filter`; KTC bootstrap từ prediction đã lưu (không gọi model), `near_threshold`; tập con cố định theo `hash(seed, image_id)`, `eval_image_ids_sha256` trong fingerprint (run toàn slice trúng cache quét lưới); run động qua `POST /internal/worker/experiments/{id}/runs`; wizard có công tắc theo attack, form `zod` cùng luật backend, chi phí "tối đa" ở bước 5 và 6, nháp `v2` cũ mở được; tab Kết quả có mục "Điểm gãy" (thẻ tóm tắt, tiến độ, quỹ đạo, so sánh chuẩn hóa), điện thoại chạm thẻ mở toàn màn hình; xếp hạng và đường cong Phase 6 chỉ gồm attack quét lưới.
- **Contract:** Group 0 (`SearchConfig`, `SearchResult`, `TrajectoryPoint`, `SearchEstimate`, `scope`/`search_order`/`predictions_key` của run, `eval_image_ids_sha256`, endpoint run động và kết quả tìm ngưỡng), đề xuất 001 (`artifact-url` đọc `predictions.json` của run đã kết thúc khi bootstrap). Người dùng chấp nhận.
- **Số liệu cuối (máy phát triển, CPU):** `make check` pass (1335 test Python, 314 Vitest, 331 test nghiệm thu không cần DB); `make test-db` 471 pass, 1 fail (test email Phase 5 phụ thuộc ngày, có từ trước); `make test-e2e` 78/78, 6,4 phút. CI xanh (người dùng xác nhận). Số đo trên fixture 5 ảnh: xem Group 7.
- **`validation.md`:** Automated Tests đủ; Manual Checks 7/7 (người dùng xác nhận đã làm và đạt); Definition of Done 3/5 (số liệu so sánh với quét lưới chưa ghi; hai câu hỏi mở chưa có câu trả lời ghi lại).
- **Câu hỏi mở:** `subset_size` 100 và 200 mẫu bootstrap: manual check đã làm nhưng số liệu chưa ghi, nên chưa trả lời; giữ giá trị mặc định.
- **Tồn đọng (người dùng cho phép đóng phase, cập nhật sau):** số liệu manual check trên KITTI 300 ảnh (điểm gãy và KTC của PGD L∞ so với đoạn đường cong quét lưới cắt 20%, `points_used`/`max_points`, thời gian thực so với "tối đa", fog, `class_filter = person`, mức lệch tập con so với kết quả cuối, thời gian bootstrap 200 mẫu, thiết bị điện thoại); câu trả lời cho hai câu hỏi mở; mục roadmap "(Từ Phase 2, 6)" khoảng tìm kiếm PGD dưới 1/255 kiểm cùng số liệu đó; migration 0006 không downgrade được khi có `cost_profiles` của spec Phase 6 (giao agent backend; sau đó bỏ `DROP OWNED BY` trong `tests/acceptance/phase_07/conftest.py`); test email Phase 5 phụ thuộc ngày (chưa có người nhận).
- **Lưu ý:** Group 0, 7, review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 7 — Group 7 (người duyệt) — 2026-10-02
#### Test nghiệm thu (task 32)
- `tests/acceptance/phase_07/`, viết độc lập với test của agent, chỉ dùng API công khai:
  - không cần DB (67 test): thuật toán lái bằng hàm mức sụt tổng hợp đúng như worker gọi `ThresholdSearch.progress` (cả dịch khoảng lên/xuống, rời rạc, `synthetic`, chạy tiếp từ `SearchResult` tuần tự hóa sau mỗi điểm, 40 tình huống ngẫu nhiên không vượt `max_points`); tập con và fingerprint (manifest mốc Phase 5 và Phase 6 giữ nguyên fingerprint); đại lượng ngưỡng; bootstrap trên dữ liệu dựng sẵn 40 ảnh;
  - `db` (39 test, worker CPU thật, fixture 5 ảnh, tập con 3): PGD L∞ tìm ngưỡng chạy một lần cho cả phiên; FGSM ngưỡng 0.5 cho các tình huống (chạm giới hạn, worker chết hai lần rồi chạy tiếp, hủy, lỗi một điểm, trúng cache quét lưới); API (đường dẫn trường của mọi luật, công thức ước lượng, trần 50 run, `images_total`, hàng đợi, run động `422`/`403`, `artifact-url`, skip, migration 0008 và quyền `advertest_app`); bootstrap không gọi model (đếm `UltralyticsDetector.forward` trong lúc bootstrap: 0).
- Số đo trên slice fixture (CPU, seed 0) để chọn ngưỡng: mức sụt tương đối của FGSM ở eps 1/2/4/8/16 là 0.26/0.34/0.57/0.60/0.64 (khoảng 0.8 giây mỗi run 5 ảnh); PGD L∞ 0.49 ở eps 1, từ 0.97 ở eps 2 (khoảng 6 giây mỗi run). FGSM trên tập con 3 ảnh gần bão hòa từ eps 8 nên ra `non_monotonic` (vẫn có điểm gãy).
- `frontend/e2e/phase_07/search.spec.ts` (3 viewport, backend và worker thật): wizard (tol mặc định 0.125, đi theo dải, cảnh báo tập con dưới 20, công tắc `adv_patch` khóa kèm giải thích), bước 5 và 6 hiển thị "tối đa", dòng tiến độ tăng khi chạy, thẻ tóm tắt và quỹ đạo khi xong, 390px chỉ thẻ và dialog toàn màn hình, nháp `v2` dạng Phase 6 mở được. Mỗi viewport một cận trên khác nhau để worker chạy thật (không trúng cache). Các mục chỉ có trong mock (câu kết luận theo trạng thái, nhãn so sánh, thẻ `failed`/`stopped_limit`) do Vitest của Group 6 phủ.
- `validation.md`: đánh dấu Automated Tests; câu "> 100%" sửa theo quyết định Group 6; mục hàng đợi ghi rõ chỉ tính experiment `queued` (xem phát hiện 2).
#### Phát hiện khi viết test
1. **Migration 0006 không downgrade được khi có dữ liệu Phase 6:** `downgrade` xóa spec `not_applicable` nhưng `cost_profiles` còn trỏ tới (khóa ngoại). Test nghiệm thu Phase 5/6 dựng DB bằng `downgrade base`, nên chạy chung phiên sau Phase 6 thì Phase 7 lỗi; Phase 7 dùng `DROP OWNED BY advertest_owner` thay thế. Cần agent backend sửa 0006 (xóa `cost_profiles` của các spec đó trước).
2. **`queue.ahead_seconds` "trừ thời gian đã dùng":** `ahead_seconds` (Phase 5) chỉ tính experiment `queued`; experiment có lease hết hạn vẫn `running`, nên experiment đứng trước chưa dùng giây nào và vế "trừ thời gian xử lý đã dùng cho attack đó" trong `requirements.md` không bao giờ có tác dụng. Test nghiệm thu kiểm theo nghĩa Phase 5. Người dùng chốt giữ nghĩa Phase 5: `requirements.md` mục Context bỏ vế "trừ thời gian đã dùng" (không đổi code; hàm `_search_remaining` vẫn trừ, vô hại).
3. Bảng `search_results` có từ trước 0008 (0008 thêm `updated_at` và ràng buộc); `RunView.scope` bị bỏ khỏi JSON khi bằng `full` (contract): ghi nhận, không phải lỗi.
#### Manual check (task 33, 34): chưa làm
Máy phát triển không có KITTI đầy đủ (chỉ fixture 5 ảnh) và không có GPU. Hướng dẫn cho người duyệt:
1. Chuẩn bị như manual check Phase 5: KITTI đầy đủ, `make up`, slice 300 ảnh (`advertest slice create --size 300`), `advertest-admin import-local`, worker (`docker/worker/up.sh cpu` hoặc `gpu`).
2. Wizard: PGD L∞ tự tìm ngưỡng, `relative_drop` 20%, dải 0–32, `tol` mặc định 0.125, tập con 100, bootstrap 200. Ghi `status`, điểm gãy, KTC 95%, `points_used`/`max_points`, thời gian thực so với "tối đa" ở bước 6. So với đường cong quét lưới PGD L∞ Phase 5/6 (hoặc chạy lưới 0.25/0.5/1/2): điểm gãy phải nằm trong đoạn mà đường cong cắt mức sụt 20%.
3. `fog` (rời rạc) ngưỡng 20%, so với quét lưới severity 1–5.
4. PGD L∞ với `class_filter = person` so với mọi class; ghi khác biệt.
5. Câu hỏi mở `subset_size`: trong quỹ đạo, so khoảng cuối trên tập con (điểm rỗng ruột) với kết quả cuối; ghi mức lệch theo eps.
6. Câu hỏi mở bootstrap: thời gian từ khi run toàn slice cuối kết thúc tới `finished_at` của experiment (gồm bootstrap 200 mẫu) trên worker.
7. Thẻ tóm tắt và quỹ đạo trên điện thoại thật (Android, iPhone), chế độ tối; trường hợp điểm gãy rất nhỏ so với dải (số thứ tự sát trục tung).

### Phase 7 — Group 6 (frontend: kết quả) — 2026-10-02
- Tab Kết quả, mục "Điểm gãy": thẻ tóm tắt mỗi attack tìm ngưỡng (câu kết luận theo 6 trạng thái, cảnh báo sát ngưỡng và không đơn điệu, dòng tiến độ khi đang chạy); biểu đồ quỹ đạo kèm bảng; biểu đồ so sánh điểm gãy chuẩn hóa kèm bảng. Điện thoại chỉ hiện thẻ, chạm thẻ mở quỹ đạo toàn màn hình.
- Đường cong metric Phase 6 chỉ gồm run của attack quét lưới.
- Review (phase-review), người dùng chọn sửa: #1 `not_reached` hiện "> {hi/max}%" thay vì luôn "> 100%" (điều chỉnh câu trong `requirements.md`); #2 bảng quỹ đạo giữ level chính xác, câu kết luận làm tròn 4 chữ số có nghĩa. Quyết định ghi vào `requirements.md` mục Frontend.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 7 — Group 5 (frontend: wizard) — 2026-10-01
- Bước 4: công tắc "Quét lưới / Tự tìm ngưỡng" theo attack (bỏ ô chế độ chung "Sắp có"); form tìm ngưỡng (3 loại ngưỡng có giải thích, ngưỡng %, class đích, dải, độ chính xác, "Nâng cao" thu gọn) với schema `zod` cùng luật backend; `adv_patch` bị khóa kèm giải thích.
- Bước 5 và 6: chi phí tối đa "tối đa ~X (tối đa N điểm)", cảnh báo `max_exceeds_limit`; nhân bản experiment tìm ngưỡng giữ cấu hình.
- Nháp giữ khóa `advertest.wizard.v2`; attack thiếu `mode`/`search` là quét lưới.
- Review (phase-review), người dùng chọn sửa cả 5 điểm: #1 không ước lượng khi form tìm ngưỡng lỗi; #2 tên truy cập theo attack; #3 `tol` theo dải tới khi người dùng sửa; #4 kiểm `tol` cho tham số rời rạc; #5 preset giữ cấu hình tìm ngưỡng. Quyết định ghi vào `requirements.md` mục Frontend.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 7 — Task 18b (worker) — 2026-10-01
- Hook `predictions` của `JobRunner`: run hoàn tất trong phiên dùng bộ nhớ; run đã kết thúc ở phiên trước hoặc trúng cache đọc `runs/<run_id>/predictions.json` qua `artifact-url` (đề xuất contract 001). `read_predictions_file` đọc bản sao theo khóa của run gốc ghi trong file.
- Test: chạy tiếp sau gián đoạn cho `drop_ci` và khoảng tin cậy giống hệt chạy liền mạch; không có file → điểm bỏ khỏi bootstrap; đọc bản sao khi trúng cache.
- Review (phase-review): #1 (người dùng chọn sửa) lỗi đọc khác 404 (MinIO `5xx`/`403`, API từ chối, file hỏng) làm sập bootstrap, experiment lặp mãi → bỏ điểm khỏi bootstrap kèm cảnh báo, mất lease vẫn dừng; test file hỏng, MinIO `500`, mất lease. #2 (ghi vào `requirements.md` mục Worker): bản sao giữ khóa của run gốc.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 7 — Group 4 (backend) — 2026-10-01
#### Thêm
- Migration `0008` (task 18a): `runs.scope` (mặc định `full`, ràng buộc giá trị), `runs.search_order` (bắt buộc khi `subset`, không trùng trong một attack), `runs.predictions_key`; `search_results` mỗi (experiment, attack) một dòng, `updated_at`.
- Kiểm tra cấu hình (task 19): `adv_patch` tìm ngưỡng → `422 not_supported_yet`; dải trong spec (rời rạc: giá trị của spec), `subset_size` ≤ số ảnh slice, `class_filter` là class đích, cận `absolute_drop` khi biết mAP sạch, không có slice huấn luyện; `MAX_RUNS` tính `max_points`. Attack tìm ngưỡng không tạo run lúc tạo experiment.
- Ước lượng (task 20, 23): `searches[]` (`search_bounds`), `max_total_seconds`, `max_exceeds_limit` (chỉ cảnh báo); `queue.ahead_seconds` cộng phần `max_seconds` còn lại.
- `services/searches.py` (task 21, 22): tạo run động (mọi vi phạm `422`, `ordinal` sau mọi run); nhận `SearchResult` (đối chiếu run, metric, cấu hình; bản cuối không thay); điều kiện hoàn tất experiment mới; chốt `stopped_limit` khi hủy hoặc hết giờ. `ExperimentDetail.search_results`, bundle có `search_results`, `scope`, `search_order`; xếp hạng chỉ gồm quét lưới; `skip` từ chối run tìm ngưỡng (task 22a).
- Đề xuất 001 (task 22b): `artifact-url` cấp `GET` prediction của run đã kết thúc; sao chép prediction khi trúng cache; `complete` lưu `predictions_key` (file phải có).
- Test: `test_migration_0008.py`, `test_phase07_api.py` (23), `test_phase07_worker_api.py` (23).
#### Sửa test cũ
- Backend: `test_skeleton.py` (hai endpoint tìm ngưỡng không còn `501`), `test_experiment_api.py` (`mode = search` chỉ `not_supported_yet` với `adv_patch`).
- Test nghiệm thu (người duyệt, người dùng cho phép ở kế hoạch Group 4): Phase 0 `test_api.py` (endpoint tìm ngưỡng không token → `401`), Phase 5 `test_experiment_validation.py` (`not_supported_yet` theo `adv_patch`).
#### Review (phase-review, 2026-10-01)
- #1 (người dùng chọn sửa): trúng cache mà file prediction gốc đã mất → API `500`, worker dừng job → không sao chép, `predictions_key` null; test mới fail trên code cũ.
- #2, #3 (người dùng chấp nhận, ghi vào `requirements.md` mục "Chốt ở Group 4"): `stopped_limit` do API chốt không có `drop_ci`; kết quả cuối không thay; đối chiếu metric; downgrade `0008` xóa `search_results`.
- Ghi nhận: `make test-db` 431 pass, 1 fail (test email Phase 5 phụ thuộc ngày, có từ trước trên `main`); `make test-e2e` chưa chạy.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 7 — Đề xuất contract 001 (người duyệt, người dùng giao) — 2026-10-01
- Nguồn: Group 3 (worker). Bootstrap cần prediction của mọi điểm toàn slice, nhưng `artifact-url` chỉ cấp URL cho run đang `running` (run đã xong → `409` = mất lease) và điểm trúng cache nằm ở thư mục run gốc.
- Contract: mô tả `ArtifactUrlRequest.key` (run phải `running`, trừ `GET runs/<run_id>/predictions.json` của run đã kết thúc thuộc experiment đang lease) và `predictions_key` (run trúng cache có bản sao file của run gốc). Không đổi kiểu, route, `schema_version`; sinh lại JSON Schema, OpenAPI, type TypeScript.
- Spec: `requirements.md` mục API (hành vi `artifact-url`, sao chép khi `skip_cached`) và mục Worker; `plan.md` task 22b (backend), 18b (worker, sau 22b); `validation.md` thêm mục API và mục chạy tiếp có `drop_ci`.
- Test Phase 3 về "run đã kết thúc không xin được URL" (khóa `late.json`, `x.json`) vẫn đúng.

### Phase 7 — Group 3 (worker) — 2026-10-01
#### Thêm
- `ml_core/runner/` (task 13, 13a, 13b): `RunContext.restricted` (run trên tập con, mAP sạch tính lại trên tập con); `build_fingerprint_inputs(..., eval_image_ids_sha256=)`; checkpoint lưu `class_correct`, `class_lost` (checkpoint cũ vẫn nạp); `finalize` truyền `class_names` (ASR theo class).
- `advertest_worker/search.py` (task 14-17): `SearchDriver` dựng lại trạng thái từ `SearchResult`, dùng lại run đã tạo theo `search_order`, gửi kết quả tạm thời sau mỗi điểm, `stopped_limit` khi hủy hoặc chạm giới hạn, `failed` khi run lỗi hoặc API từ chối, bootstrap khi kết thúc.
- `job.py` (task 13a, 14-18): quét lưới trước, rồi từng attack tìm ngưỡng; run động qua `POST /experiments/{id}/runs`; tập ảnh theo `scope`; mọi run có metric upload prediction theo ảnh; `RunResult` có `scope`, `search_order`, `predictions_key`. Client: `create_search_run`, `search_result` (`422` không phải mất lease).
- Test: `test_search_driver.py` (21, hook giả), `test_search_job.py` (6, `JobRunner` với executor thật, API và MinIO giả trong bộ nhớ), test executor, fingerprint, client.
#### Đề xuất contract
- 001 (chờ duyệt): API cho worker đọc `runs/<run_id>/predictions.json` của run đã kết thúc, sao chép file khi trúng cache. Cho tới khi duyệt, bootstrap chỉ dùng prediction của run hoàn tất trong phiên.
#### Review (phase-review, 2026-10-01)
- #1 (chặn, người dùng chọn sửa): `ApiError` (`422`) khi tạo run động hoặc gửi kết quả tạm thời làm sập job, experiment kẹt `running` và bị lease lại lặp mãi → lần tìm kết thúc `failed`, experiment chạy tiếp attack sau; test mới fail trên code cũ.
- #3, #4 (người dùng chấp nhận, ghi vào `requirements.md` mục Worker): calibration đo ở `search.hi`; run lỗi/bị bỏ qua làm lần tìm `failed`; run đã tạo chạy tiếp theo `search_order`.
- Ghi nhận: `make test-db` có `tests/acceptance/phase_05/test_email.py::test_smtp_failure_retried_then_failed_without_touching_experiment` fail cả trên `main` (test phụ thuộc ngày: `email_outbox.next_attempt_at` mặc định `now()` của Postgres, test dùng đồng hồ giả từ 2026-09-30; hỏng từ khoảng 09:40 UTC 2026-10-01). Cần giao sửa riêng.
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Chưa kiểm
- Luồng với API thật (endpoint tìm ngưỡng còn trả `501` tới Group 4); điểm toàn slice trúng cache của run quét lưới. Group 7.

### Phase 7 — Group 2 (ml-metric) — 2026-10-01
#### Thêm
- `ml_core/metrics/attack.py` (task 10, người dùng cho phép): `ImageAttackStats.class_correct`, `class_lost` (theo label, mặc định rỗng); `class_attack_success_rate`; `build_run_metrics(..., class_names=)` điền `per_class[*].attack_success_rate` (không truyền thì JSON như cũ).
- `ml_core/metrics/threshold.py` (task 10): `threshold_quantity(metrics, kind, class_filter)` cho 3 loại ngưỡng, có và không có class; `None` khi không tính được.
- `ml_core/metrics/bootstrap.py` (task 11, 12): định dạng file `runs/<run_id>/predictions.json`; `evaluation_evidence` (ghép COCO ở IoU 0.5 theo ảnh, box suy biến bị bỏ qua như pycocotools), `attack_evidence`; `average_precision_50` theo trọng số ảnh; `bootstrap_search` (`drop_ci`, KTC điểm gãy bằng nội suy, `near_threshold`).
- Test: 89 test trong `ml_core/metrics` (AP@0.5 khớp `CleanMetric` tới 1e-15 trên dữ liệu ngẫu nhiên và trên ảnh lặp lại; bootstrap không nạp torch).
#### Số liệu
- Bootstrap 200 mẫu × 12 điểm × 300 ảnh (dữ liệu tổng hợp, CPU máy phát triển): 0,3 s; dựng dữ liệu ghép trước 1,9 s.
- Lệch ban đầu với `CleanMetric` do torchmetrics truyền ngưỡng recall `torch.linspace` float32 (khác `np.linspace`): ghi cứng 101 giá trị, test so với torch.
#### Quyết định (đã ghi vào `requirements.md`, `plan.md`, `tech-stack.md`)
- Kế hoạch: Group 2 sửa `attack.py`; ghi file prediction khi chạy run chuyển sang Group 3 (task 13a); mẫu không cắt ngưỡng cắt về biên; `near_threshold` theo vế có nghĩa với `not_reached`, `below_min`.
- Review: #1 checkpoint của run phải lưu số đếm theo class (Group 3 task 13b); #2 mẫu NaN bị bỏ khỏi KTC; #3 ngưỡng recall ghi cứng (tech-stack 2.3); #4 KTC điểm gãy chỉ cho `found`/`non_monotonic`. Ghi nhận: `ImageAttackStats` không hash được (không chỗ nào hash).
- Review do cùng một agent làm (không độc lập).

### Phase 7 — Group 1 (ml-search) — 2026-10-01
#### Thêm
- `ml_core/search/subset.py` (task 5): `select_subset` (sắp theo `sha256({"purpose": "search_subset", "seed", "image_id"})`, slice không lớn hơn `subset_size` thì lấy cả slice), `eval_image_ids_sha256`.
- `ml_core/search/bounds.py` (task 6): `search_grid` (level thô; rời rạc chọn theo chỉ số, `lo`/`hi` phải là giá trị của spec), `bisect_steps`, `search_bounds` (tập con `m + s`, toàn slice `m + 1 + s`, slice nhỏ `m + s`). Chỉ import contract nên backend dùng được.
- `ml_core/search/algorithm.py` (task 7, 8): `ThresholdSearch.progress(observations, stop=, failure=)` chạy lại thuật toán trên các điểm đã đánh giá, trả điểm kế tiếp (`order` = `search_order`) hoặc kết quả cuối (`found`, `non_monotonic`, `not_reached`, `below_min`, `stopped_limit`, `failed` kèm thông điệp); level 0 là synthetic; mỗi cặp (level, tập ảnh) đánh giá một lần; `to_search_result`, `observations_from_trajectory` (chạy tiếp từ `SearchResult.trajectory`).
- Test (task 9): 58 unit test với hàm mức sụt tổng hợp, gồm test thuộc tính 400 hàm có nhiễu (số điểm không vượt giới hạn), chạy tiếp từ mọi điểm qua JSON của `SearchResult`, chạy lại mock `search_result/found.json`.
#### Quyết định (người dùng chốt ở kế hoạch Group 1; đã ghi vào `requirements.md`)
- Dịch từng ô thô tới khi đổi phía ngưỡng (kể cả khi xác nhận `lo`/`hi` cho kết quả ngược tập con); giới hạn toàn slice đổi từ `3 + s` thành `coarse_n + 1 + s` (PGD mặc định 20 → 23 điểm).
- Xác nhận mâu thuẫn (`d(a) ≥ ngưỡng`, `d(b) < ngưỡng`) → dịch xuống và gắn `non_monotonic`.
#### Review (phase-review, 2026-10-01)
- #1 (người dùng chọn sửa, agent ml-search): khoảng tạm thời ở giai đoạn xác nhận nhảy về `[lo, hi]` → giữ cận từ tập con khi điểm toàn slice chưa suy ra được; test mới fail trên code cũ.
- #2 (người dùng chọn sửa, người duyệt): `requirements.md` công thức giới hạn, quy tắc dịch, quét thô đủ mọi level, khóa tập con, quy tắc khoảng tạm thời; mock `search_result/*`, `search_result_report/*`, `experiment_detail/search_*`, `estimate_response/search_*`, bundle sinh lại theo công thức mới (đối chiếu từng mock với `search_bounds`: khớp). `estimate_response/search_pgd_fog` nay có `max_exceeds_limit = true` (7240 s > 7200 s).
- Ghi nhận (không ghi spec): `round()` làm tròn kiểu ngân hàng khi chọn chỉ số level thô rời rạc; khi cận dưới bằng 0 được xác nhận, quỹ đạo có điểm synthetic ở cả hai tập ảnh (báo frontend Group 6).
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 7 — Group 0 (người duyệt, người dùng giao) — 2026-10-01
#### Contract
- Enum: `SearchStatus.failed`; enum mới `SearchStage` (`coarse`, `bisect_subset`, `confirm`, `bisect_full`, `done`), `EvalScope` (`full`, `subset`).
- `SearchConfig`: `threshold` (0, 1], `tol < hi − lo`, `coarse_n` 3–8 (mặc định 4), `subset_size` ≥ 2 (mặc định 100), `class_filter: str | None` (thay `list[str]`), `bootstrap_samples` 0–1000 (mặc định 200).
- `RunResult`, `RunView`: `scope`, `search_order` (bắt buộc khi `scope = subset`), `predictions_key` (trong `runs/<run_id>/`). `FingerprintInputs.eval_image_ids_sha256` (null với run toàn slice). `ClassRunMetrics.attack_success_rate`.
- `SearchResult`: `stage`, `status` null khi chưa xong, `class_filter`, `metric_kind`, `max_points`, `points_used`, `message` (khi và chỉ khi `failed`); `breaking_point` cho `found` và `non_monotonic`, bằng `bracket[1]`. `TrajectoryPoint`: `drop_ci`, `synthetic`, `run_id` null khi synthetic.
- `EstimateResponse`: `searches[]` (`SearchEstimate`), `max_total_seconds`, `max_exceeds_limit`; `runs` được rỗng khi có `searches`. `ExperimentDetail.search_results`; `attack_ranking` chỉ gồm attack quét lưới. `WorkerJobBundle.search_results`, `runs` được rỗng khi mọi attack tìm ngưỡng; `BundleRun.scope`, `search_order`.
- Schema mới: `SearchRunCreate`, `SearchResultReport`. 61 JSON Schema.
- OpenAPI (endpoint khung trả `501`, Group 4 cài đặt): `POST /internal/worker/experiments/{id}/runs` (trả `BundleRun`, `201`); `POST .../search-result` đổi body thành `SearchResultReport`, trả `204`.
- **Hash cũ không đổi:** trường mới bỏ khỏi JSON khi mang giá trị mặc định (`exclude_if`); test kiểm `config_sha256`, fingerprint của manifest cũ và dump của run quét lưới.
- Mock: `SearchResult` đủ 6 trạng thái và một bản tạm thời (PGD L∞ KITTI 300 tập con 100 điểm gãy 0.5/255 với `tol` 0.125; fog rời rạc `non_monotonic`; occlusion ASR `not_reached`; FGSM `lo = 2` `below_min`; PGD L2 class `person` `stopped_limit`; class `truck` `failed`), `SearchResultReport`, `SearchRunCreate`, run tập con (`RunResult`, `RunView`, manifest có `eval_image_ids_sha256`), `AttackConfig` theo class ASR, experiment FGSM lưới + PGD và fog tìm ngưỡng (`ExperimentCreate`, `ExperimentDetail` đang chạy và xong), ước lượng (có lưới, chỉ tìm ngưỡng, thiếu profile), bundle chạy tiếp giữa giai đoạn quét thô (fixture 5 ảnh, tập con 3).
#### Thay đổi ngoài thư mục người duyệt (theo task Group 0)
- `backend/app/api/worker.py`: endpoint khung tạo run động, body mới của `search-result`.
- `frontend/src/components/status/status-config.ts`: nhãn "Thất bại" cho `SearchStatus.failed` (bảng `Record<SearchStatus, …>` phải đủ giá trị, nếu không `tsc` báo lỗi).
- Test: `contracts/python/tests/test_phase07_models.py` (38 test), `test_models.py` (`SearchResult` theo dạng mới), `test_enums.py`, `test_mocks.py` (cần cả bản tạm thời); `backend/app/tests/api/test_skeleton.py`; test nghiệm thu Phase 0 (`test_contracts.py` enum và độ phủ trạng thái, `test_api.py` endpoint worker và body của `search-result`).
#### Quyết định
- Kickoff (người dùng chốt, đã ghi vào spec Phase 7): vượt `max_points` trả `422`; `MAX_RUNS = 50` tính cả `max_points`; chi phí tối đa là trường riêng, chỉ cảnh báo; `tol` mặc định (hi − lo)/256; `subset_size` ≥ 2; `class_filter` một class. Bổ sung độ phủ: xếp hạng, `ordinal`, `early_stop`, migration `0008`, nháp wizard cũ, `failed`, hủy, hiển thị `below_min`.
- Group 0 (người duyệt tự chọn, ghi vào `requirements.md` mục "Chi tiết chốt ở Group 0"): `SearchResult` tạm thời có `status = null` và `stage`; worker dựng lại trạng thái tìm kiếm từ `trajectory` (không có checkpoint riêng); `search-result` mang `lease_id`; ASR theo class trong `ClassRunMetrics`; `metric_kind` 4 giá trị. `tech-stack.md` mục 3.3 và 4.3 thêm `failed`.
#### Số liệu
- `make test` (1184 test Python, 232 Vitest), `make test-acceptance` (264 test), `make test-db` (386 test), lint, mypy, `tsc`, `contracts-check`, `verify:build` pass. Ước lượng của mock (cost profile mock 1.229 s/ảnh): PGD tối đa 20 điểm, khoảng 93 phút.
#### Review (phase-review, 2026-10-01)
- #1 (chặn theo mặc định, người dùng chấp nhận): Group 0 sửa `status-config.ts` của agent frontend; ghi thành task 4a của `plan.md` (thêm enum thì thêm nhãn để `main` không đỏ).
- #2, #3 (người dùng chọn sửa): `bracket` của mock tạm thời sai (`[1, 2]` → `[0, 1]` ở 3 mock; bundle `[0, 16]` → `[0, 4]`); quy ước `bracket` là khoảng hẹp nhất suy ra từ các điểm đã có, kể cả khi quét thô (ghi vào `requirements.md`); test `test_mock_bracket_is_best_known_interval`.
- #4 (người dùng chọn sửa): `PassCriterion.class_filter` đổi thành `str | None` cùng kiểu `SearchConfig`.
- #5 (người dùng chọn ghi vào spec): `progress.images_total` chỉ tính run đã tạo; `queue.ahead_seconds` tính phần `max_seconds` còn lại của attack tìm ngưỡng (`requirements.md`, plan task 23, `validation.md`).
- Ghi nhận: sửa backend và test nghiệm thu Phase 0 theo tiền lệ Group 0 Phase 6; `tol` bắt buộc với tham số rời rạc; script sinh mock không commit.
- Sau khi sửa: `make check` (1191 test Python, 232 Vitest, 264 test nghiệm thu), `make test-e2e` (72 test, 6,8 phút) pass.
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Lưu ý
- Group 0 do agent làm thay người duyệt theo ủy quyền của người dùng; không độc lập.

---

## Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

**Trạng thái:** ✅ hoàn thành 2026-10-01, còn tồn đọng. Group 0–7 đã merge.

### Replan sau Phase 6 — 2026-10-01
- Phase 6 `requirements.md`: câu hỏi mở `rule_v1` đã trả lời (đủ, không cần `rule_v2`).
- Phase 7 `requirements.md` mục Context: loại attack tìm ngưỡng khỏi `attack_ranking`; `eval_image_ids_sha256` null với run toàn slice (giữ cache quét lưới); endpoint tạo run động trả `422`, không `409` (worker coi `409` là mất lease); `ordinal` và dừng sớm chỉ cho quét lưới; chốt run động có đếm vào `MAX_RUNS = 50`; `fog` dễ `non_monotonic`; nháp wizard `v2`.
- Phase 8 `requirements.md`: Context về case cũ bị ẩn trong report và case bắt buộc review, phương pháp làm mờ trong report, ảnh thứ ba theo `perturbation_kind`; câu hỏi mở mới về `max_drop_at_level` khi level bị `early_stop`.
- `roadmap.md`: lưới mịn eps nhỏ chuyển sang Phase 7 (gộp vào khoảng tìm kiếm PGD); stdout của CLI chuyển sang Phase 11; Phase 8 "heatmap nhiễu" đổi thành ảnh thứ ba theo loại biến đổi.
- Người dùng chấp nhận toàn bộ đề xuất.

### Phase 6 — Tổng kết (phase-close) — 2026-10-01
- **Giao được:** 7 spec mới (5 corruption severity 1–5 bằng bản vá imagecorruptions, `bbox_occlusion`, `adv_patch` train một lần bằng `RobustDPatch` trên slice huấn luyện không giao, lưu MinIO, dùng lại theo khóa patch, chạy tiếp từ checkpoint); seed theo ảnh; quét lưới thô → mịn, dừng sớm (`early_stop`, `POST /runs/{id}/skip`); xếp hạng `auc_drop`; làm mờ `rule_v1` cho mọi ảnh hiển thị và thumbnail trước khi upload; ước lượng có `training_seconds`; wizard ba nhóm attack, preset "Toàn bộ catalog", slice huấn luyện, công tắc dừng sớm; tab Kết quả có bảng xếp hạng, biểu đồ cột, trục chuẩn hóa; tiến độ hai giai đoạn của patch; trang `/admin/attacks`.
- **Contract:** Group 0 (trường Phase 6, `PatchArtifact`, endpoint nội bộ, 7 seed), đề xuất 001 (`TrainingParams.batch_size`, `adv_patch` version 2), 002 (`FailureCaseView.artifacts` null khi ẩn), 003 (`RunAttackSpec.param_max`). Người dùng chấp nhận roadmap, contract và seed catalog.
- **Số liệu cuối:** `make check` trên `72b7cb3` (lint, type check sạch; 1125 test Python, 231 Vitest, 264 test nghiệm thu không cần DB). Group 7: `make test-db` gồm 69 test nghiệm thu Phase 6 với worker CPU thật; `make test-e2e` 72 test, 4,5 phút. CI xanh trên `main` (người dùng xác nhận).
- **`validation.md`:** Automated Tests đủ; Manual Checks 7/7 (người dùng xác nhận đã làm và đạt); Definition of Done 5/6 (câu hỏi mở về `learning_rate` và `max_iter` của patch chưa ghi giá trị).
- **Câu hỏi mở:** `rule_v1` đủ che mặt và biển số trên KITTI (người dùng kiểm ≥ 20 case, không cần `rule_v2`). `learning_rate`, `max_iter` của patch: người dùng đã hiệu chỉnh, giá trị chưa ghi.
- **Tồn đọng (người dùng cho phép đóng phase, cập nhật sau):** số liệu của manual check chưa ghi (thời gian train patch, thời gian mỗi attack, bảng xếp hạng trên KITTI 300 ảnh; bất thường của mức sụt theo severity); giá trị `learning_rate`, `max_iter` sau hiệu chỉnh (nếu khác seed: đề xuất contract nâng `version` của `adv_patch`); ba mục chuyển tiếp chưa làm: lưới mịn ở eps nhỏ (Phase 2), sai số ước lượng PGD 300 ảnh (Phase 5), stdout của CLI khi Ultralytics import lần đầu (Phase 5). Mục "nên sửa" ở `ml_core/metrics/tests/test_ranking.py` vẫn mở.
- **Lưu ý:** Group 0, 7, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 6 — Group 7 (người duyệt) — 2026-10-01
#### Thêm
- `scripts/e2e.sh` (task 36a): `adv_patch` nạp với `max_iter = 4`, `checkpoint_every = 2` (cùng tên và version với seed, hash và id tính lại; chỉ trên DB tạm của E2E); slice đánh giá 3 ảnh và slice huấn luyện 2 ảnh không giao (`--exclude-slice`), vẫn giữ slice 5 ảnh của Phase 5.
- `tests/acceptance/phase_06/` (task 36): dùng lại hạ tầng của Phase 5 (nạp `phase_05/conftest.py` theo đường dẫn, cùng tên module); spec patch `max_iter = 4` riêng của test. 69 test:
  - thuật toán (không DB): seed theo ảnh, 5 corruption × 5 severity trên ảnh letterbox KITTI, occlusion, hình học và train patch trên YOLOv8n thật, vùng `rule_v1`, làm mờ, metric không đổi khi tắt làm mờ, quy tắc xếp hạng;
  - với worker CPU thật qua API: thứ tự thô → mịn, dừng sớm từ metric trong bundle (attack không được gọi cho level bị bỏ), `early_stop = false`, 409 khi `skip` run không `queued`, giới hạn sau lượt một, train → đăng ký → dùng lại patch (không train lại), chạy tiếp từ checkpoint sau khi worker chết, chạm giới hạn giữa lúc train, `patch_key` trong fingerprint, ước lượng có `training_seconds`, calibration của spec mới, ảnh trong MinIO đã làm mờ, `display_mode` và view bị ẩn không có khóa, quyền catalog admin;
  - chung: 7 spec mới hợp lệ, hash 3 spec cũ, fingerprint manifest và `config_sha256` của Phase 5 không đổi (dữ liệu mốc chép từ commit `99c81ff` vào `data/`), roadmap.
- `frontend/e2e/phase_06/` (task 36), 4 kịch bản × 3 viewport: experiment toàn catalog rút gọn chạy xong rồi xem bảng xếp hạng (thẻ ở 390px), biểu đồ cột, trục chuẩn hóa 0–100%, case fog có dải "Đã làm mờ" và nhãn "Vùng khác biệt"; wizard (nháp v1, preset 10 attack, `adv_patch` 0.1 và 0.25, chặn khi chưa chọn slice huấn luyện, chỉ liệt kê slice không giao, dừng sớm bật mặc định, thời gian train); run patch hiện "Đang train patch (x/4)"; `/admin/attacks` đủ 10 spec, engineer bị chuyển tới `/forbidden`.
#### Sửa lỗi (phát hiện khi viết test)
- Worker (vai trò agent worker, người dùng cho phép): batch đo calibration không có `image_id` nên corruption và occlusion ném lỗi; `calibrate` nằm ngoài `try` nên experiment kẹt ở `running` trên máy chưa có cost profile. Nay batch đo có `image_id` và `ignore_boxes` như `RunExecutor`; unit test và test nghiệm thu mới.
#### Quyết định (người dùng chốt ở Group 7; đã ghi vào spec)
- `fog` mức 3 và 4 của tham số gốc imagecorruptions cùng cường độ (2.5) nên mức khác biệt không tăng chặt giữa hai mức này; validation sửa: `fog` tăng 1 < 2 < 3, 4 < 5, 2 < 4, 1 < 5; `contrast` tăng ở mọi cặp mức. Đo trên KITTI: mức 4 thấp hơn mức 3 ở 5/6 seed.
- Task 37–38 (toàn catalog trên KITTI 300 ảnh, kiểm tra làm mờ bằng mắt): máy phát triển không còn KITTI đầy đủ và không có GPU; người dùng tự chạy sau theo hướng dẫn trong báo cáo Group 7.
- Ghi vào `requirements.md` (mục "Quyết định khi implement") các quyết định của Group 1–7; `validation.md` sửa câu chữ sai số patch (Group 2), thêm mục calibration corruption/occlusion, ghi giới hạn của E2E; `tech-stack.md` (bản vá imagecorruptions); `plan.md` (ml-privacy sửa `executor.py`); `roadmap.md` đánh dấu các mục tính năng.
#### Ghi nhận
- E2E không dựng được run `early_stop` trên fixture 3 ảnh: chỉ `bbox_occlusion` 0.9 (level lớn nhất) làm model sụp (0,049 mAP sạch, sát ngưỡng 0,05). Nhãn kiểm bằng Vitest, luồng kiểm bằng test nghiệm thu với worker thật.
- E2E chỉ kiểm "Đang train patch"; giai đoạn đánh giá 3 ảnh ngắn hơn chu kỳ cập nhật 2 giây của giao diện.
- Mục "nên sửa" ở `ml_core/metrics/tests/test_ranking.py` (thuộc agent ml-core) vẫn mở.
#### Số liệu
- `make test-e2e`: 72 test (60 của Phase 4–5, 12 của Phase 6), 4,5 phút. Test nghiệm thu Phase 6: 69 test, khoảng 1,5 phút trong `make test-db`.

### Phase 6 — Group 6 (frontend) — 2026-10-01
#### Thêm
- Wizard bước 4 (task 30): ba nhóm "Tấn công", "Biến đổi điều kiện", "Che khuất"; spec rời rạc (corruption) chọn severity bằng chip bật/tắt; attack cần train (patch) phải chọn slice huấn luyện từ `GET /slices?disjoint_from=<slice đánh giá>`, lọc cùng dataset version và ≤ `max_training_images` ảnh (chưa chọn thì không sang bước 5; đổi slice đánh giá hoặc dataset version thì chọn lại); nút "Toàn bộ catalog" (mọi spec với bộ level gợi ý, `adv_patch` 0.1 và 0.25: 43 run với catalog hiện tại); công tắc "Dừng sớm khi model đã sụp" bật mặc định (`early_stop` chỉ gửi khi tắt, body như Phase 5 khi bật). Nháp đổi khóa sang `advertest.wizard.v2`; attack trong nháp thiếu trường mới được điền mặc định. Nhân bản giữ slice huấn luyện và dừng sớm.
- Ước lượng (task 31): thời gian train patch ở bước 4 (cần train / đã có / chưa đo được) và cột "Train patch" trong bảng ước lượng bước 6.
- Tab Kết quả (task 32): bảng xếp hạng attack (auc_drop, mức sụt lớn nhất, số level kèm level dừng sớm, độ phủ, cờ partial; "Không đủ dữ liệu" khi null; thẻ dưới md) và biểu đồ cột `auc_drop`; công tắc trục hoành chuẩn hóa `level / param_max` (0–100%) cho mọi biểu đồ và cột "% dải" trong bảng số liệu; run `early_stop` ghi "Bỏ qua: model đã sụp ở level thấp hơn (sụp ở <tham số> <level>)" trong bảng run và đánh dấu trong bảng số liệu.
- Tiến độ run patch (task 33): "Đang train patch (x/y)" với thanh theo vòng lặp, rồi "Đang đánh giá" với thanh theo ảnh.
- `CaseViewer` (task 34): nhãn ảnh thứ ba theo `perturbation_kind` (Nhiễu khuếch đại / Vùng khác biệt / Vị trí patch); dải "Đã làm mờ mặt và biển số" khi `anonymization.applied`.
- Trang `/admin/attacks` (task 35): mọi spec và version (kể cả đã tắt), bảng từ xl và thẻ dưới xl, hash rút gọn có nút copy, "Tải thêm"; mục điều hướng "Attack catalog" (`attack_catalog.manage`, admin có 6 mục nên điện thoại 3 mục + "Thêm"). Chế độ mock có `/admin/attack-specs` và `disjoint_from`.
#### Đổi ngoài task
- Nhãn dataset chưa ẩn danh ở bước 3: "Chưa ẩn danh: ảnh failure case được làm mờ mặt và biển số" (trước: "ảnh failure case bị ẩn", không còn đúng với case mới từ Phase 6).
- Test `CaseViewer` Phase 5 chọn mock case chưa làm mờ (mock Phase 6 có ảnh thứ ba khác loại).
#### Đề xuất contract
- 003 (`RunAttackSpec.param_max`): người dùng duyệt, người duyệt áp dụng (đã merge vào `main`), dùng cho trục chuẩn hóa.
#### Quyết định (người dùng chốt ở kế hoạch Group 6; người duyệt ghi vào spec)
- Một công tắc dừng sớm chung cho mọi attack; nhân bản cấu hình có attack bật và attack tắt (chỉ tạo được qua API) thì công tắc tắt kèm ghi chú.
- Trục hoành chuẩn hóa áp cho biểu đồ từng attack (miền cố định 0–100%), không thêm biểu đồ gộp; chuẩn hóa `level / max` như bảng xếp hạng.
#### Ghi nhận
- E2E Phase 6 (`frontend/e2e/phase_06/`) do người duyệt viết ở Group 7; Group 6 kiểm bằng Vitest. E2E Phase 5 vẫn pass (60/60).
- Không tự chọn slice huấn luyện khi chỉ có một ứng viên (khác class mapping): người dùng chọn rõ ràng.

### Phase 6 — Đề xuất contract 003 (người duyệt, người dùng duyệt) — 2026-10-01
- Nguồn: Group 6 (frontend), task 32 "trục hoành chuẩn hóa": `RunView.attack_spec` không có dải tham số chính; engineer chỉ đọc được spec đang bật (`GET /attack-specs`), nên run của spec version đã tắt không chuẩn hóa được.
- `RunAttackSpec.param_max` (bắt buộc, `primary_param.max` của spec mà run đã dùng). `schema_version` không đổi; không đổi DB, hash, route.
- 43 mock `run_view` thêm `param_max` theo seed (khớp tên và version). Test `test_run_view_param_max_matches_spec`. Sinh lại JSON Schema, OpenAPI, type TypeScript.
- Việc tiếp theo: backend `_run_view` điền `param_max`; frontend dùng cho trục chuẩn hóa (`level / param_max`).

### Phase 6 — Đề xuất contract 002 (người duyệt, người dùng duyệt) — 2026-10-01
- Nguồn: Group 5 (backend), mục validation "`FailureCaseView` có `display_mode = hidden_unanonymized` không chứa khóa MinIO": `artifacts` của view kế thừa `CaseArtifacts` bắt buộc nên backend không bỏ khóa được.
- `FailureCaseView.artifacts: CaseArtifacts | None`, null khi và chỉ khi `display_mode = hidden_unanonymized` (validator kiểm). `FailureCaseRecord`, DB và dữ liệu worker gửi không đổi; `schema_version` không đổi.
- Mock `failure_case_view/hidden_unanonymized.json`: `artifacts = null`. Test `test_artifacts_null_iff_hidden`. Sinh lại JSON Schema, OpenAPI, type TypeScript (frontend không đọc `artifacts`).
- Việc tiếp theo: backend (nhánh `phase06-backend`) trả `artifacts = None` khi ảnh bị ẩn; Group 7 kiểm `artifacts is None` trong test nghiệm thu.

### Phase 6 — Group 5 (backend) — 2026-10-01
#### Thêm
- Migration `0007`: bảng `patches` (khóa patch, `artifact` hoặc `checkpoint_key`, không có cả hai; `GRANT SELECT, INSERT, UPDATE` cho `advertest_app`, không cấp `DELETE`); `cost_profiles.sec_per_image_iteration`; `failure_cases.anonymization`, `perturbation_kind`; `runs.phase`, `iterations_done`, `iterations_total`.
- Kiểm tra cấu hình (task 24): `attacks.{i}.training_slice_id` bắt buộc với spec cần train, cấm với spec khác; slice phải tồn tại, đã đăng ký, cùng dataset version với slice đánh giá, không giao, không quá `max_training_images` ảnh.
- Task 24a: run tạo theo thứ tự `coarse_to_fine` của từng attack. Task 24b: `GET /slices?disjoint_from=<id>` (slice không tồn tại → 404).
- Ước lượng (task 25): `training_seconds = max_iter × số ảnh slice huấn luyện × sec_per_image_iteration`, cộng vào tổng và kiểm giới hạn; null khi patch đã đăng ký hoặc profile chưa có số đo. Cost profile lưu `sec_per_image_iteration`.
- API nội bộ (task 26, 26a): bundle có `training_slices`, `patches`, `runs[].metrics`, `runs[].patch_key`; `POST /runs/{id}/skip` (chỉ run `queued`, run kích hoạt cùng experiment và attack, level nhỏ hơn, đã sụp theo `collapsed`; `status_reason` có `trigger_run_id`); `POST /runs/{id}/patch` (khóa phải khớp, file `.npy`, `.png` phải có; khóa đã đăng ký thì trả bản có sẵn); tiến độ `phase = training` lưu checkpoint patch (phải nằm dưới `patches/<key>/`) và số vòng; `artifact-url` cho thư mục patch của run; `complete` lưu `anonymization`, `perturbation_kind`.
- View (task 27, 28, 28a): `attack_ranking` bằng `ml_core.metrics.ranking.rank_attacks`; `RunView.phase` và `training`; `display_mode = normal` khi case có `anonymization.applied` (case cũ không có thì giữ quy tắc Phase 5); câu tóm tắt và email ghi "N bỏ qua (M do dừng sớm)".
- Task 29: `GET /admin/attack-specs` (mọi spec và version, kể cả spec đã tắt; phân trang keyset theo `(name, version)`, cursor sai → 422; chỉ `attack_catalog.manage`).
- Test: `test_migration_0007.py`, `test_phase06_api.py`, `test_phase06_worker_api.py`, `test_notifications.py`; `test_skeleton.py` chuyển endpoint đã làm khỏi danh sách 501.
#### Sửa test cũ (thư mục backend)
- `test_migration_0004.py` chèn attack spec có body hợp lệ thay vì `{}`: endpoint admin liệt kê cả spec đã tắt nên spec rỗng làm hỏng test khác dùng chung DB.
#### Đề xuất contract
- 002 (người dùng duyệt, người duyệt áp dụng ở `phase06-reviewer-p002`, merge vào nhánh này): `_view` trả `artifacts = None` khi `display_mode = hidden_unanonymized`.
#### Ghi nhận
- `make test-db` còn 2 test nghiệm thu Phase 5 fail: `test_failure_case_access.py::test_unanonymized_dataset_hides_every_image_but_keeps_boxes` và `::test_dev_flag_serves_unblurred_with_mode`. Worker Phase 6 làm mờ mọi case mới nên case có `anonymization.applied` → `normal` (`requirements.md` mục Làm mờ); hai test vẫn mong `hidden_unanonymized`, `dev_unblurred`. Người dùng chọn giữ code theo spec, người duyệt cập nhật test ở Group 7 (ví dụ kiểm trên case cũ không có `anonymization`).
- Chưa chạy worker end-to-end với luồng patch và `skip` trên API thật (Group 7, e2e `adv_patch` với `max_iter = 4`).
#### Quyết định nên ghi vào spec
- Cờ `DEV_ALLOW_UNBLURRED` không đổi `display_mode` của case đã làm mờ (vẫn `normal`).
- `training_seconds` null (không tính vào tổng) khi profile chưa có `sec_per_image_iteration`.
- `skip` sai trạng thái → 409; run kích hoạt không hợp lệ → 422.
#### Review (phase-review, 2026-10-01)
- #1 (chặn): patch đã đăng ký thì `artifact-url` chỉ cấp `GET` trong `patches/<key>/`, trừ `DELETE` trong `checkpoints/` (worker xóa checkpoint cuối sau khi đăng ký); `PUT` và xóa file patch → 403, để run khác cùng khóa không ghi đè hay xóa được patch.
- #3 (người dùng chọn sửa): `skip` tính lại bằng `ml_core.runner.grid.early_stop`: attack tắt `grid.early_stop` → 422; `trigger_run_id` phải là run kích hoạt (level nhỏ nhất đã sụp, metric đầy đủ: `completed` hoặc `skipped` do cache, không `partial`) và run bị bỏ phải nằm trong danh sách cần bỏ.
- #4 (người dùng chọn sửa): patch cần train mà profile chưa đo `sec_per_image_iteration` → run đó coi như thiếu profile (`sec_per_image`, `est_seconds` null), `total_seconds = null`, attack vào `missing_profiles` (đúng luật của `EstimateResponse`, không đổi contract).
- Test mới: `test_skip_rejected_when_early_stop_off`, trigger có metric một phần, URL sau khi đăng ký, view ẩn không có `artifacts`; `test_estimate_without_training_cost` viết lại theo #4.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 6 — Group 3, phần worker — 2026-10-01
#### Thêm
- Worker dựng perturbation bằng `attacks/factory.py`; `StoreCandidates` nhận `perturbation_kind(spec)`; fingerprint có `patch_key` của run patch (task 17).
- `advertest_worker/early_stop.py` (task 16): `RunLedger` giữ trạng thái và metric mọi run (từ `bundle.runs[].metrics`, cập nhật khi run trong phiên xong hoặc trúng cache); trước mỗi run `queued`, gọi `ml_core.runner.grid.early_stop` cho attack đó (theo `grid.early_stop`) rồi `POST /runs/{id}/skip` kèm `trigger_run_id`. Client thêm `skip`, `register_patch`.
- `advertest_worker/patch.py` (task 17): patch có sẵn thì tải và kiểm sha256; chưa có thì train trên slice huấn luyện (tiếp từ `checkpoint_key`), checkpoint `patches/<key>/checkpoints/<vòng>.npz` (vòng 0 trước lần báo đầu, bản cũ xóa sau khi API nhận bản mới; mất lease khi xóa thì dừng), mỗi vòng `ProgressReport` với `phase = training`; chỉ thị khác `continue` → run `cancelled` hoặc `stopped_limit` (0 ảnh), checkpoint giữ lại; train xong upload `.npy`, `.png`, đăng ký, API trả bản khác thì dùng bản đó.
- `JobCache.training_loader`: tải ảnh của slice huấn luyện. `JobRunner._patch_perturbation` nối luồng trên vào run.
- Calibration `adv_patch`: `sec_per_image` đo khi dán patch ngẫu nhiên ở `area_ratio` lớn nhất; `sec_per_image_iteration` đo bằng `measure_sec_per_image_iteration` trên tối đa `training.batch_size` ảnh.
- Test: `backend/worker/tests/test_early_stop.py`, `test_patch_flow.py` (client giả, store trong bộ nhớ, estimator giả: train mới, dùng patch có sẵn, chạy tiếp từ checkpoint cho cùng patch, dừng giữa lúc train, bản đăng ký của worker khác, mất lease), calibration patch trong `test_calibrate.py`.
#### Thay đổi ngoài thư mục (người dùng cho phép)
- `attacks/patch/artifact.py`: file patch đặt tên theo nội dung `patches/<key>/<patch_sha256>.npy|.png` (trước là `patch.npy`, `patch.png` cố định): hai worker cùng train một khóa không còn ghi đè file của nhau (test tái hiện lỗi sai sha256).
#### Ghi nhận
- Endpoint `skip`, `patch`, bundle có `patches`/`training_slices`, `artifact-url` cho `patches/` vẫn trả 501 tới Group 5: luồng mới mới kiểm bằng client giả; `JobRunner._patch_perturbation` chưa có test tích hợp với API thật (Group 7).
#### Review (phase-review, 2026-10-01)
- Người dùng yêu cầu sửa trước merge: #1 `gpu_seconds` của run patch thiếu thời gian train (API ghi đè bằng `RunResult.gpu_seconds`) → `obtain_patch` trả `training_seconds` (cộng dồn qua các lần chạy tiếp; 0 khi dùng patch có sẵn), `PatchInterrupted.seconds`, `_Finisher.extra_seconds` cộng vào `gpu_seconds`; #2 đối chiếu `run.patch_key` và `patch.area_ratio` của bundle với `compute_patch_key` và `run.level`, lệch thì run `failed`; #3 lỗi khi đo chi phí train `adv_patch` chỉ ghi cảnh báo, không dừng job. Test: `test_patch_job.py`, `test_training_seconds_reported_for_gpu_seconds`.
- Ghi nhận: 409 khi `skip` làm dừng cả experiment (client coi 409 là mất lease); luồng patch và `skip` chưa chạy với API thật.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 6 — Group 3, phần ml-core — 2026-10-01
#### Thêm
- `ml_core/runner/grid.py` (task 15): `coarse_to_fine` (`[2, 4, 8, 16, 32]` → `[2, 8, 32, 4, 16]`), `collapsed` (mAP@0.5 tấn công ≤ 5% mAP sạch; mAP sạch bằng 0 thì không coi là sụp), `early_stop` (run kích hoạt là level nhỏ nhất đã sụp, chỉ tính run có metric đầy đủ; bỏ mọi run `queued` có level lớn hơn trong cùng attack).
- `RunExecutor.process_batch` (task 15a): mỗi target có `image_id` và `ignore_boxes` (ART chỉ đọc `boxes`, `labels`).
- Task 17 (ml-core): `RunExecutor`, `Runner` nhận mọi `Perturbation`; `Runner` dựng bằng `attacks/factory.py` nên CLI `advertest run` chạy được corruption, occlusion; spec cần train (patch) bị từ chối khi đọc cấu hình ("chỉ chạy qua worker"); `linf_eps` trả `None` với phép biến đổi không phải attack ART.
- Task 18: `build_fingerprint_inputs(..., patch_key=)`; null thì fingerprint không đổi.
- Task 19: `ml_core/runner/images.py`: `difference_image` (`|δ| / max|δ|`), `perturbation_kind(spec)`, `third_image`; `StoreCandidates`, `MemoryCandidates` nhận `kind` (mặc định nhiễu khuếch đại), ảnh thứ ba vẫn đi qua làm mờ; `FailureCaseRecord.perturbation_kind` ghi theo `candidates.kind`.
- Task 20: `ml_core/metrics/ranking.py`: `rank_attack`, `rank_attacks` (hình thang từ (0, 0) trên `level / max`, level `early_stop` lấy `relative_drop` của `trigger_run_id`, không ngoại suy, dưới 2 điểm → null xếp cuối, `partial`); cho cùng kết quả với mock `experiment_detail/full_catalog` (tính độc lập bằng script sinh mock).
- Task 20a: `create_slice(..., exclude=)` và `advertest slice create --exclude-slice <id>` (lặp lại được, phải cùng dataset version).
#### Quyết định (người dùng chốt ở kế hoạch Group 3; người duyệt ghi vào spec)
- Group 3 chia hai nhánh tuần tự: `phase06-ml-core` rồi `phase06-worker`.
- Không dừng sớm khi mAP@0.5 sạch bằng 0 (không đánh giá được mức sụt).
- Test nghiệm thu Phase 2 `test_attack_labels_are_ground_truth` đòi target có đúng `{boxes, labels}`, mâu thuẫn contract Phase 6 (`image_id` bắt buộc): người dùng cho người duyệt sửa (commit `phase06(reviewer)` trong nhánh) thành có `boxes`, `labels`, `image_id`, chỉ thêm được `ignore_boxes`, vẫn cấm `scores`.
#### Ghi nhận
- Worker (nhánh sau) cần: truyền `perturbation_kind(spec)` cho `StoreCandidates`, dùng `attacks/factory.py`, `patch_key` trong fingerprint, gọi `early_stop` trước mỗi run.
- Level có metric nhưng `relative_drop = null` (mAP sạch bằng 0) đếm vào `levels_evaluated` nhưng không thành điểm của đường cong.

### Phase 6 — Group 4 (ml-privacy) — 2026-10-01
#### Thêm
- `ml_core/privacy/regions.py`: vùng `rule_v1` từ hợp ground truth, prediction sạch và prediction sau biến đổi (score ≥ 0,25): 1/3 trên của `person`, 40% dưới của `car`/`truck`, toàn bộ ignore region; cắt theo khung ảnh.
- `ml_core/privacy/blur.py`: mỗi vùng (mọi pixel chạm box) làm mờ Gaussian bán kính `max(8, 0,2 × cạnh ngắn)` px rồi pixelate khối `max(4, cạnh ngắn / 6)` px; ngoài vùng giữ nguyên; tất định. `METHOD = rule_v1`, `VERSION = 1`.
- `ml_core/privacy/case.py`: vùng của một ảnh từ prediction thô (mọi class của model, kể cả class không phải class đích) và `CaseAnonymization`.
- `ml_core/runner/candidates.py`: `add` nhận vùng làm mờ bắt buộc; ảnh sạch, ảnh sau biến đổi, ảnh thứ ba (tính từ ảnh chưa làm mờ) và thumbnail được làm mờ trước khi giữ trong RAM hay ghi vào store.
- `ml_core/runner/executor.py` (người dùng cho phép sửa tối thiểu): `_offer` tính vùng và truyền vào `add`, lưu số vùng trong `case_inputs` (có trong checkpoint); `_record` ghi `anonymization`. Checkpoint cũ không có số vùng → `anonymization = None` (ảnh ứng viên của nó chưa làm mờ).
- Test: `ml_core/privacy/tests/` (vùng, làm mờ trên ảnh có chi tiết, tích hợp với executor: mọi case có `anonymization` `rule_v1`, mọi ảnh hiển thị và thumbnail trùng đúng bản làm mờ tính lại từ dataset, ngoài vùng giống hệt ảnh gốc, metric không đổi khi tắt làm mờ, checkpoint cũ). Test của `ml_core/runner` cập nhật lời gọi `add`, `_offer`.
#### Ghi nhận
- Backend chưa lưu `anonymization` (bảng `failure_cases` chưa có cột; Group 5 task 28): tới lúc đó case vẫn `hidden_unanonymized` (an toàn).
- Ảnh của fixture executor là mảng màu phẳng nên làm mờ có thể không đổi pixel; việc làm mờ thay đổi ảnh có chi tiết kiểm tra ở `test_blur.py`.
#### Số liệu
- `make check`: 1088 test Python (+12), 201 Vitest, 211 test nghiệm thu không cần DB. `make test-db`: 354 test (gồm test nghiệm thu Phase 3, 5 với worker thật đi qua bước làm mờ).
#### Quyết định (người dùng chốt ở kế hoạch Group 4; người duyệt ghi vào spec)
- ml-privacy được sửa tối thiểu `executor.py` (`_offer`, `_record`) → `plan.md` phần phân chia thư mục.
- Vùng làm mờ dùng prediction thô mọi class (không chỉ class đích); làm mờ luôn áp cho case mới (không phụ thuộc `datasets.anonymized`).

### Phase 6 — Đề xuất contract 001 (người duyệt, người dùng duyệt) — 2026-10-01
- Nguồn: review Group 2 phát hiện #1: patch train ra phụ thuộc batch size (`v8DetectionLoss` trả `loss * batch_size`, chuẩn hóa theo cả batch), batch size lấy từ cost profile của từng máy, còn khóa patch và fingerprint không chứa batch size.
- `TrainingParams.batch_size` (bắt buộc); seed `adv_patch` lên version 2 với `batch_size = 8`, thay version 1 trong file seed (version 1 chưa có run nào). Hash của 9 spec còn lại không đổi; `schema_version` không đổi.
- Mock có `adv_patch` sinh lại (19 file: `id`, `spec_sha256`, `version`, khóa patch, fingerprint); `test_seeds.py` kiểm tra `batch_size` và version 2.
- DB dev đã seed trước đó còn dòng `adv_patch` version 1 đang bật: tắt tay hoặc dựng lại DB. DB của test và CI dựng mới.
- Số liệu: `make check` (lint, type check, 1047 test Python, 201 Vitest, 211 test nghiệm thu không cần DB).
- Việc tiếp theo: agent attack-patch cho `PatchTrainer` và `measure_sec_per_image_iteration` dùng `spec.training.batch_size` (nhánh `phase06-attack-patch`); Group 3 train patch không dùng batch size của cost profile; `scripts/e2e.sh` (task 36a) nạp `adv_patch` kèm `batch_size`.
### Phase 6 — Group 2 (attack-patch) — 2026-10-01
#### Thêm
- `attacks/patch/geometry.py`: `patch_key` (bọc `compute_patch_key`), vùng ảnh thật từ mask, phần giao vùng thật của slice huấn luyện, cạnh `round(sqrt(area_ratio × diện tích))`, vị trí ở tâm; `PatchDoesNotFit` khi không vừa.
- `attacks/patch/training.py`: `PatchTrainer` gọi `RobustDPatch` mỗi lần một vòng (`max_iter = 1`, giữ `attack._patch` giữa các lần gọi) để có checkpoint và tiến độ; patch khởi tạo theo `np.random.default_rng(seed)`; trạng thái `random` của ART lưu trong `TrainingState` nên train tiếp từ checkpoint cho cùng patch và cùng lịch sử như train liền; khôi phục `random` chung sau khi train; callback checkpoint ở vòng 0 và mỗi `checkpoint_every` vòng, callback tiến độ trả `False` thì dừng. Checkpoint là `.npz` không pickle, tự ghi số vòng đã xong.
- Giá trị mục tiêu: trung bình `compute_loss` trên ảnh huấn luyện đã dán patch (không biến đổi ngẫu nhiên) so với prediction ảnh sạch tính một lần.
- `attacks/patch/artifact.py`: `patch.npy` (float32, không pickle, `patch_sha256` là sha256 của file), `patch.png`, `build_artifact` tạo `PatchArtifact` (chỉ khi đủ `max_iter` vòng), `load_patch` kiểm tra sha256 và kích thước.
- `attacks/patch/adapter.py` (`PatchPerturbation`): dán patch vào tâm vùng ảnh thật của từng ảnh, `level` phải bằng `area_ratio` của patch, vùng pad giữ nguyên.
- `attacks/patch/calibration.py`: `measure_sec_per_image_iteration` (5 vòng, `area_ratio` lớn nhất).
- Theo đề xuất contract 001: `PatchTrainer` và `measure_sec_per_image_iteration` lấy batch size từ `spec.training.batch_size` (bỏ tham số `batch_size`), không từ cost profile.
- Test: 27 test mới trong `attacks/tests/` với estimator giả (diện tích, vị trí, mục tiêu tăng, train tiếp từ checkpoint khớp train liền, checkpoint ở 0 và mỗi n vòng, `PatchArtifact` hợp lệ, dán patch, đo chi phí).
#### Kiểm tra
- YOLOv8n thật trên 5 ảnh fixture (CPU), `area_ratio` 0,1 (cạnh 111): 10 vòng mất 12,8 giây (0,25 giây/ảnh/vòng); giá trị mục tiêu 4,06 → 4,94. Ước tính một patch 200 vòng trên slice 50 ảnh khoảng 42 phút trên CPU.
#### Số liệu
- `make check`: 1076 test Python (+29 so với trước group), 201 Vitest, 211 test nghiệm thu không cần DB.
#### Quyết định (người dùng chốt ở Group 2; người duyệt ghi vào spec)
- Kích thước và vị trí patch khi train theo phần giao vùng ảnh thật của slice huấn luyện; khi đánh giá đặt ở tâm vùng thật của từng ảnh.
- Giá trị mục tiêu là loss của detector trên ảnh đã dán patch.
- Sai số diện tích ±1% tính theo diện tích vùng ảnh thật (patch vuông cạnh nguyên không đạt ±1% tương đối ở tỉ lệ nhỏ: 0,02 trên KITTI lệch tối thiểu 1,2%) → sửa câu chữ trong `validation.md`.
#### Ghi nhận
- ART làm tròn ảnh về bội số của `learning_rate` ở bước chỉnh độ sáng (hành vi gốc); `patch_location` của ART là (hàng, cột), `patch_shape` là (C, H, W) khi `channels_first`.
- `attacks/factory.py` vẫn báo `UnsupportedAttack` cho `adv_patch`: adapter cần patch đã train, Group 3 dựng `PatchPerturbation` sau khi tra hoặc train patch.

#### Review (phase-review, 2026-10-01)
- Phát hiện #1 (người dùng chọn sửa): patch phụ thuộc batch size lấy từ cost profile → đề xuất contract 001 (người dùng duyệt, người duyệt áp dụng), code dùng `spec.training.batch_size`. Ghi nhận: `training_seconds` chưa tính lượt dự đoán ảnh sạch đầu mỗi lần train; giới hạn 50 ảnh do backend chặn; gán `attack._patch` (thuộc tính riêng của ART, kiểm tra lại khi nâng ART).
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 6 — Group 1 (attack-transform) — 2026-10-01
#### Thêm
- `attacks/common/seed.py`: `per_image_seed(seed, image_id)` (64 bit đầu của sha256 `canonical_json`), `image_rng`, `target_image_id`; `attacks/common/checks.py`: kiểm tra đầu vào chung, vùng ảnh thật theo mask.
- `attacks/corruptions/functions.py`: bản vá nội bộ của 5 hàm imagecorruptions 1.1.2 (Apache-2.0, `LICENSE.imagecorruptions`, ảnh `frost/`): `np.float_` → `np.float64`, số ngẫu nhiên lấy từ `np.random.Generator` truyền vào, đọc ảnh frost không cần `pkg_resources`. Hằng số giữ nguyên; cùng dãy số ngẫu nhiên thì kết quả trùng từng pixel với bản gốc ở 5 corruption × 5 severity (so bằng môi trường tạm).
- `attacks/corruptions/adapter.py` (`CorruptionPerturbation`): cắt vùng ảnh thật → uint8 (làm tròn) → corruption → float → đặt lại; mask = 0 giữ nguyên; mỗi ảnh một `rng` theo `image_id`; vùng thật nhỏ hơn 32 pixel báo lỗi.
- `attacks/occlusion/adapter.py` (`OcclusionPerturbation`): hình chữ nhật pixel nguyên nằm trọn trong box, kích thước nguyên gần `ratio` × diện tích box nhất (ưu tiên đúng tỉ lệ box), vị trí theo `rng` của ảnh, màu `fill_255`; không tô pixel chạm `ignore_boxes` (khóa tùy chọn trong target) và pixel mask = 0.
- `attacks/factory.py`: `build_perturbation(spec, estimator | None)` cho corruption, occlusion (không cần estimator) và attack ART; `adv_patch` báo `UnsupportedAttack` tới Group 2. `attacks.art_adapter.build_perturbation` giữ nguyên kiểu `ArtPerturbation` (ml_core và worker khai theo nó); Group 3 chuyển chỗ gọi.
- `pyproject.toml`: khai trực tiếp `opencv-python==5.0.0.93`, `scipy==1.17.1` (đã khóa qua ultralytics, `uv.lock` không đổi phiên bản); `scipy` vào danh sách `ignore_missing_imports` của mypy.
- Test: `attacks/tests/` thêm 164 test (seed, 5 × 5 × 4 kích thước, pad, dải giá trị, mức khác biệt tăng theo severity với fog và contrast, độc lập batch size và thứ tự, diện tích ±2%, ignore region, factory).
#### Kiểm tra
- 5 ảnh fixture KITTI (vùng thật 640x193): mỗi corruption ở severity 1, 3, 5 và occlusion 0,25/0,5/0,75 cho ảnh hợp lý, pad giữ nguyên (script tạm, không commit).
#### Quyết định (người dùng chốt ở kế hoạch Group 1; người duyệt ghi vào spec)
- imagecorruptions 1.1.2 lỗi (cần `pkg_resources`; `fog` dùng `np.float_`) → bản vá nội bộ; `tech-stack.md` mục 3 cần cập nhật.
- Occlusion đọc `ignore_boxes` tùy chọn trong target; Group 3 truyền cùng `image_id` (plan task 15a) và docstring `Perturbation` cần ghi.
#### Số liệu
- `make check`: 1046 test Python (+164), 201 Vitest, 211 test nghiệm thu không cần DB (không đổi so với trước group).
#### Review (phase-review, 2026-10-01)
- Người dùng yêu cầu sửa trước merge #1: target thiếu khóa `boxes` (hoặc `None`) làm occlusion lặng lẽ không che → nay báo lỗi; mảng rỗng vẫn hợp lệ (có test). Ghi nhận: unit test dùng ảnh giả lập (Group 7 phủ ảnh thật); seed > 2^53 − 1 bị `canonical_json` từ chối; `frost6.jpg` không dùng (giữ như bản gốc); `attacks/factory.py` nằm ngoài thư mục con của plan nhưng đã được duyệt ở kế hoạch; commit `5084517` lọt lỗi lint, sửa ở `b442481`.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 6 — Group 0 (người duyệt, người dùng giao) — 2026-10-01
#### Contract
- Enum: `AttackAccess.not_applicable`, `SkipReason.early_stop`; enum mới `RunPhase` (`training`, `evaluating`), `PerturbationImageKind` (`amplified_noise`, `difference`, `patch_location`).
- `AttackSpec`: `requires_training`, `training` (`TrainingParams`: `max_iter`, `learning_rate`, `sample_size`, `checkpoint_every`, `max_training_images`); attack không được có `access = not_applicable`.
- `AttackConfig.training_slice_id`, `GridConfig.early_stop` (mặc định `true`); `StatusReason.trigger_run_id` (khi và chỉ khi `early_stop`); `FingerprintInputs.patch_key`; `CostProfile.sec_per_image_iteration`; `ProgressReport.phase`, `iterations_done`, `iterations_total`; `EstimateRun.training_seconds` (cộng vào `total_seconds`); `FailureCaseRecord.perturbation_kind`; `FailureCaseRecord.anonymization` (`CaseAnonymization`); `ExperimentDetail.attack_ranking` (`AttackRankingEntry`, có `coverage`, `levels_early_stopped`); `RunView.phase`, `training` (`IterationProgress`); `RunView.fingerprint` được null với run `early_stop`.
- Schema mới: `PatchArtifact` (kèm `compute_patch_key`, `patch_prefix`), `PatchRegistration`, `RunSkipRequest`, `AttackSpecAdminView`, `AttackSpecAdminPage`; `WorkerJobBundle.training_slices`, `patches` (`BundlePatch`), `runs[].metrics`, `runs[].patch_key`. 59 JSON Schema.
- **Hash cũ không đổi:** trường mới mang giá trị mặc định bị bỏ khỏi JSON (`exclude_if`), JSON Schema không khai bắt buộc và không ghi `default` (openapi-typescript coi trường có `default` là luôn có mặt). Đã kiểm tra: `spec_sha256` của `fgsm`, `pgd_linf`, `pgd_l2` và nội dung seed cũ giữ nguyên.
- Seed: 7 spec mới (`fog`, `snow`, `frost`, `motion_blur`, `contrast` với severity rời rạc 1–5; `bbox_occlusion` 0–0.9; `adv_patch` `RobustDPatch` 0.02–0.25, `training` 200 / 0.02 / 1 / 50 / 50, `cost_model.cpu_only`).
- OpenAPI (endpoint khung trả `501`, Group 5 cài đặt): `GET /admin/attack-specs` (`attack_catalog.manage`), `POST /internal/worker/runs/{id}/skip`, `POST /internal/worker/runs/{id}/patch`.
- Mock: experiment toàn catalog (10 attack, 28 run: `early_stop` có `trigger_run_id`, `failed`, `stopped_limit` partial; `attack_ranking` có `auc_drop = null`, `partial`, tính bằng quy tắc hình thang), experiment patch đang train (`phase = training`, 120/200), run patch đang đánh giá, failure case đã làm mờ (vị trí patch, vùng khác biệt), `PatchArtifact`, `PatchRegistration`, `RunSkipRequest`, `ProgressReport` khi train, cost profile patch, ước lượng có `training_seconds`, manifest có `patch_key`, bundle chạy tiếp có slice huấn luyện, patch đang dở và run cần tính lại dừng sớm, trang catalog admin (10 spec), slice huấn luyện 50 ảnh.
#### Thay đổi ngoài thư mục người duyệt (theo task Group 0)
- `backend/migrations/versions/0006_attack_access_not_applicable.py`: thêm giá trị enum (seed mới phải nạp được; test enum khớp contract).
- `backend/app/api/public.py`, `worker.py`: 3 endpoint khung.
- Test: `backend/app/tests/api/test_skeleton.py` (endpoint worker và khung mới), `backend/app/tests/db/test_seed.py` (10 spec), `test_route_protection_db.py` (15 permission có route), `contracts/python/tests/test_seeds.py`, `test_enums.py`, test nghiệm thu Phase 0 (`test_contracts.py` enum, `test_api.py` endpoint worker).
#### Quyết định (đã ghi vào spec Phase 6)
- Kickoff (người dùng chốt): dừng sớm là hàm thuần ở ml-core, worker áp dụng, backend gán thứ tự; chi phí train theo ảnh × vòng lặp, slice huấn luyện ≤ 50 ảnh, preset 2 kích thước patch; `x = level / max`, không ngoại suy; làm mờ cả ảnh thứ ba; E2E dùng `adv_patch` với `max_iter = 4`.
- Group 0 (người duyệt tự chọn, ghi vào `requirements.md` mục "Chi tiết chốt ở Group 0"): trường mới không đổi hash cũ; `trigger_run_id` để xếp hạng biết run kích hoạt; level `early_stop` được đếm là điểm của đường cong (attack sụp ngay ở level đầu không bị xếp cuối); tiến độ train dùng `ProgressReport` với checkpoint ở vòng 0; `perturbation_kind` ở cấp case (không đặt trong `artifacts`, vốn chỉ chứa khóa MinIO); trang admin phân trang; migration `0006` chỉ gồm enum.
- Phát hiện khi làm: chưa có cách tạo slice huấn luyện không giao (CLI chỉ chọn ngẫu nhiên từ dataset) → thêm task 20a (`slice create --exclude-slice`), 24b (`GET /slices?disjoint_from=`), 36a (fixture 5 ảnh phải tách slice đánh giá và slice huấn luyện).
- `roadmap.md`: Phase 6 đổi tên, thêm xếp hạng và làm mờ (chuyển từ Phase 10), phụ thuộc 3 và 5; bảng Tổng quan đánh dấu Phase 5 ✅.
#### Số liệu
- `make check` (lint, type check, `contracts-check`, 862 test Python, 201 Vitest, 211 test nghiệm thu không cần DB), `make test-db` (354 test), `verify:build` đều pass.
#### Review (phase-review, 2026-10-01)
- Không có phát hiện chặn. Người dùng yêu cầu sửa trước merge: #1 thiếu test cho ca sai của validator mới và cho việc bỏ trường mặc định → thêm `contracts/python/tests/test_phase06_models.py` (20 test: hash spec, config, fingerprint cũ không đổi; trường bỏ được không bắt buộc, không có `default`; luật `training`, `trigger_run_id`, `phase`, `PatchArtifact`, `BundlePatch`, bundle, `ProgressReport`, `training_seconds`, xếp hạng, mock làm mờ); #2 mô tả `exceeds_limit` nói rõ cộng `training_seconds`; #3 `WorkerJobBundle` kiểm tra slice huấn luyện cùng dataset version và không giao với slice đánh giá.
- Người dùng chấp nhận (đã có trong spec): #8 `--exclude-slice` và `disjoint_from` (task 20a, 24b); #9 level `early_stop` được đếm vào ngưỡng 2 điểm của `auc_drop`.
- Ghi nhận cho group sau: Group 5 thêm xác thực token cho `skip`, `patch`; sau merge, wizard cho chọn spec Phase 6 trước khi worker có adapter (run `failed` cho tới Group 1, 2, 5); `downgrade` của `0006` lỗi nếu đã có run dùng spec mới; `learning_rate` là giá trị tạm; bảng Tổng quan của roadmap sửa khi đóng phase.
- `make test-e2e`: 60 test pass. Sau khi sửa: 882 test Python.
#### Lưu ý
- Group 0 do agent làm thay người duyệt theo ủy quyền của người dùng; không độc lập.

---

## Phase 5 — Wizard tạo experiment và theo dõi tiến độ

**Trạng thái:** ✅ hoàn thành 2026-09-30, còn tồn đọng. Group 0–7 đã merge.

### Replan sau Phase 5 — 2026-09-30
- Phase 6 `requirements.md` mục Context: ghi các giả định từ code Phase 5 (`display_mode` tính trong `artifacts.py`, cần lưu `anonymization` và bỏ khóa MinIO khi ẩn; `training_seconds` cộng vào `total_seconds` và `exceeds_limit`; preset "Toàn bộ catalog" khoảng 45 run sát trần 50; nháp wizard `v1` gộp nông; E2E trúng cache, máy `e2e-offline`; `early_stop` đếm vào "bỏ qua").
- Phase 7 `requirements.md` mục Context: `not_supported_yet` hiện áp mọi spec; `max_seconds` phải ghép với `total_seconds` và `exceeds_limit`.
- `roadmap.md`: Phase 6 thêm đo sai số ước lượng PGD 300 ảnh (tồn đọng Phase 5) và lỗi stdout của CLI khi Ultralytics import lần đầu; Phase 11 thêm khả năng tiếp cận của box trên canvas và nháp wizard có tài nguyên đã xóa.
- Người dùng chấp nhận toàn bộ đề xuất.

### Phase 5 — Tổng kết (phase-close) — 2026-09-30
- **Giao được:** API experiment (tạo có kiểm tra cấu hình `422` kèm `fields`, ước lượng từ cost profile `images × spp × 1.2`, xem, hủy, nhân bản, giới hạn 3 experiment đang chờ, tên mặc định do DB đặt); đọc tài nguyên cho wizard; URL ảnh `/artifacts/<token>` (HMAC 10 phút, cần phiên), `display_mode` theo `anonymized` và `DEV_ALLOW_UNBLURRED`; email khi kết thúc qua outbox (Mailpit ở dev); frontend wizard 6 bước giữ nháp, danh sách và chi tiết experiment 5 tab (tiến độ polling, biểu đồ Recharts, failure case có watermark, chi phí, tái lập), trình xem case (zoom, slider, vuốt), khối engineer trên `/home`.
- **Contract:** 3 `ErrorCode` mới, `DisplayMode`, `ErrorBody.fields`, 15 schema, OpenAPI các route Phase 5; đề xuất 001 (`RunView.fingerprint` được null khi run chưa bắt đầu). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` (804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest), `make test-db` (353 test, gồm 36 test nghiệm thu Phase 5 với worker CPU thật), `make test-e2e` (60 test, gồm 21 test Phase 5 = 7 kịch bản × 3 viewport, khoảng 2 phút).
- **`validation.md`:** Automated Tests đủ; Manual Checks 6/7 (người dùng xác nhận); Definition of Done 4/5.
- **CI:** xanh trên `68cf796` gồm job `e2e` với worker thật (sau khi sửa `e2e.sh`; người dùng xác nhận, kiểm tra qua GitHub API).
- **Tồn đọng (cập nhật khi có kết quả):** manual check PGD eps 2/4/8/16 trên slice KITTI 300 ảnh qua wizard; sai số ước lượng so với thời gian thực tế chưa đo.
- **Chuyển tiếp (không chặn):** khóa MinIO trong `FailureCaseView.artifacts` vẫn trả khi ảnh bị ẩn; box trên canvas chưa đọc được bằng trình đọc màn hình; nháp cũ có model/slice đã xóa chỉ báo qua `422`; CLI `advertest` có thể lẫn thông báo của Ultralytics vào stdout ở lần đầu (xem replan).
- **Lưu ý:** Group 0, 7, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 5 — Group 7 (người duyệt, người dùng giao) — 2026-09-30
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_05/` (36 test `db`, worker CPU thật qua `JobRunner`, fixture KITTI 5 ảnh và YOLOv8n): kiểm tra cấu hình (`422` có `fields`), ước lượng, giới hạn 3 experiment đang chờ, vòng đời (hủy khi đang `running` sau batch đầu, `finished_at`; chuyển từ Group 2; tên mặc định; giới hạn 28800 được chấp nhận), cache theo fingerprint, URL ảnh (token, hết hạn, cần phiên), `display_mode`, email qua outbox (thử lại rồi `failed`), đọc tài nguyên. Spec tự tạo có nội dung không hợp lệ đặt `is_active = false` (task 33).
- E2E `frontend/e2e/phase_05/` (7 kịch bản × 3 viewport = 21): đi hết wizard (seed 0 ở bước 6) → chi tiết → tiến độ tự cập nhật → kết quả (biểu đồ) → chi phí → failure case (watermark, dải cảnh báo dev, bật tắt lớp box, slider trên điện thoại) → tái lập (fingerprint, tải manifest); giữ nháp khi tải lại; level ngoài dải chặn bước 4; nhân bản mở bước 6; reviewer không thấy "Tạo experiment"; hủy qua hộp xác nhận; `/home` có khối experiment đang chờ và lần gửi thứ 4 báo `queue_limit_reached`.
- `scripts/e2e.sh` (task 3a): dựng dữ liệu fixture bằng CLI và `import-local`, tạo bucket MinIO, chạy worker CPU thật cho `local-dev`, máy `e2e-offline` không có worker, `DEV_ALLOW_UNBLURRED=true`, không gửi email; in log worker khi fail. CI job e2e thêm MinIO và fixture.
#### Phát hiện khi làm
- Viewport chạy sau dùng cùng cấu hình nên run trúng cache: E2E chờ trạng thái `completed` và chấp nhận câu "0/2 hoàn thành, 2 bỏ qua".
- Chạy chung `make test-db`: MinIO còn object của Phase 3 (card cùng key, khác thời điểm đăng ký) → `KeyConflictError`; fixture Phase 5 dọn bucket khi dựng lại DB.
- CI job e2e fail lần đầu (sau merge): Ultralytics lần đầu import in thông báo tạo settings ra stdout, lẫn vào JSON của CLI `advertest` mà `e2e.sh` đọc. `e2e.sh` dùng `YOLO_CONFIG_DIR` riêng và import trước một lần (máy local nay chạy như CI).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest. `make test-db`: 353 test. `make test-e2e`: 60 test trong khoảng 2,3 phút.
#### Chưa làm (cần người dùng, task 34)
- KITTI 300 ảnh, PGD eps 2/4/8/16 qua wizard (ghi sai số ước lượng); theo dõi trên điện thoại thật; email trong Mailpit và bấm link; ảnh chưa làm mờ bị ẩn, bật cờ dev thì hiện kèm dải cảnh báo; pinch-zoom, slider, vuốt; iPhone (thanh dưới không bị thanh home che, ô nhập không tự zoom); biểu đồ chế độ sáng và tối. Máy phát triển không có GPU.
#### Review
- Phát hiện chặn (đã sửa trước merge): thiếu 5 mục validation — tên mặc định và giới hạn 28800 (test nghiệm thu), seed 0 ở bước 6, `queue_limit_reached`, `/home` và tab Chi phí (E2E). Ghi vào spec (người dùng chốt): E2E chấp nhận run trúng cache giữa các viewport, máy `e2e-offline` (`validation.md`); fixture dọn MinIO khi dựng lại DB (`plan.md` task 33).
#### Lưu ý
- Test nghiệm thu, E2E và sửa script do agent làm thay người duyệt theo ủy quyền của người dùng (không độc lập).

### Phase 5 — Group 6 (frontend) — 2026-09-30
#### Thêm
- `/experiments`: lọc Của tôi / Tất cả, trạng thái, model; bảng (≥ 1280px) / thẻ; Tải thêm; polling khi còn experiment đang chạy.
- `/experiments/:id`: 5 tab (Tổng quan, Kết quả, Failure case, Chi phí, Tái lập) giữ trên `?tab=`; Hủy (chủ sở hữu, `queued`/`running`, hộp xác nhận); Nhân bản mở wizard `?clone=`; tab Failure case có watermark và ô "Ảnh bị ẩn"; tab Tái lập có fingerprint rút gọn, git commit, cảnh báo `git_dirty`, phiên bản thư viện, Docker image, môi trường, tải `manifest.json`.
- `/failure-cases/:id`: `CaseViewer`, chuyển case trong run (`?run=`), xin lại URL khi ảnh lỗi.
- `/home`: khối engineer (đang chạy hoặc chờ, 5 kết thúc gần nhất, nút tạo).
- Điều hướng: bật "Experiment", thêm "Tạo experiment"; `AppShell` tự tính mục đang sáng (có đường dẫn loại trừ). Vitest 187 → 201.
#### Thay đổi
- Test điều hướng và `/home` (Vitest) theo điều hướng mới; E2E Phase 4 `onboarding.spec.ts`: engineer có 4 mục (commit `phase05(reviewer)`, task 37, người dùng cho phép).
#### Kiểm tra
- Chromium 390/820/1440 với mock: 10 trang không cuộn ngang, không lỗi console; `make test-e2e` 39/39.
#### Quyết định (đã ghi vào `requirements.md`)
- Người dùng chốt: sửa `router.tsx`, `nav/config.ts`, `HomePage.tsx`, `AppShell.tsx`, E2E Phase 4.
- Agent chọn, người duyệt chấp nhận ở review: bộ lọc mặc định theo quyền, tab trên URL, `?run=` cho trình xem, khối `/home` từ 50 experiment mới nhất.
#### Review
- Phát hiện #1 (sửa trước merge): trình xem mở không có `?run=` gọi `GET /runs/` rỗng → `useRun` chỉ gọi khi có id (có test). Ghi nhận: luồng với backend thật (hủy khi đang chạy, tiến độ, tải manifest) chờ E2E Group 7; bảng "Thêm" của admin trên điện thoại chưa có E2E thao tác.
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest; `verify:build` pass; `make test-e2e` 39 test.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 5 (frontend) — 2026-09-30
#### Thêm
- `features/wizard/`: wizard 6 bước tại `/experiments/new` (chặn theo `experiment.create`): thanh bước, cột tóm tắt (desktop), thanh dưới cố định nằm trên thanh tab điều hướng (điện thoại); nháp `sessionStorage` (`advertest.wizard.v1`), xóa khi tạo thành công; protocol, model, dataset version và slice (class mapping tự chọn khi chỉ có một, báo lỗi khi không có), attack với chip level (kiểm dải, trùng, tối đa 12) và bộ gợi ý, "Tự tìm ngưỡng" hiện "Sắp có", máy chạy và giới hạn (phút); ước lượng debounce 500 ms; bước 6 tóm tắt, ước lượng từng run, ô tên, hộp xác nhận; lỗi 422 về đúng bước và trường, 409 `queue_limit_reached` giữ nháp; nhân bản `?clone=<id>` mở bước 6 kèm cảnh báo.
- `ApiError.fields`; chế độ mock trả `POST /experiments/estimate`. Vitest 151 → 187.
#### Kiểm tra
- Chromium 390 và 1440 với mock: đi hết wizard, level ngoài dải chặn bước 4, tải lại giữ nháp, hộp xác nhận, nhân bản mở bước 6, không cuộn ngang. Phát hiện và sửa: thanh tab điều hướng của khung ứng dụng che thanh dưới của wizard trên điện thoại.
#### Quyết định (đã ghi vào `requirements.md`)
- Người dùng chốt: sửa `router.tsx`, `api/errors.ts`, `api/mocks.ts`; chọn sẵn máy local.
- Agent chọn, người duyệt chấp nhận ở review: tự chọn protocol duy nhất, giới hạn theo phút, bộ level gợi ý, bỏ lựa chọn phụ thuộc khi đổi model/dataset, ô tên tùy chọn.
#### Review
- Phát hiện #1 (sửa trước merge): lỗi ô nhập level của attack đã bỏ chọn vẫn khóa nút "Tiếp" → chỉ tính attack đang chọn (có test). Sửa kèm: tên không thuộc body ước lượng; nhân bản báo lỗi khi không tải được slice. Ghi nhận: nháp cũ có model/slice đã xóa chỉ được báo qua 422 (xem lại ở Phase 11).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 187 Vitest; `verify:build` pass.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 4 (frontend) — 2026-09-30
#### Thêm
- `features/experiments/api.ts`: hook experiment, danh sách (Tải thêm), run, manifest, failure case; polling 2 giây khi `queued`/`running`, dừng ở trạng thái cuối, tạm dừng khi tab ẩn; xin lại URL ảnh trước khi hết hạn 60 giây và khi ảnh tải lỗi (một lần mỗi bộ URL); `artifactSrc` thêm `VITE_API_BASE_URL`.
- `statusSentence` và `ExperimentStatusSummary` (cùng cách viết với email).
- `components/charts/MetricCurves`: mỗi attack một khối (mAP@0.5 có đường mAP sạch, tỷ lệ tấn công thành công), run `partial` đánh dấu, bảng số liệu, tab trên điện thoại.
- `components/case-viewer/CaseViewer`: cạnh nhau có zoom đồng bộ (desktop), slider + pinch-zoom + vuốt (điện thoại), 4 lớp box trên canvas theo `devicePixelRatio`, object bị mất tô đỏ, ảnh nhiễu, watermark, khung giữ chỗ `hidden_unanonymized`, dải cảnh báo `dev_unblurred`, slot `aside` cho Phase 8.
- Mock mọi GET của Phase 5 (`src/api/mocks.ts`); `useRun` dừng polling khi run kết thúc (từ Phase 0).
- Dependency: `recharts` 3.10.1, `react-is` 19.2.8 (peer của Recharts), `react-zoom-pan-pinch` 4.2.0. Vitest 103 → 151.
#### Kiểm tra
- Chromium 3 viewport với mock (trang thử tạm, không commit): không cuộn ngang, không lỗi console, Recharts render, slider chỉ ở 390px, canvas theo DPR.
#### Quyết định (đã ghi vào `requirements.md`, `tech-stack.md`)
- Người dùng chốt: sửa `src/api/mocks.ts`, `queries.ts`; bố cục biểu đồ mỗi attack một khối.
- Agent chọn, người duyệt chấp nhận ở review: định nghĩa object bị mất; ngưỡng nhãn; xin lại URL; vuốt; màu box cố định.
#### Review
- Phát hiện #1 (sửa trước merge): cột `aside` chiếm chỗ khi không có form, khung ảnh desktop ~450px nên nhãn box bị ẩn → cột chỉ có khi có `aside`, nhãn theo màn hình từ 768px (khung 618px ở 1440px). Ghi nhận: tương tác zoom/pinch/vuốt chưa thử thật (E2E Group 7, manual); box trên canvas không đọc được bằng trình đọc màn hình (xem lại ở Phase 11).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 151 Vitest; `verify:build` pass.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 3 (backend) — 2026-09-30
#### Thêm
- `backend/app/services/notifications.py`: mẫu email tiếng Việt (HTML và văn bản, escape tên), thêm vào `email_outbox` trong cùng transaction khi experiment chuyển `completed` (`runs._after_run`) hoặc `cancelled` (`experiments.cancel`, cả API và CLI); `deliver_due` (SKIP LOCKED, backoff 30/60/120/240 giây, `failed` sau 5 lần, `last_error`); gửi bằng `smtplib` (không thêm dependency); vòng nền 10 giây trong `lifespan` khi có `SMTP_HOST`.
- Mailpit trong `docker/compose.yaml` (pin digest, giao diện `127.0.0.1:8025`); biến `SMTP_*` cho API và `.env.example`.
- Test: `tests/test_notifications.py` (nội dung, câu tóm tắt, escape, SMTP giả), `tests/db/test_email_outbox.py` (completed/cancelled/rollback, backoff, `failed`, trạng thái experiment không đổi).
#### Kiểm tra
- Gửi thật qua container Mailpit tạm: nhận đúng tiêu đề và nội dung tiếng Việt.
#### Quyết định (đã ghi vào `requirements.md` Phase 5, mục Email)
- Câu tóm tắt, tiêu đề, link; email hủy gửi ngay lúc hủy; không có `SMTP_HOST` thì chờ; backoff; gửi có thể trùng khi commit lỗi (không mất); Mailpit `v1.27`.
#### Review
- Không có phát hiện chặn. Ghi nhận: vòng nền không có test tự động (manual check với `make up`); API chạy ngoài Docker cần bỏ trống `SMTP_HOST`.
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 317 test.
#### Lưu ý
- Code, review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 2 (backend) — 2026-09-30
#### Thêm
- `services/experiment_config.py`: kiểm tra cấu hình dùng chung cho ước lượng và tạo, gom mọi lỗi với đường dẫn trường (`InvalidConfig` → `422 invalid_request` hoặc `not_supported_yet`); lỗi sai schema cũng trả `fields`.
- Ước lượng theo run (`skip_reason = incompatible`, `missing_profiles`, `exceeds_limit` theo cận dưới, `queue.position`, `ahead_seconds`); `POST /experiments/estimate`.
- `POST /experiments` (dùng chung `create_experiment` với CLI `submit`; giới hạn 3 experiment `queued` có khóa dòng user → `409 queue_limit_reached`); `GET /experiments` (lọc `owner`, `status`, `model`, keyset), `GET /experiments/{id}`, `/runs`, `GET /runs/{id}`, `/runs/{id}/manifest`, `POST /experiments/{id}/cancel` (chỉ chủ sở hữu), `GET /experiments/{id}/clone`.
- `services/artifacts.py`: URL ảnh `/artifacts/<token>` (HMAC, 10 phút, chỉ khóa `runs/`), `display_mode` theo `anonymized` và `DEV_ALLOW_UNBLURRED`; `GET /runs/{id}/failure-cases` (thumbnail), `GET /failure-cases/{id}`, `GET /artifacts/{token}` (cần phiên).
- `finished_at` khi `completed` và khi hủy; migration `0005` điền lại `finished_at` còn thiếu.
- `ARTIFACT_TOKEN_SECRET`, `DEV_ALLOW_UNBLURRED` trong compose và `.env.example`.
- Test: `test_experiment_api.py` (29 test, Postgres và MinIO thật).
#### Contract (đề xuất 001, người dùng duyệt)
- `RunView.fingerprint` null khi và chỉ khi run chưa bắt đầu; `RunResult` của worker giữ nguyên (lớp cơ sở chung `_RunCommon`). Mock `run_view` cập nhật, thêm test contract.
#### Thay đổi
- Test nghiệm thu Phase 0 (`IMPLEMENTED_GROUPS` thêm `/experiments`, `/runs`, `/failure-cases`) và Phase 4 (`POST /experiments` đại diện `experiment.create` nay trả `422 invalid_request`): commit `phase05(reviewer)`, người dùng cho phép. Test backend `test_errors.py`: chỉ lỗi `422` có `fields`, không lặp lại giá trị gửi lên ở bất kỳ đâu trong body (review #1).
#### Quyết định (đã ghi vào `requirements.md` Phase 5)
- Người dùng chốt: đề xuất 001; khóa token từ biến môi trường; sửa test nghiệm thu trong nhánh.
- Agent chọn, người duyệt chấp nhận ở review: `fields` cho lỗi sai schema; từ chối attack spec trùng; hàng đợi chỉ `queued`, thứ tự `submitted_at`, `id`; ước lượng không kiểm giới hạn 3; `GET /runs/{id}`; chi tiết URL ảnh (khóa `runs/`, đọc trọn, `Cache-Control`, thumbnail dự phòng); nhân bản giữ spec cũ khi không có version mới.
#### Phát hiện khi làm
- Route ảnh và manifest mở MinIO trước khi kiểm tra token/run (token sai → `500` khi thiếu cấu hình MinIO): nay chỉ đọc MinIO sau khi hợp lệ.
#### Số liệu
- `make check`: 796 test Python, 209 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 312 test.
#### Chuyển cho Group 7
- Test API hủy experiment đang `running` (validation "worker dừng").
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 1 (backend) — 2026-09-29
#### Thêm
- Migration `0004`: `compute_targets.max_time_limit_s` (mặc định 28800, CHECK mặc định ≤ tối đa); `experiments.created_at` (điền `submitted_at`, index `(created_at, id)`), `name` NOT NULL (trigger `experiments_default_name` đặt `<model> · <slice> · <ngày UTC>` khi bỏ trống; experiment cũ điền cùng quy tắc), `cloned_from`, `finished_at` (experiment cũ đã kết thúc lấy thời điểm run cuối cùng xong); bảng `email_outbox` (có `next_attempt_at`; app không xóa được).
- `advertest-admin compute-target create --max-time-limit`, `compute-target set-limits` (audit `compute_target.update_limits`), `list` in giới hạn tối đa.
- `backend/app/services/catalog.py` và route `GET /models`, `/models/{id}`, `/datasets`, `/dataset-versions/{id}`, `/slices`, `/class-mappings`, `/attack-specs` (chỉ đang hoạt động), `/protocols` (`active`, `dev`), `/compute-targets` (`online` theo heartbeat 60 giây, `queue_length` đếm `queued`); `404` khi không có.
- API nội bộ của worker khai `422` là `ErrorResponse` (task 5a); OpenAPI không còn `HTTPValidationError`.
- Test: `test_migration_0004.py` (nâng từ 0003 với dữ liệu kiểu Phase 3), `test_catalog_api.py`, `set-limits` ở service và CLI.
#### Thay đổi
- Test nghiệm thu Phase 0 `test_api.py`: `IMPLEMENTED_GROUPS` thêm 6 nhóm (commit `phase05(reviewer)`, người dùng cho phép). Test backend: `SAMPLE_CALLS`, test CSRF cho GET dùng `/budget` (route còn là khung).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 5)
- `email_outbox.next_attempt_at`; người duyệt cập nhật `IMPLEMENTED_GROUPS` trong nhánh.
- Review: `GET /attack-specs` giữ nghiêm (spec hỏng → `500`), dữ liệu test tự tạo spec rỗng phải `is_active = false` (`plan.md` task 33); Group 2 điền lại `finished_at` còn thiếu (task 13).
- Agent tự chọn, người duyệt chấp nhận ở review: tên mặc định bằng trigger DB (để test Phase 0 chèn experiment không tên vẫn chạy); `queue_length` chỉ đếm `queued`; lệnh `set-limits`.
#### Số liệu
- `make check`: 801 test Python, 212 test nghiệm thu không cần DB (6 nhóm khung ít hơn), 103 Vitest. `make test-db`: 283 test.
#### Lưu ý
- Code, review và ghi spec do cùng một agent làm (review không độc lập).

### Phase 5 — Group 0 (người duyệt, người dùng giao) — 2026-09-29
#### Contract
- `ErrorCode` thêm `not_supported_yet` (422), `queue_limit_reached` (409), `internal_error` (500); enum mới `DisplayMode` (`normal`, `hidden_unanonymized`, `dev_unblurred`).
- `ErrorBody.fields` (`FieldError {path, message}`, path dạng `attacks.0.grid.levels`); bỏ khỏi body khi không có, nên lỗi cũ vẫn chỉ có `{code, message}`.
- 15 schema mới: `ExperimentCreate` (`ExperimentConfig` + `name`, `cloned_from`), `ExperimentClone {config, warnings}`, `EstimateResponse` (run có `skip_reason = incompatible` thì `est_seconds = 0`; `total_seconds` null khi và chỉ khi có run thiếu profile; `missing_profiles` đúng bằng các attack đó), `ExperimentSummary` (`finished_at` null khi và chỉ khi `draft`/`queued`/`running`), `ExperimentDetail` (`queue_position` chỉ khi `queued`, `limit` bằng `config.limit`), `ExperimentPage`, `RunView` (`RunResult` + tên, version, tham số chính của spec), `FailureCaseView` (`hidden_unanonymized` thì không URL nào; URL dạng `/artifacts/<token>` tương đối với gốc API), `ComputeTargetPublic`, `ModelSummary`, `DatasetSummary`, `DatasetVersionSummary`, `SliceSummary`, `ClassMappingSummary`, `ProtocolSummary`. 54 JSON Schema.
- Mock sinh bằng script, ID tham chiếu chéo khớp nhau: experiment đủ 10 trạng thái; experiment `completed` có 8 run (hoàn thành, `cached`, lỗi, `stopped_limit` có `metrics.partial`, chưa chạy do chạm trần); run đủ 7 trạng thái; `EstimateResponse` đủ, thiếu profile, vượt giới hạn, `incompatible`; `FailureCaseView` đủ 3 `display_mode`; lỗi có `fields`, `queue_limit_reached`, `not_supported_yet`. Test độ phủ mock trong `contracts/python/tests/test_experiment_models.py`.
- OpenAPI: khung `501` qua `**guard(p)` cho `GET /models`, `/models/{id}`, `/datasets`, `/dataset-versions/{id}`, `/slices`, `/class-mappings`, `/attack-specs`, `/protocols`, `/compute-targets`, `GET|POST /experiments` (`POST` trả `201`), `POST /experiments/estimate`, `GET /experiments/{id}`, `/runs`, `POST /cancel` (`experiment.cancel_own`), `GET /clone`, `GET /runs/{id}` (nay trả `RunView`), `/runs/{id}/manifest`, `/runs/{id}/failure-cases`, `/failure-cases/{id}`, `/artifacts/{token}` (`experiment.read`, trả `image/png`/`image/webp`). Route người dùng khai `422` là `ErrorResponse`. Permission có route: 12 → 14.
#### Thay đổi
- `backend/app/api/errors.py`: `VALIDATION_ERROR_RESPONSE`; `ApiError` và `error_response` nhận `fields`; handler lỗi không lường trước trả `500 internal_error`, không lộ chi tiết (ghi log).
- Test Phase 0 (`test_contracts.py`, `contracts/python/tests/test_enums.py`): bảng enum thêm mã Phase 5 và `DisplayMode`.
- Ngoài thư mục người duyệt (người dùng cho phép): `backend/app/api/public.py`, `errors.py`, `backend/app/tests/api/test_skeleton.py` (route mới, kiểm tra `422` khai `ErrorResponse`, `500`, `fields`), `backend/app/tests/db/test_route_protection_db.py` (14 permission), `frontend/src/api/messages.ts` (thông điệp 3 mã mới).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 5)
- Kickoff: ảnh qua API proxy bằng token 10 phút; `skip_reason` và `ExperimentClone` trong contract; E2E bật `DEV_ALLOW_UNBLURRED`; seed cố định 0; code backend mở rộng `backend/app/services/`; `max_time_limit_s` mặc định 28800; tên experiment do server đặt khi bỏ trống; làm mờ giữ ở Phase 10; giữ giới hạn 3 experiment đang chờ.
- Group 0: `GET /artifacts/{token}` cần cả phiên (`experiment.read`) lẫn token, không công khai (không phải sửa test Phase 4, thêm một lớp bảo vệ); thêm cột `experiments.created_at` (Group 1, điền `submitted_at`).
- Người duyệt (agent) tự chọn: `ModelSummary` dùng `framework` thay kiến trúc (DB không có cột); `GET /experiments` mặc định `owner=all`; danh sách tài nguyên của wizard trả mảng (không phân trang).
#### Chuyển cho group sau (`plan.md` task 5a, 5b)
- Router API nội bộ của worker vẫn khai `422` là `HTTPValidationError` (chỉ OpenAPI; runtime đã trả `ErrorResponse`).
- Khi route khung được cài đặt thật: cập nhật `IMPLEMENTED_GROUPS` (Phase 0), `test_multiple_roles_get_the_union` (Phase 4) và `test_union_of_roles` (backend), vốn đòi `POST /experiments` trả `501`.
#### Số liệu
- `make check`: 808 test Python, 218 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 264 test.
#### Review (phase-review, 2026-09-29)
- Không có phát hiện chặn. Phát hiện #1 (người dùng yêu cầu sửa trước merge): contract cấm `exceeds_limit = true` khi thiếu profile, nên phần ước lượng được đã vượt giới hạn cũng không cảnh báo → bỏ ràng buộc, `exceeds_limit` tính trên cận dưới; ghi vào `requirements.md` mục Ước lượng và `validation.md`. Phát hiện #6: `cloned_from` phải tồn tại (ghi vào `plan.md` task 9).
- Ghi nhận: khóa MinIO trong `FailureCaseView.artifacts` vẫn trả khi ảnh bị ẩn (không cho quyền đọc; xem lại ở Phase 11).
#### Lưu ý
- Group 0, review và phần sửa sau review do cùng một agent làm thay người duyệt theo ủy quyền của người dùng; không độc lập.

### Kickoff Phase 5 — 2026-09-29
- Chốt 8 câu hỏi (xem Quyết định ở Group 0), bổ sung độ phủ vào `validation.md` (đọc tài nguyên, `online`/`queue_length`, lọc và phân trang, `finished_at` khi hủy, xin lại URL, `queue_limit_reached` trên giao diện, `/home`, tab Chi phí) và task 3a (worker và `DEV_ALLOW_UNBLURRED` trong `scripts/e2e.sh`).

---

## Phase 4 — Xác thực và phân quyền

**Trạng thái:** ✅ hoàn thành 2026-09-29. Group 0–7 đã merge.

### Replan sau Phase 4 — 2026-09-29
- Phase 5 `requirements.md`: bảng endpoint dùng action `experiment.submit` (trước ghi `experiment.created`, mâu thuẫn với chính spec); mục Context ghi các quy ước của Phase 4 (`**guard(p)`, thứ tự 401/403/422, phân trang keyset và `Page[T]`, `validation_error`/`invalid_request`, `ERROR_MESSAGES`, action `entity.verb`). `validation.md`: `experiment.submit`.
- Phase 5 `plan.md`: task 1a (OpenAPI khai `422` là `ErrorResponse`, cân nhắc `ErrorCode` cho `500`), 2a (endpoint khung qua `**guard(p)`, cập nhật số permission có route trong test backend), 37 (cập nhật test điều hướng của Phase 4 khi bật `/experiments`).
- Phase 6 `plan.md` task 35: mục `/admin/attacks` trong `NAV_ITEMS` (admin 5 mục → điện thoại 3 mục + "Thêm"), dùng lại mẫu bảng/thẻ của Phase 4.
- `roadmap.md` Phase 11: "(Từ Phase 4)" `/docs` công khai, `TRUSTED_PROXIES` của compose chỉ hợp cho dev, ô chọn actor tối đa 100.
- Rủi ro: thời gian job CI `e2e` tăng theo số kịch bản (chạy tuần tự); kịch bản E2E đăng nhập sai nhiều lần sẽ khóa đăng nhập của cả bộ (cùng IP).

### Phase 4 — Tổng kết (phase-close) — 2026-09-29
- **Giao được:** yêu cầu truy cập → admin duyệt/từ chối → đăng nhập bằng phiên phía server (cookie httpOnly 12 giờ, sha256 token, CSRF double-submit, giới hạn 5 lần sai/15 phút theo email và IP qua `TRUSTED_PROXIES`); đổi và đặt lại mật khẩu (link một lần do admin tạo); ma trận quyền trong contract (21 permission, sinh sang TypeScript), `require_permission` cho mọi route cần phiên và kiểm tra lúc khởi động; quản trị người dùng (luật admin cuối cùng, tự vô hiệu hóa, chuyển trạng thái), audit log đủ thao tác tài khoản và trang xem cho admin; frontend mobile-first (sidebar / cột icon / thanh tab), trang giới thiệu, đăng nhập, yêu cầu truy cập, chờ duyệt, đặt lại mật khẩu, tài khoản, `/home` theo role, quản lý người dùng, audit log.
- **Contract:** `Permission`, `ROLE_PERMISSIONS`, 7 `ErrorCode` mới, 13 schema (`AccessRequest`, `Me`, `UserAdminView`, `AuditLogEntry`, `Page`...), OpenAPI `/auth/*`, `/admin/users/*`, `/audit-log` với `x-permission`; `AuditLogEntry.action` chỉ đòi chuỗi không rỗng (review Group 3). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` (709 test Python, 217 test nghiệm thu không cần DB, 103 Vitest), `make test-db` (251 test, gồm 70 test nghiệm thu Phase 4 cần DB), `make test-e2e` (39 test = 13 kịch bản × 3 viewport, khoảng 38 giây).
- **`validation.md`:** Automated Tests đủ; Manual Checks 6/6 (điện thoại Android và iPhone thật, đọc lại nội dung: người dùng xác nhận); Definition of Done 5/5.
- **CI:** xanh trên GitHub, gồm job `e2e` (người dùng xác nhận, 2026-09-29).
- **Chuyển tiếp (không chặn):** `/docs`, `/openapi.json` công khai; compose tin cả mạng Docker trong `TRUSTED_PROXIES` (chỉ hợp cho dev); lỗi `500` chưa có `ErrorCode`, OpenAPI khai `422` là `HTTPValidationError`; ô chọn actor trên trang audit tối đa 100 người dùng; 9 permission chưa có route chỉ được kiểm tra ở mức ma trận.
- **Lưu ý:** Group 0, 7, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 4 — Group 7 (người duyệt, người dùng giao) — 2026-09-29
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_04/` (134 test: 64 ô ma trận quyền không cần DB, 70 test `db`): người dùng tạo qua API thật (yêu cầu truy cập, admin duyệt), mỗi client một IP gốc qua proxy tin cậy, đồng hồ giả. Đủ mọi mục Automated Tests backend của `validation.md` (bảo vệ route, xác thực, CSRF, hiệu lực tức thời, quản trị, audit). Luật "admin active cuối cùng" kiểm tra qua HTTP bằng cách tạm vô hiệu các admin khác rồi khôi phục (người dùng chốt).
- E2E `frontend/e2e/phase_04/` (13 kịch bản × 3 viewport = 39): yêu cầu truy cập → chờ duyệt; admin duyệt qua giao diện → điều hướng chỉ mục được phép; từ chối có lý do; engineer → `/forbidden`; hết phiên → `/login?next=` rồi quay lại; bàn phím cho form đăng nhập và yêu cầu truy cập; bố cục theo viewport (tab/cột icon/sidebar, bảng/thẻ, bottom sheet, không cuộn ngang); số chờ duyệt trên `/home`; hai trình duyệt; cờ cookie và localStorage. Hai lần chạy liên tiếp đều 39/39.
- Playwright `workers: 1` (người dùng chốt: các kịch bản dùng chung DB).
#### Thay đổi
- Test nghiệm thu Phase 0 (`test_api.py`, task 34): bỏ nhánh chuyển tiếp; không phiên → đúng `401 unauthenticated`; phiên thật đủ 3 role → đúng `501` cho nhóm còn là khung.
#### Manual check (máy phát triển, không có điện thoại thật)
- `make up` (project `advertest-p4check`, cổng riêng, env tạm, đã dọn): 4 service healthy; uvicorn chạy `--no-proxy-headers`; seed admin trong container; đăng nhập bằng email chữ hoa → `200`, cookie `advertest_session` (`HttpOnly; Max-Age=43200; Path=/; SameSite=lax`) và `csrf_token` (không `HttpOnly`); `/auth/me` đúng; đăng nhập qua proxy `/api` của frontend `200`; đăng xuất thiếu CSRF → `403`.
- **Phát hiện:** trong compose, với `TRUSTED_PROXIES=127.0.0.1` mặc định, đăng nhập qua proxy của frontend ghi IP của container frontend (`172.19.0.5`): mọi người dùng chung một IP, giới hạn đăng nhập sai theo IP khóa chung. Đã sửa (người dùng chốt): compose mặc định `TRUSTED_PROXIES=127.0.0.1,172.16.0.0/12`, ghi chú trong `.env.example` rằng bản triển khai chỉ đặt IP reverse proxy thật. Chạy lại `make up`: không header → ghi `172.19.0.1` (gateway, mọi người dùng trên máy này vốn chung IP vì cổng chỉ gắn 127.0.0.1); có reverse proxy gửi `X-Forwarded-For: 198.51.100.23` → ghi đúng `198.51.100.23`.
- Chưa làm (cần người dùng): điện thoại Android và iPhone thật (luồng đầy đủ, không tự zoom, thanh tab không bị thanh home che, copy link đặt lại); đọc lại toàn bộ nội dung tiếng Việt.
#### Số liệu
- `make check`: 709 test Python, 217 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 251 test. `make test-e2e`: 39 test trong khoảng 38 giây.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi vào spec: E2E tuần tự (`tech-stack.md` mục 7), `TRUSTED_PROXIES` của compose (`requirements.md`), cách kiểm tra luật admin cuối cùng (`validation.md`). Ghi nhận: tin cả mạng Docker chỉ hợp cho dev (xem lại ở Phase 11).

### Phase 4 — Group 6 (frontend) — 2026-09-29
#### Thêm
- `/admin/users`: tab Chờ duyệt / Tất cả, "Tải thêm"; bảng TanStack Table v9 (≥ 1280px), thẻ (< 1280px); duyệt (role được yêu cầu chọn sẵn), từ chối (bắt buộc lý do), đổi role (bỏ admin có cảnh báo), vô hiệu hóa (xác nhận), kích hoạt, link đặt lại (ô chỉ đọc + copy, dự phòng chọn sẵn khi không có clipboard); lỗi 409/422 trong dialog; làm mới danh sách, số chờ duyệt, audit, `me`.
- `/admin/audit`: lọc người thực hiện (ô chọn hoặc nhấn tên), hành động, loại đối tượng, khoảng ngày; thay đổi dạng `status: a → b`; ID rút gọn ở giữa kèm copy; bảng/thẻ; "Tải thêm".
- Điều hướng bật 2 trang admin; dependency `@tanstack/react-table` 9.2.4. Vitest 91 → 103.
#### Kiểm tra
- Luồng admin thật (spec tạm, không commit) trên 3 viewport: duyệt, từ chối, đổi role, tạo và copy link, vô hiệu hóa, lọc audit, người bị từ chối thấy `/pending?code=account_rejected`; dialog là bottom sheet ở 390px; không cuộn ngang.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`)
- Lọc actor bằng ô chọn (tối đa 100) và nhấn tên; "Tải thêm"; ngày theo giờ máy, trọn ngày kết thúc; ẩn nút tự vô hiệu hóa; bảng từ 1280px.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi nhận: ô chọn actor thiếu người khi hơn 100 người dùng.

### Phase 4 — Group 5 (frontend) — 2026-09-29
#### Thêm
- Trang `/` (giới thiệu, ba role), `/login` (quay lại `next`; `account_*` → `/pending?code=`), `/request-access` và `/request-access/sent`, `/pending`, `/reset-password/:token`, `/account` (thông tin, đổi mật khẩu với lỗi `422` dưới ô mật khẩu hiện tại, đăng xuất), `/home` (khối theo role, số chờ duyệt cho admin).
- `RequirePermission` hiện lỗi và nút "Thử lại" khi `/auth/me` lỗi khác `401` (task 30a); điều hướng bật "Trang chủ", "Tài khoản".
- Schema zod (`src/auth/schemas.ts`) cùng luật với contract; `SelectField`, `TextareaField`, `FormAlert`, `LoadError`; `src/test-utils.tsx`. Vitest 70 → 91.
#### Sửa trong lúc làm
- Bản build của E2E không đặt `VITE_API_BASE_URL=/api` nên gọi API không qua proxy (kịch bản khói chỉ gọi `/api/health` nên không lộ): đặt trong `playwright.config.ts`.
#### Kiểm tra
- Chạy thử luồng thật (spec tạm, không commit) trên 3 viewport với backend thật: yêu cầu truy cập → chờ duyệt → admin duyệt (qua API) → `/account` chuyển về `/login?next=` rồi quay lại → đổi mật khẩu (sai rồi đúng) → đăng xuất; không cuộn ngang.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`, `plan.md`)
- `/pending?code=`; `/request-access/sent`; khối admin đếm tối đa 100 ("100+"); bản build E2E dùng `/api`; Group 6 làm mới số chờ duyệt sau khi duyệt/từ chối.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn.

### Phase 4 — Group 4 (frontend) — 2026-09-29
#### Thêm
- API client: `apiSend` gửi cookie và `X-CSRF-Token` (từ cookie `csrf_token`); `401 unauthenticated` → `/login?next=...`, `403 forbidden` → `/forbidden` qua `QueryCache`/`MutationCache`; `ERROR_MESSAGES` tiếng Việt cho mọi `ErrorCode`; proxy Vite `xfwd: true`.
- `useMe()`, `can()`, `<RequirePermission>`, trang `/forbidden`; cấu hình điều hướng `src/nav/config.ts` (quyền, cờ `implemented`; mọi mục còn `false`).
- `AppShell`: sidebar ≥ 1280px, cột icon 768–1279px, thanh tab < 768px (3 mục + "Thêm"), `safe-area-inset`, `viewport-fit=cover`; `Dialog` đáp ứng (bottom sheet trên điện thoại), `ConfirmDialog`, `Button` (≥ 44px), `TextField`, `useZodForm` (resolver tự viết).
- Dependency: `react-hook-form` 7.89.0, `zod` 4.6.5. Vitest 36 → 70.
#### Sửa trong lúc làm
- Bản build production chứa chunk mock khi kiểm tra chế độ mock qua hàm gọi từ hai chỗ: viết thẳng biểu thức `import.meta.env` tại chỗ gọi.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `tech-stack.md`)
- Thanh tab 3 mục + "Thêm"; chỉ `401 unauthenticated`/`403 forbidden` chuyển trang toàn cục; `next` chỉ đường dẫn nội bộ; `VITE_MOCK_ME`; resolver zod tự viết.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Chuyển cho Group 5 (`plan.md` task 30a): trạng thái lỗi khi `/auth/me` lỗi khác `401`.

### Phase 4 — Group 3 (backend) — 2026-09-29
#### Thêm
- `backend/app/admin/users.py`: duyệt, từ chối, đổi role, vô hiệu hóa (thu hồi mọi phiên), kích hoạt, tạo link đặt lại (24 giờ, sha256, vô hiệu link cũ); khóa dòng và advisory lock cho luật admin active cuối cùng; audit `before`/`after` = `{status, roles}` trong cùng transaction.
- `backend/app/audit/query.py`, `backend/app/api/pagination.py`: `/audit-log` lọc, `actor` dạng object; phân trang keyset theo `(created_at, id)`.
- Endpoint `/admin/users/*`, `/audit-log` (OpenAPI không đổi); `APP_BASE_URL` trong compose và `.env.example`.
- Test: `tests/db/test_admin_api.py` (19): duyệt/từ chối, `409` các loại, admin cuối cùng (service, trong transaction rollback), link đặt lại, hiệu lực tức thời, `403`, phân trang, audit không chứa bí mật, `/audit-log` không lọc đọc được dòng lệch quy ước.
#### Contract (người duyệt, người dùng chốt ở review)
- `AuditLogEntry.action`: bỏ mẫu `entity.verb`, chỉ đòi chuỗi không rỗng. Lý do: audit log chỉ thêm, dòng lệch quy ước (test Phase 0 chèn `'x'`) làm cả trang `/audit-log` trả `500`. Quy ước `entity.verb` giữ cho code ghi, có test.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md`, `validation.md` Phase 4)
- Đổi role và tạo link chỉ cho user `active`/`disabled`; link mới vô hiệu link cũ; `reset_link_created` có `before` = `after`; thứ tự `(created_at, id)` giảm dần, cursor mờ, cursor sai hoặc thời gian thiếu múi giờ → `422`; `APP_BASE_URL` mặc định.
#### Review
- Review do chính agent viết nhánh (không độc lập). Phát hiện nên sửa (#3, `/audit-log` trả `500` với dòng lệch mẫu) đã xử lý trước khi merge bằng thay đổi contract ở trên và test backend.

### Phase 4 — Group 2 (backend) — 2026-09-29
#### Thêm
- `backend/app/auth/permissions.py`: `require_permission(p)` theo `ROLE_PERMISSIONS` (`403 forbidden`), `guard(p)` (dependency và `x-permission` từ một nguồn), `check_route_permissions` chạy trong `create_app()` và `lifespan`.
- Mọi route cần phiên trong `public.py` dùng `**guard(...)`: `401`/`403` trước `501`. OpenAPI không đổi.
- `current_user` đọc cookie bằng dependency riêng `session_token`: thiếu cookie → `401` không mở DB.
- Test: ma trận quyền (63 trường hợp), route giả thiếu hoặc lệch khai báo, `401` cho mọi route cần phiên, phiên thật theo từng role (12 permission có route), hợp role, bỏ role có hiệu lực ngay.
#### Phát hiện khi làm
- FastAPI 0.141 giữ router con dưới dạng `_IncludedRouter` (không chép route vào `app.routes`): kiểm tra phải duyệt bằng `fastapi.routing.iter_route_contexts` như khi sinh OpenAPI; có test bảo đảm route qua router con bị phát hiện.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md` Phase 4)
- `**guard(p)`; kiểm tra khởi động đòi đúng một `require_permission` khớp `x-permission`; thứ tự `401` → `403` → `422` → route; thiếu cookie không mở DB.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Ghi nhận: 9 permission chưa có route chỉ được kiểm tra ở mức ma trận; `/docs`, `/openapi.json` vẫn công khai (xét ở Phase 11).
- `make check` (717 test Python, 153 nghiệm thu, 36 Vitest) và `make test-db` (161) pass.

### Phase 4 — Group 1 (backend) — 2026-09-29
#### Thêm
- Migration `0003`: `sessions` (sha256 token, `UPDATE` không `DELETE`), `password_reset_tokens` (`UPDATE` không `DELETE`), `auth_events` (chỉ thêm), `users.reject_reason`, `users.disabled_at`.
- `backend/app/auth/`: argon2id và chính sách mật khẩu (`passwords.py`); phiên phía server 12 giờ, cookie `advertest_session` (HttpOnly, SameSite=Lax, Secure theo `COOKIE_SECURE`) và `csrf_token` (`sessions.py`); `current_user` đọc phiên, user, trạng thái, role từ DB (`deps.py`); middleware CSRF double-submit (`csrf.py`); giới hạn 5 lần sai trong 15 phút theo email và IP (`rate_limit.py`); nghiệp vụ (`service.py`).
- Endpoint `/auth/request-access`, `login`, `logout`, `me`, `password`, `password-reset` (OpenAPI không đổi).
- Lỗi thống nhất: body sai schema → `422 validation_error` (không lặp lại giá trị gửi lên); lỗi HTTP của framework → `ErrorResponse`.
- `TRUSTED_PROXIES`, `COOKIE_SECURE` trong compose và `.env.example`; entrypoint `--no-proxy-headers`.
- Test: `tests/db/test_auth_api.py` (24), `test_auth_sessions.py`, `tests/auth/test_csrf.py`, `test_passwords.py`, `tests/api/test_errors.py`.
#### Quyết định (người dùng chốt, đã ghi vào `requirements.md` Phase 4)
- Đúng mật khẩu nhưng tài khoản chưa `active`, và lần bị chặn `429`: không ghi `auth_events`, không tính vào giới hạn.
- `ProxyHeadersMiddleware` trong app thay cờ uvicorn (test được); audit đổi/đặt lại mật khẩu có `before`/`after` null; `405` → `invalid_request`; link đặt lại sai/đã dùng/hết hạn → `422 invalid_request`.
- `current_user` làm ở Group 1; Group 2 còn `require_permission`, gắn cho mọi route và kiểm tra lúc khởi động.
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn. Chuyển cho Group 4: `xfwd: true` cho proxy Vite (`plan.md` task 19). Còn mở (contract): lỗi `500` chưa có `ErrorCode`; OpenAPI khai `422` là `HTTPValidationError`.
- `make check` (645 test Python, 153 nghiệm thu, 36 Vitest) và `make test-db` (155) pass.
#### Manual check còn lại
- `make up`: đăng nhập admin seed, xem cờ cookie trong DevTools (entrypoint mới chưa chạy trong Docker).

### Phase 4 — Group 0 (người duyệt, người dùng giao) — 2026-09-29
#### Contract
- `advertest_contracts.permissions`: enum `Permission` (21 giá trị), `ROLE_PERMISSIONS` (đúng từng ô bảng trong `requirements.md`), `permissions_for(roles)` (hợp), `AUTHENTICATED`; sinh `frontend/src/contracts/permissions.ts`.
- `ErrorCode` thêm `invalid_credentials`, `account_pending`, `account_rejected`, `account_disabled`, `rate_limited`, `csrf_failed`, `validation_error`.
- Schema mới: `AccessRequest`, `LoginRequest`, `Me` (`permissions` phải bằng hợp của `roles`), `UserAdminView`, `ApproveRequest`, `RejectRequest`, `RolesUpdate` (cả hai: ít nhất 1 role, không trùng), `PasswordChange`, `PasswordResetLink`, `PasswordResetConsume`, `AuditActor`, `AuditLogEntry`, `Page[T]` (`UserAdminPage`, `AuditLogPage`); kiểu `Email` (tự chuyển chữ thường), `NewPassword` (10–256 ký tự). Mock: `Me` cho từng role và engineer+reviewer, `UserAdminView` đủ 4 trạng thái, `AuditLogEntry` có actor `null`. 39 JSON Schema.
- OpenAPI: `/auth/request-access|login|password-reset` công khai (không cookie); `/auth/logout|me|password`, `/admin/users/*` (7 endpoint), `/audit-log` (lọc, cursor) là khung `501`. Mọi route cần phiên khai `x-permission` và `401`/`403` `ErrorResponse`. Bỏ `GET /users` (Phase 0).
#### Thêm
- `@playwright/test` 1.63.0, `frontend/playwright.config.ts` (3 viewport, `vite preview` có proxy `/api`), `frontend/e2e/smoke.spec.ts`; `scripts/e2e.sh` (migration, seed admin, uvicorn, Playwright); `make test-e2e`; job CI `e2e`.
#### Thay đổi
- `tech-stack.md` mục 4, 4.1, 5, 11 (phiên phía server, `require_permission`/`x-permission`, `react-hook-form`/`zod`, Playwright); `roadmap.md` Phase 4.
- Test nghiệm thu Phase 0 (`test_api.py`, `test_contracts.py`): nhóm `/admin` thay `/users`; endpoint công khai của `/auth`; kiểm tra `501` chỉ cho nhóm còn là khung và tạm chấp nhận `401 unauthenticated` khi không có phiên (Group 7 siết lại, `plan.md` task 34).
- Ngoài thư mục người duyệt (người dùng cho phép): `backend/app/api/public.py`, `errors.py`, `security.py` (mô tả cookie), `main.py`; `backend/app/tests/api/test_skeleton.py` (danh sách route, thêm kiểm tra `x-permission`); `scripts/gen_contracts.py`; `Makefile`; `.github/workflows/ci.yml`; `frontend/` (Playwright, tsconfig, ignore).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 4)
- Kickoff: sửa test Phase 0; IP qua `TRUSTED_PROXIES`; sai mật khẩu hiện tại → `422 invalid_request`; action `user.password_reset`, actor là chính người dùng, `AuditLogEntry.actor` dạng object; phiên 12 giờ không ghi nhớ; bổ sung độ phủ (email chữ thường, `409` cho chuyển trạng thái sai, `APP_BASE_URL`, test hợp quyền...).
- Group 0: `x-permission: authenticated` cho route chỉ cần đăng nhập; `RolesUpdate` ít nhất 1 role; test Phase 0 chuyển tiếp `401|501`.
- Người duyệt (agent) tự chọn: ánh xạ `x-permission` của endpoint khung (`/reviews` → `review.decide`, `/budget` → `budget.manage`, `/slices` → `dataset.read`, `/failure-cases` → `experiment.read`); `Email` tự kiểm tra hình dạng thay vì `EmailStr` (tránh dependency `email-validator`).
#### Review
- Review do chính agent viết nhánh (không độc lập): không có phát hiện chặn; ghi vào `requirements.md` chi tiết phản hồi của endpoint (login trả `Me`, `202`/`204`, `limit` 50/100, `since`/`until`), sửa câu task 1a trong `plan.md`. Còn theo dõi: job CI `e2e` chưa chạy trên GitHub; Group 7 siết lại test Phase 0.
#### Số liệu
- `make test-e2e`: 6 test (2 kịch bản × 3 viewport) pass trong 3.7 giây.

---

## Phase 3 — Worker và máy local

**Trạng thái:** ✅ hoàn thành 2026-09-29, **còn tồn đọng** (người dùng cho phép đóng phase). Group 0–6 đã merge.

### Replan sau Phase 3 — 2026-09-29
- Phase 4 `requirements.md`: danh sách `ErrorCode` gộp các mã đã có từ Phase 3 (`invalid_request` cho 422 nghiệp vụ; `validation_error` cho 422 do sai schema).
- Phase 5 `requirements.md`: `POST /experiments` dùng lại `experiments.submit` (inference params, `failure_cases_per_run`, action audit `experiment.submit`/`experiment.cancel`); `ErrorResponse` cần đường dẫn trường; câu hỏi mở mới về cách phục vụ ảnh cho điện thoại (presigned URL hiện ký cho `127.0.0.1:9000`).
- Phase 6 `requirements.md`: làm mờ ở `StoreCandidates` của worker; `targets` chưa có `image_id` trong `RunExecutor`; thời gian train patch báo qua `progress`; PGD phụ thuộc nhẹ batch size.
- `tech-stack.md` mục 4.4: tái lập với batch size khác nhau (±0.01).
- `roadmap.md`: "Từ Phase 3" cho Phase 9 (user MinIO riêng, GPU) và Phase 10 (`DEFAULT_STORE_DIR`, quyền 0600 của `LocalStore`).
- Rủi ro: ảnh trên điện thoại ở Phase 5; thời gian job acceptance của CI tăng; tái lập và calibration trên GPU chưa đo.

### Phase 3 — Tổng kết (phase-close) — 2026-09-29
- **Giao được:** experiment gửi qua `advertest-admin` (compute target, token, `import-local`, `submit`, `experiment list|show|cancel`); API nội bộ `/internal/worker` (lease có `lease_id`, bundle, heartbeat, start có cache toàn hệ thống, progress, artifact-url, complete, cost profile); worker `advertest-worker` (chạy trực tiếp hoặc Docker `cpu`/`gpu`) chạy `RunExecutor` theo batch, checkpoint lên MinIO qua presigned URL, chạy tiếp sau gián đoạn, calibration, giới hạn thời gian, hủy; artifact và thumbnail trong MinIO; đủ trạng thái run có lý do.
- **Contract:** schema API worker (`WorkerLease`, `WorkerJobBundle`, `RunStartRequest/Response`, `ProgressReport`, `WorkerDirective`, `ArtifactUrlRequest/Response`, `CostProfile`, `RunCompletion`), `RunResult.cached_from_run_id`, `RunMetrics.partial`, `FailureCaseRecord.id` gồm `run_id`, thumbnail, `ProtocolStatus`, `ErrorCode` (401/403/404/409/422). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` pass trên `main` (562 test Python, 156 test nghiệm thu không cần DB, 36 Vitest); `make test-db` 124 test (41 test nghiệm thu Phase 3). KITTI 300 ảnh, CPU, worker trong Docker: `pgd_sweep` 28 phút xử lý, metric trong ±0.01 so với Phase 2 (FGSM trùng tuyệt đối); `kill -9` chạy tiếp sau 59 giây; checkpoint 27 MB cho 6 run; calibration PGD batch 2 1.229 s/ảnh, FGSM batch 2 0.158 s/ảnh.
- **`validation.md`:** Automated Tests đủ; Manual Checks 9/10; Definition of Done 5/6.
- **CI:** xanh sau khi push `main` gồm Group 6 (người dùng xác nhận, 2026-09-29).
- **Tồn đọng (cập nhật khi có kết quả):**
  - Manual check profile `gpu` và số calibration trên GPU.
  - User MinIO riêng cho API (từ Phase 0), `DEFAULT_STORE_DIR` chỉ đúng khi cài editable (từ Phase 1): chưa có task, đề xuất chuyển sang phase sau (replan).
  - Kết quả PGD phụ thuộc nhẹ vào batch size trên KITTI thật (trong sai số).
- **Lưu ý:** Group 0, 6, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 3 — Group 6 (người duyệt, người dùng cho phép) — 2026-09-29
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_03/` (41 test, mọi mục Automated Tests của `validation.md`): `test_architecture.py` (AST import, env compose, OpenAPI và router), `test_worker_auth.py`, `test_leasing.py`, `test_artifacts.py`, `test_execution.py` (golden Phase 2 ±0.01), `test_resume.py` (so lần chạy liền mạch ±0.005/±0.01, gián đoạn một và hai lần), `test_limits.py`, `test_calibration.py` (CLI `advertest-worker calibrate` qua uvicorn thật), `test_audit.py`. Chạy với worker thật, YOLOv8n và 5 ảnh fixture thật, Postgres và MinIO thật; cả bộ khoảng 1.5 phút trên CPU.
- Lần chạy liền mạch và lần bị gián đoạn dùng GIT_COMMIT khác nhau (fingerprint khác, không trúng cache); yêu cầu `start` trong test có fingerprint riêng mỗi lần.
- Manifest trong Docker kiểm bằng test mô phỏng env (`GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`) cộng manual check trong container (người dùng chốt).
#### Manual check (máy phát triển, CPU 16 luồng, không GPU; `make up` với project và cổng riêng, đã dọn)
- `import-local`: 300/7481 ảnh KITTI lên MinIO (đếm object; chỉ ảnh thuộc slice).
- `pgd_sweep.yaml` trên slice KITTI 300 ảnh, worker trong Docker (`docker/worker/up.sh cpu`), 28 phút xử lý: 6 run `completed`, mỗi run 20 failure case đủ file (PNG 640x640, thumbnail WebP 320x320), `candidates/` rỗng, manifest có `docker_image_digest` thật và `git_dirty = false`.
- `kill -9` worker khi run PGD L∞ eps 2 ở 132/300 ảnh; khởi động lại; worker nhận lại experiment sau 59 giây (lease hết hạn) và chạy tiếp từ checkpoint batch 65.
- Metric so với Phase 2 (CLI, batch 8): FGSM eps 4/8 trùng tuyệt đối (0.1765, 0.1631); PGD L∞ eps 2 (run bị gián đoạn) mAP@0.5 0.0129 vs 0.0123, ASR 0.761 vs 0.767; eps 4 0.0018 vs 0.0017, ASR 0.897 vs 0.903; eps 8, 16 trùng mAP, ASR lệch ≤ 0.006: trong sai số ±0.01. Lệch có cả ở run PGD không bị gián đoạn, nhiều khả năng do batch size (2 vs 8) chứ không do chạy tiếp.
- Gửi lại cùng cấu hình: 6 run `skipped` (`cached`), xong trong khoảng 20 giây.
- Giới hạn 60 giây: dừng ở 59.9 giây xử lý; run hiện tại `stopped_limit` (42/300 ảnh, `partial = true`), 5 run chưa chạy `stopped_limit` với 0 ảnh.
- Worker chạy trực tiếp (`uv run --extra cpu advertest-worker run --once`): FGSM eps 4 trên 300 ảnh, 48.5 giây, `completed`.
- Calibration trên CPU: PGD L∞ batch 2, 1.229 s/ảnh (batch 1: 1.319, batch 4: 1.321); FGSM batch 2, 0.158 s/ảnh.
- Checkpoint sau `pgd_sweep`: mỗi run 1 file (4.1–5.0 MB), tổng 27 MB cho 6 run (trước khi sửa: 691 MB cho một run).
#### Tồn đọng
- Manual check profile `gpu` (không có GPU); số calibration trên GPU.
- PGD phụ thuộc nhẹ vào batch size trên KITTI thật (≤ 0.0006 mAP, ≤ 0.006 ASR): nằm trong sai số, nên ghi vào spec về tái lập.
- Definition of Done: CI xanh sau khi push, đánh dấu `roadmap.md` (skill `phase-close`).

### Phase 3 — sửa checkpoint quá nặng (worker) — 2026-09-29
#### Thay đổi
- `advertest_worker/job.py`: xóa checkpoint k-1 sau khi `progress` của checkpoint k thành công (khi chạy tiếp, xóa checkpoint trong bundle sau batch kế tiếp); giữ checkpoint cuối cùng của run (xóa trước `complete` thì worker chết đúng lúc đó sẽ không chạy tiếp được). Xóa lỗi chỉ ghi cảnh báo; mất lease (`409`) khi xóa thì dừng experiment ngay.
- Test end-to-end: chạy tiếp sau khi worker chết còn đúng checkpoint cuối mỗi run (fail trên code cũ); xóa lỗi không làm run `failed`; mất lease khi xóa thì không xử lý thêm, không gửi `complete` (fail trên code cũ).
#### Quyết định (ghi theo review; đã ghi vào `requirements.md` Phase 3, Checkpoint và chạy tiếp; `validation.md` thêm manual check dung lượng checkpoint)
- Mỗi run chỉ giữ checkpoint mới nhất mà API đang trỏ tới; có thể thừa một file nếu worker chết giữa `progress` và lệnh xóa.
#### Review
- Review (do chính agent viết nhánh, không độc lập): 1 điểm phải sửa (nuốt `LeaseLost` khi xóa checkpoint), đã sửa kèm test.
- `make check` pass (562 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 86 test pass.
#### Tồn đọng
- Chưa đo lại dung lượng trên KITTI (ước tính còn khoảng 4.7 MB mỗi run thay vì 691 MB): manual check Group 6.

### Phase 3 — Group 5 (backend) — 2026-09-29
#### Thêm
- CLI `advertest-admin` (`backend/admin_cli/cli.py`, entry point trong `pyproject.toml`, người dùng cho phép): `compute-target create|rotate-token|list`, `import-local --store --as`, `submit --config --target [--time-limit] --as` (in ước lượng hoặc "chưa có ước lượng"), `experiment list|show [--watch]|cancel --as`. Lệnh ghi dữ liệu kiểm `--as` là admin `active`.
- `docker/compose.yaml`: service `worker-cpu` (profile `cpu`) và `worker` (profile `gpu`, nvidia), host network, env chỉ gồm `API_URL`, `WORKER_TOKEN`, `CACHE_DIR`, `DEVICE`, `DOCKER_IMAGE_DIGEST`; MinIO mở `127.0.0.1:9000`; `api` có `MINIO_PUBLIC_ENDPOINT` và mount `ADVERTEST_DATA_DIR` chỉ đọc.
- `docker/worker/up.sh cpu|gpu`: build từ working tree sạch, `GIT_COMMIT` là commit hiện tại, `DOCKER_IMAGE_DIGEST` là image ID thật.
- `.env.example` (`MINIO_PORT`, `MINIO_PUBLIC_ENDPOINT`, `ADVERTEST_DATA_DIR`, `API_URL`, `WORKER_TOKEN`, `WORKER_DEVICE`); `docs/van-hanh-worker.md`.
- Test: `test_admin_cli.py` (CliRunner, Postgres và MinIO thật: token chỉ in một lần, `--as` không phải admin bị từ chối, audit, submit/show/list/cancel, `--watch`), `test_compose.py` (env worker không có thông tin đăng nhập, profile, cổng).
#### Sửa (phát hiện khi chạy thật trên Docker)
- Image thiếu thư viện cho opencv: `api` (từ Group 2, qua `ml_core.models.wrapper`) và worker không import được ultralytics, tức `make up` hỏng trên `main` trước nhánh này. Dockerfile cài `libgl1`, `libglib2.0-0`, `libxcb1`; `MPLCONFIGDIR`, `YOLO_CONFIG_DIR` ở `/tmp`.
- Image thiếu `contracts/seeds/`: seed không chạy được trong container. `.dockerignore` thêm thư mục này.
#### Số liệu đo được (chạy thật trên Docker, KITTI slice 300 ảnh seed 42, YOLOv8n, CPU, worker trong container)
- FGSM eps 4/255: mAP@0.5 sạch 0.5332 → 0.1765, ASR 0.438: trùng tuyệt đối số của Phase 2 (CLI). 71.6 giây xử lý; calibration chọn batch 1, 0.244 s/ảnh. 20 failure case kèm thumbnail, `candidates/` rỗng; manifest có `docker_image_digest` thật, `git_dirty = false`.
- Checkpoint: 300 file, checkpoint cuối 4.7 MB, tổng 691 MB cho một run (mỗi batch ghi checkpoint đầy đủ, không xóa checkpoint cũ).
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3, Luồng xử lý của worker, CLI quản trị; `validation.md` Manual Checks)
- `DOCKER_IMAGE_DIGEST` là image ID thật truyền lúc chạy; worker compose dùng host network, MinIO mở `127.0.0.1:9000`; entry point `advertest-admin` (người dùng chốt).
- `import-local` bắt buộc `--as`, chạy bằng uid của máy; `ADVERTEST_DATA_DIR` mount vào `api`; `local-dev` cấp token bằng `rotate-token`; seed truyền biến admin khi chạy.
#### Review
- Review (do chính agent viết nhánh, không độc lập): không có điểm chặn; ghi nhận: checkpoint quá nặng (worker), compose chạy thẳng không qua `up.sh` làm worker lỗi fingerprint, quyền 0600 của `LocalStore`, CLI chỉ bắt `ServiceError`.
- `make check` pass (562 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 84 test pass.
#### Tồn đọng
- **Checkpoint quá nặng** (Group 4, nên làm trước Group 6): worker xóa checkpoint k-1 sau khi `progress` của checkpoint k thành công.
- Worker nên kiểm `GIT_COMMIT` lúc khởi động (image build không qua `up.sh`).
- `LocalStore` ghi file quyền 0600 (ml-core): cân nhắc 0644 để `import-local` không cần `exec -u`.
- Profile `gpu` chưa chạy thử; manual check `pgd_sweep.yaml` và `kill -9` trên `make up`.
- Image thử nghiệm còn trên máy: `advertest-worker:cpu`, `advertest-g5smoke-api` (container và volume đã dọn).

### Phase 3 — Group 4 (worker) — 2026-09-29
#### Thêm
- Package `advertest_worker` (`backend/worker/advertest_worker/`): `config.py` (`API_URL`, `WORKER_TOKEN`, `CACHE_DIR`, `DEVICE`), `client.py` (API nội bộ, retry với backoff, `409` → `LeaseLost`), `cache.py` (tải theo sha256, `LocalStore` trong cache, `ShaCacheLoader`), `calibrate.py` (n = min(20, số ảnh), batch tối đa min(n, 32), dừng khi hết VRAM hoặc hết lợi trên CPU, có lượt khởi động), `job.py` (vòng lặp start → batch → checkpoint → `progress` → chỉ thị → `complete`; chạy tiếp từ checkpoint; tự dừng khi không đủ thời gian; giảm batch khi hết VRAM; heartbeat ở luồng riêng), `cli.py` (`advertest-worker run [--once]`, `calibrate --experiment <id>`).
- Test: client (MockTransport), calibration trên CPU, vòng lặp `serve`; end-to-end với API, Postgres, MinIO thật: chạy xong, trùng cache (attack không được gọi), worker chết rồi chạy tiếp (mỗi ảnh đúng một lần), giới hạn thời gian (kết quả một phần), hủy (dừng sau batch hiện tại), checkpoint hỏng.
#### Thay đổi (sửa theo review)
- Worker: lỗi khi tải hoặc dựng lại checkpoint chỉ làm run `failed`; vòng lặp `run` không thoát khi một job lỗi.
- Backend (`phase03-backend-fp`): chạy tiếp với fingerprint khác → run `failed` (commit trước khi trả `409`) thay vì kẹt ở `running`; test service, HTTP, end-to-end với worker thật.
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3, Luồng xử lý của worker, Calibration)
- `calibrate --experiment <id>`, không lease (người dùng chốt).
- Worker xét chỉ thị ở đầu batch và ngay sau `progress`; run `failed`/`cancelled` xóa ứng viên; batch mặc định 8; cache `~/.cache/advertest-worker`; thời gian calibration không tính vào giới hạn; vòng lặp không thoát khi một job lỗi; fingerprint đổi khi chạy tiếp thì run `failed`.
#### Review
- Review (do chính agent viết nhánh, không độc lập): 3 điểm phải sửa, đã sửa kèm test; các test mới fail trên code cũ. Trong lúc viết test hủy cũng phát hiện và sửa: chỉ thị `cancel` trả về từ `progress` của batch cuối bị bỏ qua.
- `make check` pass (559 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 81 test pass.
#### Tồn đọng
- Nhánh giảm batch khi hết VRAM chưa có test (không có GPU): manual check trên máy GPU.
- Test end-to-end dùng YOLOv8n ngẫu nhiên (không có failure case); fixture thật để cho test nghiệm thu Group 6. Metric sau khi chạy tiếp trùng lần chạy liền mạch đã kiểm ở unit test Group 1, chưa kiểm qua worker.
- Group 5: service `worker` trong compose, `.env.example` (`MINIO_PUBLIC_ENDPOINT`), tài liệu chạy worker.

### Phase 3 — Group 3 (backend) — 2026-09-29
#### Thêm
- `backend/app/api/worker.py`: cài đặt 8 endpoint `/internal/worker` (`lease` 200/204, `bundle`, `heartbeat`, `start`, `progress`, `artifact-url`, `complete` 204, `cost-profiles` 204); `search-result` vẫn là khung (Phase 7). OpenAPI không đổi so với Group 0.
- `backend/app/api/deps.py`: session factory, storage, đồng hồ là dependency (test thay được); mỗi endpoint mở transaction riêng; bearer token → compute target (thiếu token 401 trước khi mở DB).
- `backend/app/api/errors.py`: lỗi service → HTTP (404, 403, 409, 422) với `ErrorResponse`.
- `backend/app/services/bundle.py` (dựng `WorkerJobBundle`: card, slice, manifest từ MinIO; mapping, attack spec, cost profile từ DB; presigned GET cho weights, manifest, ảnh, checkpoint); `runs.artifact_url`.
- `backend/app/presign.py`: presigned PUT/GET/DELETE 15 phút qua `MINIO_PUBLIC_ENDPOINT`.
- Test HTTP với Postgres và MinIO thật (`test_worker_api.py`): token và xoay token, bundle với URL tải thật (kiểm sha256), luồng run, URL ngoài thư mục run (403), run đã kết thúc (409), artifact thiếu (422), lease cũ (409), cost profile, URL hết hạn; `test_skeleton.py`: 8 endpoint trả 401 khi thiếu token.
#### Contract (người duyệt, người dùng cho phép)
- `ErrorCode` thêm `invalid_request` (422); sinh lại JSON Schema, OpenAPI, TypeScript.
#### Thay đổi
- Test nghiệm thu Phase 0 `test_worker_internal_endpoint_returns_501` gọi endpoint khung `search-result` thay cho `lease` (người dùng cho phép). Phase 7 phải đổi lại khi cài đặt `search-result`.
#### Quyết định (đã ghi vào `requirements.md` Phase 3, API nội bộ cho worker)
- Bảng mã lỗi của API worker; `bundle` không đòi `lease_id`; `MINIO_PUBLIC_ENDPOINT` mặc định `MINIO_ENDPOINT`; presigned URL còn hiệu lực tới khi hết hạn kể cả sau khi run kết thúc.
#### Review
- Review (do chính agent viết nhánh, không độc lập): không có điểm chặn; ghi nhận: URL còn hiệu lực sau khi run kết thúc, `KeyNotFoundError` từ MinIO trong bundle thành 500, `assert` trong endpoint `lease`, presigner dùng khóa root MinIO.
- `make check` pass (551 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 73 test pass.
#### Tồn đọng
- `MINIO_PUBLIC_ENDPOINT` trong `.env.example` và compose (Group 5); manual check chữ ký qua host công khai với `make up`.
- OpenAPI chưa khai báo 401/403/409/422 cho endpoint worker (cần thay đổi contract nếu muốn).
- Lỗi validation của FastAPI (422 `{"detail": ...}`) chưa theo `ErrorResponse` (Phase 4).

### Phase 3 — Group 2 (backend) — 2026-09-29
#### Thêm
- Migration `0002`: `protocol_status` thêm `dev`, seed `dev-open` (`created_by` null chỉ với `status = dev`); `experiments.lease_id`, `processing_seconds_used`, `inference_params`, `failure_cases_per_run`; `runs.fingerprint` nullable, `cached_from_run_id`, `checkpoint_key`, `checkpoint_batch_index`, `ordinal`; `failure_cases` theo `FailureCaseRecord` (bỏ `artifact_uri`, `thumbnail_uri`, `details`; thêm `fingerprint`, `rank`, `lost_objects`, `new_false_positives`, `detections`, `artifacts`); `slices.slice_sha256`; `cost_profiles.environment`. Upgrade/downgrade hai chiều.
- `backend/app/services/`: `compute_targets` (token `secrets`, DB lưu sha256, xoay token, xác thực), `audit` (`require_admin`, `record`), `registry` (`import_local` từ `LocalStore` vào DB và MinIO, id là `content_id`, chỉ ảnh thuộc slice, chạy lại an toàn), `experiments` (`submit`, `cancel`, `sweep_cancelled`), `leasing` (`lease` `SKIP LOCKED`, `heartbeat`, `directive`), `runs` (`start` có cache toàn hệ thống, `progress`, `complete` kiểm tra artifact trong MinIO, `record_cost_profile`), `estimate`.
- `backend/app/storage.py`: client S3 (boto3) của backend, `Buckets`, bố cục khóa MinIO.
- Test `db` (Postgres và MinIO thật): model khớp migration (trước đây chưa có test này), `dev-open`, compute target, registry, lease (kể cả hai worker đồng thời), cache, giới hạn thời gian, hủy, ước lượng, audit.
#### Quyết định (người dùng chốt hoặc ghi theo review; đã ghi vào `requirements.md` Phase 3)
- `dev-open` không có người tạo, id cố định (mục Protocol phát triển).
- Cost profile giữ lịch sử, profile mới nhất thắng (Calibration và ước lượng).
- Hủy: chờ worker báo nếu lease còn hạn; lease hết hạn thì dọn ngay hoặc ở lần `lease` kế tiếp (Trạng thái).
- Dạng `manifest_uri` và khóa artifact (Bố cục lưu trữ trong MinIO); `runs.ordinal`, `SKIP LOCKED`, thứ tự khóa (API nội bộ); `gpu_seconds` lấy từ worker, giới hạn tính theo tổng API cộng dồn (Trạng thái); kiểm tra admin ở CLI (CLI quản trị).
#### Review
- Review (do chính agent viết nhánh, không độc lập): 3 điểm phải sửa trước khi merge, đã sửa kèm test: run kẹt ở `running` khi hủy rồi worker chết; thứ tự khóa run/experiment có thể gây deadlock; khóa artifact có `..` gây lỗi 500. Test thứ tự khóa và test khóa `..` đã chạy lại trên code cũ và fail; test dọn run kẹt chưa chạy lại trên code cũ. Trong lúc viết test cũng phát hiện và sửa: `lease` khóa dòng compute target làm worker cùng target chờ nhau.
- `make check` pass (546 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 67 test pass.
#### Tồn đọng
- Group 3: dựng `WorkerJobBundle`, presigned URL, đổi lỗi service sang HTTP (404/403/409/422).
- Target `local-dev` do seed tạo không có token: dùng `rotate-token` thay vì `create` (Group 5, `validation.md` Manual Checks).
- User MinIO riêng cho API (tồn đọng Phase 0) chưa có task.
- Migration 0002 thêm cột NOT NULL vào `failure_cases`: chỉ chạy được khi bảng rỗng (đúng với mọi môi trường trước Phase 3).

### Phase 3 — Group 1 (ml-core) — 2026-09-29
#### Thêm
- `ml_core/runner/executor.py`: `RunExecutor` (`process_batch`, `finalize`, `to_checkpoint`, `from_checkpoint`), `RunContext`, `build_context`, `load_clean_predictions`, `linf_eps`. Checkpoint JSON: ảnh đã xử lý, prediction sau tấn công đã lọc class đích, `ImageAttackStats`, top-K và mọi ứng viên đã upload, thời gian xử lý; không chứa ảnh; từ chối checkpoint khác fingerprint. mAP tính lại ở `finalize` theo thứ tự slice.
- `ml_core/runner/candidates.py`: `MemoryCandidates` (CLI, bố cục Phase 2) và `StoreCandidates` (worker: PNG và thumbnail vào `runs/<run_id>/candidates/<image_id>/`, chép sang `cases/<case_id>/` khi hoàn tất).
- `ml_core/runner/images.py`: `thumbnail_webp` (320 px, WebP), mask letterbox, PNG, ảnh nhiễu khuếch đại (chuyển từ `run.py`).
- `ml_core/runner/cache_loader.py`: `ShaCacheLoader` đọc ảnh `<cache>/<sha256>` có kiểm tra hash.
- `ml_core/store/`: `MinioStore` (client S3 truyền vào, bất biến theo ETag/nội dung), `PresignedStore` (`httpx`), protocol `DeletableStore`.
- 21 unit test mới (chạy tiếp gián đoạn hai lần với batch size khác trùng tuyệt đối metric, record và nội dung ảnh; top-K; thumbnail; hai store với client S3 giả và `httpx.MockTransport`).
#### Thay đổi
- CLI `advertest run` dùng `RunExecutor`; bố cục store và đầu ra như Phase 2; 58 test nghiệm thu Phase 2 pass.
#### Quyết định (người dùng chốt; đã ghi vào `requirements.md` Phase 3)
- Run dừng do giới hạn: mọi metric, kể cả mAP sạch, tính trên ảnh đã xử lý (Decisions).
- Loader theo sha256 cho worker đặt trong `ml_core/runner` (Executor dùng chung).
- Ghi vào spec theo review: ứng viên chỉ bị xóa khi hoàn tất, hoàn tất chạy lại được; thời gian batch không gồm upload; `PresignedStore.put` ghi đè được; `MinioStore` nhận client truyền vào; checkpoint theo danh sách ảnh. `validation.md` thêm mục "không xin được URL cho run không `running`".
#### Review
- Review nhanh (do chính agent viết nhánh, không độc lập): 1 điểm phải sửa trước khi merge, đã sửa (unit test thứ tự top-K, bằng điểm, `evict`). `make check` pass (546 test Python, 153 test nghiệm thu, 36 Vitest).
#### Tồn đọng
- Chưa đo kích thước checkpoint trên KITTI 300 ảnh với model thật.
- `from_checkpoint` chưa từ chối `image_id` trùng trong `done` (checkpoint do executor ghi nên không xảy ra).

### Phase 3 — Group 0 (người duyệt) — 2026-09-29
#### Contract
- `RunResult.cached_from_run_id` (chỉ khi `skipped`/`cached`); `RunMetrics.partial` (mặc định `false`, `true` khi và chỉ khi `stopped_limit`); mock `stopped_limit_time_partial`, `skipped_cached_phase3`.
- `compute_failure_case_id(fingerprint, run_id, image_id)`; `CaseArtifacts.clean_thumb`, `adversarial_thumb` (nullable: CLI không tạo); mock `failure_case_record/worker_minio` theo bố cục MinIO.
- Enum `ProtocolStatus` (`active`, `retired`, `dev`); `ErrorCode` thêm `unauthenticated`, `forbidden`, `not_found`, `conflict`.
- Schema mới: `WorkerLease`, `WorkerJobBundle` (`BundleRun`, `BundleCheckpoint`, `BundleDownloads`, `BundleLimit`), `HeartbeatRequest`, `RunStartRequest`, `RunStartResponse`, `ProgressReport`, `WorkerDirective`, `ArtifactUrlRequest`, `ArtifactUrlResponse`, `CostProfile`, `RunCompletion`; kiểu `ObjectKey` (không có `.`/`..`, không `/` đầu), `PresignedUrl`. Mỗi schema có mock; 26 JSON Schema.
- OpenAPI `/internal/worker`: thêm `GET experiments/{id}/bundle`, `POST runs/{id}/start`, `POST cost-profiles`; body và response theo schema mới; `lease` khai `200 WorkerLease` / `204`; `complete`, `cost-profiles` trả `204`. Giữ `experiments/{id}/search-result` (Phase 7).
#### Thêm
- `httpx==0.28.1` thành dependency chính; package `advertest_worker` (`backend/worker/advertest_worker/`, mới có `__init__.py`), script `advertest-worker = advertest_worker.cli:app` (Group 4 viết `cli.py`); mypy, ruff khai package mới.
#### Thay đổi
- Test nghiệm thu Phase 0: danh sách enum (`ErrorCode`, `ProtocolStatus`) và endpoint worker theo Phase 3. Phase 2: `test_case_id_is_uuid5_of_fingerprint_run_and_image`.
- Ngoài thư mục người duyệt (người dùng cho phép): `ml_core/runner/run.py` truyền `run_id` vào `compute_failure_case_id` (1 dòng); `backend/app/tests/api/test_skeleton.py` cập nhật danh sách endpoint worker, gọi thử heartbeat và artifact-url kèm body từ `contracts/mocks` (nay có body bắt buộc), thêm `GET bundle`.
#### Review
- Review nhanh (do chính agent viết nhánh, không độc lập): 2 điểm phải sửa trước khi merge, đã sửa: `test_skeleton.py` gọi thử lại đủ heartbeat, artifact-url; `validation.md` ghi `RunCompletion` thay `RunResult`. `make check` pass (525 test Python, 153 test nghiệm thu, 36 Vitest); `make test-db` 41 test pass.
#### Quyết định (người dùng chốt; đã ghi vào `requirements.md` Phase 3)
- Lease có `lease_id`; request của worker gửi kèm, `lease_id` cũ → `409` (`validation.md` thêm 1 mục).
- `artifact-url` cấp presigned `PUT`, `GET`, `DELETE`; worker tự chép ứng viên sang `cases/` và xóa phần thừa.
- Người duyệt (agent) tự chọn, ghi vào `requirements.md`: bundle có `inference_params`, `failure_cases_per_run`, `cost_profiles`; `RunCompletion` không dùng cho run `cached`; run `incompatible` hoặc lỗi khi dựng attack vẫn đi qua `start` rồi `complete`.

### Phase 3 — kickoff (spec) — 2026-09-29
#### Quyết định (người dùng chốt)
- `POST /complete` nhận `RunCompletion` (`run_result` + `failure_cases`); API kiểm tra record và khóa artifact, ghi bảng `failure_cases` (sửa bảng cho khớp `FailureCaseRecord`) (`requirements.md` Phase 3, bảng API và Decisions; `plan.md` task 2, 10, 21, 28).
- `FailureCaseRecord.id = compute_failure_case_id(fingerprint, run_id, image_id)`; đóng câu hỏi mở (`requirements.md` Phase 3). Group 0 sửa contract, mock và test nghiệm thu Phase 2 liên quan.
- Worker: `httpx==0.28.1` thành dependency chính, entry point riêng `advertest-worker run|calibrate` (`plan.md` task 4b, 29; `tech-stack.md` mục 11).
- Worker mặc định chạy trực tiếp; compose có profile `cpu` (CI) và `gpu` (tồn đọng khi chưa có máy GPU); đóng câu hỏi mở (`requirements.md`, `validation.md` Manual Checks).
- Calibration: n = min(20, số ảnh của slice), batch tối đa min(n, 32), trên CPU dừng khi `sec_per_image` không giảm (`requirements.md` mục Calibration, `validation.md`).
- Giới hạn thời gian mặc định 2 giờ theo `tech-stack.md` mục 4.2; đóng câu hỏi mở.
#### Tồn đọng
- Lỗ hổng độ phủ chưa xử lý (xem báo cáo kickoff): user MinIO riêng cho api, image CUDA; `DEFAULT_STORE_DIR`, `import-local` không có `--as`; test tự động cho "chỉ upload ảnh thuộc slice", `kind = local`/`billing_mode = none`, seed `dev-open`, `lease` trả `204`, `experiment list`/`show --watch`; cột `environment` của `cost_profiles`; task 23 và 30 không có trong requirements; trạng thái experiment khi mọi run `failed`; seed đã tạo sẵn target `local-dev` (trùng với `compute-target create --name local-dev`).

---

## Phase 2 — Attack white-box đầu tiên

**Trạng thái:** ✅ hoàn thành 2026-09-28, **còn tồn đọng** (người dùng cho phép đóng phase và cập nhật sau). Group 0–4 đã merge.

### Phase 2 — Tổng kết (phase-close) — 2026-09-28
- **Giao được:** adapter ART → `Perturbation` cho `fgsm`, `pgd_linf`, `pgd_l2` (mask vùng ảnh thật, áp lại sau `generate`); metric sau tấn công (ASR, FP mới, mức sụt, `RunMetrics`); chọn failure case kèm 3 PNG và `FailureCaseRecord`; fingerprint, manifest, cache theo fingerprint, `--force`; CLI `advertest run --config [--force]`, `advertest run show`.
- **Contract:** `Perturbation.apply(..., mask)`, `FingerprintInputs.git_dirty`, `RunMetrics.attack_success_rate` nhận `null`, schema `FailureCaseRecord`. Người duyệt đã chấp nhận (Group 0).
- **Số liệu cuối:** `make check` pass trên `main` (463 test Python, 152 test nghiệm thu gồm 58 của Phase 2, 36 test Vitest); `make test-db` 41 test pass. KITTI (CPU): mAP@0.5 sạch 0.5332 → PGD L∞ eps 2/255: 0.0123, eps 4/255: 0.0017; FGSM eps 4/255: 0.1765; PGD L2 eps 1: 0.0556. PGD 1.3 s/ảnh, FGSM 0.17 s/ảnh. Chạy lại `--force` trùng tuyệt đối.
- **`validation.md`:** Automated Tests đủ; 5/7 Manual Checks (người dùng xác nhận); Definition of Done 4/5.
- **CI:** xanh sau khi push `main` gồm phần đóng phase (người dùng xác nhận, 2026-09-29); đánh dấu Definition of Done "Automated Tests pass trên CI".
- **Tồn đọng (cập nhật khi có kết quả):**
  - 2 manual check cần GPU: thời gian mỗi ảnh và batch size lớn nhất khi tính gradient trên GPU; `--force` trên GPU nằm trong sai số.
- **Lưu ý:** các group của người duyệt (0, 4), việc review và merge do agent làm thay theo ủy quyền của người dùng; review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Phase 2 — kickoff (spec) — 2026-09-28
#### Thay đổi
- `attack_success_rate` là `null` khi `|C| = 0`; chạy bằng CLI thì `compute_target_id = null`; cấu hình đọc bằng PyYAML; `git_dirty` bỏ qua `.ai-log/`; run `cached` chỉ in ra, không ghi store; ảnh nhiễu khuếch đại L2 chia theo `max|δ|`; ml-core được sửa `configs/examples/` (`requirements.md`, `plan.md`, `validation.md` Phase 2; `tech-stack.md` mục 11).
#### Quyết định
- Preset `kitti-coco` giữ nguyên, không gộp `bus` vào `truck`; đóng câu hỏi mở (`requirements.md` Phase 2, Decisions).
- Manual check cần GPU chạy trên CPU; phần GPU là tồn đọng (`validation.md` Phase 2).
#### Tồn đọng
- Lỗ hổng độ phủ chưa có mục trong `validation.md`: nhãn cho attack là ground truth, `new_false_positives` trừ số trên ảnh sạch, mAP sạch từ cache, `experiment_id`, `environment`/`gpu_seconds`/`cost`, `inference_params` đổi fingerprint, `run show`, nội dung PNG nhiễu.

### Replan sau Phase 2 — 2026-09-28
- Phase 3 `requirements.md`: `RunExecutor` giữ hành vi Phase 2 (mask áp lại sau `generate`, lọc/ghép prediction, top-K chép riêng ảnh, lỗi khi dựng attack → `failed`); checkpoint chứa prediction đã lọc class đích, không chứa ảnh; CLI giữ bố cục `runs/<fingerprint>/`, MinIO dùng `runs/<run_id>/`; image worker đặt `GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`; `submit --config` dùng `LocalRunConfig`; câu hỏi mở mới về `FailureCaseRecord.id` trùng khi hai run cùng fingerprint chạy đồng thời.
- Phase 3 `plan.md` task 5 và 32; `validation.md` thêm 2 test (manifest trong Docker, checkpoint không chứa ảnh).
- `roadmap.md`: thêm mục "(Từ Phase 2)" cho Phase 3, 6 (lưới mịn ở eps nhỏ), 7 (khoảng tìm kiếm bắt đầu dưới 1/255), 8 (report ghi eps trên ảnh float letterbox, xem lại số failure case).
- Rủi ro: checkpoint nặng nếu lưu prediction thô; YOLOv8n trên ảnh float bão hòa ở mọi mức eps của catalog; thời gian và batch size trên GPU vẫn chưa đo (calibration Phase 3 là lần đo đầu tiên).

### Phase 2 — Group 4 (người duyệt) — 2026-09-28
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_02/` (58 test: Chung, Tính đúng của attack, Metric, Failure case, Fingerprint/manifest/cache, Trạng thái), chạy trên fixture thật bằng CPU; luồng dựng qua CLI trong store tạm; khoảng 1 phút 40 giây cả bộ nghiệm thu.
- Golden value `tests/fixtures/golden/phase_02.json`: mAP@0.5 sạch 0.5186; `fgsm` eps 4: mAP@0.5 0.2231, ASR 0.6; `pgd_linf` eps 4: mAP@0.5 0.0016, ASR 0.9333; sai số ±0.01.
- `validation.md`: 9 mục bổ sung độ phủ (nhãn attack là ground truth, FP mới trừ số ảnh sạch và bỏ class không đích, mAP sạch từ cache, `experiment_id`, `environment`/`gpu_seconds`/`cost`, `inference_params` đổi fingerprint, `run show`, bảng tóm tắt, ảnh nhiễu ở vùng pad) và bố cục `attempts/`.
#### Thay đổi
- `requirements.md`: ghi các quyết định của Group 1–3 (mask áp lại sau `generate`, `level` ngoài dải, lọc và ghép prediction, bố cục store, đầu ra CLI, box trong failure case, `DOCKER_IMAGE_DIGEST`, `GIT_COMMIT`); trả lời 2 câu hỏi mở.
- Sửa lỗi import vòng `ml_core.runner.run` ↔ `ml_core.cli` (vai trò ml-core, nhánh `phase02-ml-core-fix`, đã merge): phát hiện khi viết test nghiệm thu.
#### Số liệu đo được (KITTI, slice 300 ảnh seed 42, YOLOv8n, CPU 16 luồng, batch 8, seed 0)
- mAP@0.5 sạch 0.5332, mAP@0.5:0.95 sạch 0.3042 (khớp baseline Phase 1, lấy từ cache).

| Attack | eps | mAP@0.5 | Relative drop | ASR |
|---|---|---|---|---|
| `pgd_linf` | 2/255 | 0.0123 | 0.977 | 0.767 |
| `pgd_linf` | 4/255 | 0.0017 | 0.997 | 0.903 |
| `pgd_linf` | 8/255 | 0.0005 | 0.999 | 0.948 |
| `pgd_linf` | 16/255 | 0.0001 | 1.000 | 0.984 |
| `fgsm` | 4/255 | 0.1765 | 0.669 | 0.438 |
| `fgsm` | 8/255 | 0.1631 | 0.694 | 0.481 |
| `pgd_l2` | 1 | 0.0556 | 0.896 | 0.623 |
| `pgd_l2` | 2 | 0.0142 | 0.973 | 0.790 |
| `pgd_l2` | 4 | 0.0037 | 0.993 | 0.872 |
| `pgd_l2` | 8 | 0.0010 | 0.998 | 0.932 |

- Thời gian: PGD 1.3 s/ảnh (L∞ và L2), FGSM 0.17 s/ảnh; sweep `pgd_sweep.yaml` 48 phút (2 mức đầu chậm hơn vì test chạy song song), `pgd_l2` 26 phút; RAM tối đa 3.3 GB.
- Chạy lại với `--force`: 6 run trùng tuyệt đối với lần đầu (mAP, ASR, danh sách failure case), cùng fingerprint, ghi vào `reruns/`. `git_dirty = false` (chạy từ worktree sạch tại `6554445`).
- Failure case (`pgd_linf` eps 8, 5 case xem bằng mắt): box ground truth, prediction và ignore region khớp ảnh; nhiễu không nhìn thấy trên ảnh sau tấn công; ảnh nhiễu khuếch đại chỉ có nhiễu trong vùng ảnh thật (vùng pad = 128). Sau tấn công xe biến mất và xuất hiện 40–52 detection sai, phần lớn trên nền.
#### Quyết định (người dùng chốt)
- Giữ dải eps của catalog; vùng hữu ích nằm dưới `pgd_l2` eps 1 và `pgd_linf` eps 2/255 (`requirements.md`, Open Questions).
- Giữ 20 failure case mỗi run, xem lại ở Phase 8.
#### Tồn đọng
- Manual check cần GPU: thời gian mỗi ảnh và batch lớn nhất khi tính gradient, `--force` trên GPU.
- Replan (phase-close): Phase 6 cần lưới mịn ở eps nhỏ (dưới 1/255 với L∞); Phase 7 cần khoảng tìm kiếm mặc định nhỏ; YOLOv8n trên ảnh float không lượng tử hóa rất dễ bị tấn công, report nên ghi rõ.

### Phase 2 — Group 3 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/runner/`: `config.py` (`LocalRunConfig`, YAML, `experiment_id`, đối chiếu spec với catalog), `env.py` (`git_state` bỏ `.ai-log/`, thiết bị, `environment`, `DOCKER_IMAGE_DIGEST`), `fingerprint.py` (`config_sha256` riêng từng run), `run.py` (quét lưới: cache theo fingerprint, `--force`, attack theo batch có mask letterbox, metric, top-k failure case, PNG, `FailureCaseRecord`, manifest, `RunResult`).
- CLI `advertest run --config <yaml> [--force]` (stdout: mảng JSON `RunResult`; stderr: tiến độ, cảnh báo, bảng tóm tắt) và `advertest run show <fingerprint>`.
- `configs/examples/pgd_sweep.yaml` (PGD L∞ 2, 4, 8, 16; FGSM 4, 8) với id KITTI trong `data/store`.
- 36 unit test (YOLOv8n ngẫu nhiên, KITTI tổng hợp; bài kiểm tra gradient được giả lập).
#### Thay đổi
- `current_git_commit`, `describe_device`, `default_device` chuyển sang `ml_core/runner/env.py`; `advertest eval` dùng chung, cảnh báo working tree bẩn nay bỏ qua `.ai-log/`.
#### Quyết định (cần ghi vào `requirements.md` Phase 2)
- Bố cục store (người dùng chốt): `runs/<fp>/` chỉ cho `completed` (`result.json` ghi sau cùng); `failed` và `skipped/incompatible` ở `runs/<fp>/attempts/<run_id>/`; `--force` khi đã có kết quả ghi vào `reruns/<run_id>/`, khi chưa có thì ghi thư mục chính.
- Run `cached` chép `metrics`, `failure_case_ids`, `progress` từ kết quả cũ; không ghi store.
- Box trong `FailureCaseRecord`: prediction đã lọc (class đích, score ≥ `operating_conf`, ngoài ignore region).
- `docker_image_digest` từ biến `DOCKER_IMAGE_DIGEST` (không có thì `"none"`); có `GIT_COMMIT` thì `git_dirty = false`.
#### Review
- Review (do chính agent viết code, không độc lập) tìm 2 lỗi nên sửa, đã sửa trước khi merge: ảnh failure case giữ view của cả batch (có thể tốn khoảng 1.5 GB RAM với 300 ảnh); lỗi khi dựng attack làm dừng cả lệnh thay vì ghi `failed`.
#### Số liệu đo được (5 ảnh fixture, YOLOv8n, CPU, `advertest run`)
- mAP@0.5 sạch 0.5186 (khớp golden Phase 1). Sau tấn công: PGD L∞ eps 4 → 0.0016 (ASR 0.933), eps 16 → 0.0 (ASR 1.0); FGSM eps 4 → 0.2231 (ASR 0.6), eps 8 → 0.2053 (ASR 0.667). Tổng 21 s; lần hai (cached) 3.7 s.
- Batch 1 và batch 5 cho kết quả trùng tuyệt đối; vùng pad trong PNG của 5 failure case giữ nguyên, ảnh nhiễu ở vùng pad bằng 0.5.
#### Tồn đọng
- Phase 3: run lỗi giữa lúc ghi artifact vào `runs/<fp>/` có thể để lại file thừa (nên ghi vào thư mục tạm rồi đổi tên).

### Phase 2 — Group 2 (ml-metric) — 2026-09-28
#### Thêm
- `ml_core/metrics/attack.py`: `match_predictions` (ghép một-một), `image_attack_stats` / `ImageAttackStats` (`correct`, `lost`, `new_false_positives`, `severity_score`), `attack_success_rate`, `compute_drops`, `build_run_metrics` (dựng `RunMetrics`), `severity_score`, `select_failure_cases`; 17 unit test.
#### Quyết định (người dùng chốt; cần ghi vào `requirements.md` Phase 2 mục Metric)
- Trước khi ghép, prediction được lọc như pipeline mAP (class đích, bỏ IoA ≥ 0.5 với ignore region), cho cả tập C và FP mới.
- Ghép một-một cho cả ảnh sạch và ảnh sau tấn công.
- Agent tự chọn: IoU ≥ 0.5 tính cả biên; ghép với ground truth có IoU lớn nhất; `absolute_drop` có thể âm; `image_id` so theo chuỗi khi xếp failure case.
#### Số liệu đo được (YOLOv8n, 3 ảnh fixture, ground truth = prediction sạch ≥ 0.5, CPU)
- ASR: FGSM eps 4 = 0.6; PGD L∞ eps 4 và 16 = 1.0. FP mới mỗi ảnh: 7–9 (FGSM), 14–38 (PGD).

### Phase 2 — Group 1 (attack) — 2026-09-28
#### Thêm
- `attacks/registry.py`: `load_catalog`, `get_spec` (theo `name` trả version cao nhất, hoặc theo `spec_sha256`), `UnknownAttack`.
- `attacks/art_adapter.py`: `ArtPerturbation` (FGSM, PGD L∞, PGD L2 qua ART), `build_perturbation(spec, estimator)`, `IncompatibleAttack`, `UnsupportedAttack`; 27 unit test với estimator giả (`PyTorchYolo` bọc model tuyến tính nhỏ).
#### Quyết định (cần ghi vào `requirements.md` Phase 2)
- ART 1.20.1 bỏ qua `mask` trong `FastGradientMethod` khi estimator là object detector (đã xác nhận: nhiễu 8/255 ở vùng pad); adapter truyền mask cho ART rồi áp lại mask sau `generate` (vùng pad lấy nguyên ảnh gốc) và cắt về `clip_values`.
- `level` ngoài `[min, max]` của spec → `ValueError`; PGD thiếu `eps_step_ratio` dùng 0.25.
#### Số liệu đo được (YOLOv8n, 2 ảnh fixture, CPU)
- FGSM eps 8: 0.16 s/ảnh; PGD L∞ eps 8: 1.3 s/ảnh; PGD L2 eps 2: 1.5 s/ảnh. Vùng pad giữ nguyên chính xác; loss tăng (PGD L∞ 2.1 → 27.3).
- PGD L∞ làm số detection ≥ 0.25 tăng mạnh (7 → 46, 10 → 67): FP mới nhiều, ASR có thể thấp hơn kỳ vọng.

### Phase 2 — Group 0 (người duyệt) — 2026-09-28
#### Contract
- `Perturbation.apply` thêm `mask: MaskBatch | None = None` (N, 1, H, W), float32; `tech-stack.md` mục 3.1 cập nhật.
- `FingerprintInputs.git_dirty: bool` (bắt buộc); mock `manifest/gpu_local.json` tính lại fingerprint (`712a8585…`).
- `RunMetrics.attack_success_rate: UnitFloat | None`; mock mới `run_result/completed_no_detections.json`.
- Schema mới `FailureCaseRecord` (`schema_version = 1`) với `CaseBox`, `CaseIgnoreRegion`, `CaseDetections`, `CaseArtifacts`, hàm `compute_failure_case_id`; mock `failure_case_record/pgd_linf_eps8.json`. Validator: `id` đúng `compute_failure_case_id(fingerprint, image_id)`, `severity_score = lost_objects + 0.5 × new_false_positives` và > 0, ground truth không có score, prediction bắt buộc có score.
- Seed `fgsm`, `pgd_linf`, `pgd_l2` khớp bảng `requirements.md`, không sửa.
- Sinh lại JSON Schema (15), `openapi.json`, `frontend/src/contracts/`.
#### Thêm
- Dependency `pyyaml==6.0.3` (đã có trong `uv.lock` qua ultralytics); mypy khai `yaml` trong `ignore_missing_imports` (`tech-stack.md` mục 7, 11).
#### Thay đổi
- Test nghiệm thu Phase 0 `test_fingerprint_changes_with_every_input`: thêm `git_dirty` vào danh sách trường phải làm đổi fingerprint (chặt hơn, người dùng cho phép).
#### Quyết định (người dùng chốt)
- `FailureCaseRecord` có thêm trường `fingerprint` để schema tự kiểm tra `id`; box ghi `class_name` (class đích), ignore region là `{bbox, source}` (`requirements.md` Phase 2, bảng `FailureCaseRecord`).
#### Số liệu đo được
- `make check` pass: 383 test Python, 94 test nghiệm thu, 36 test Vitest; `contracts-check` sạch.
#### Tồn đọng
- Phase 3: bảng DB `failure_cases` (`artifact_uri`, `thumbnail_uri`, `details`) khác schema `FailureCaseRecord`; `id` trùng giữa lần chạy gốc và `--force` (cùng fingerprint, cùng ảnh) sẽ xung đột khóa chính khi lưu DB.

## Phase 1 — Inference và metric

**Trạng thái:** ✅ hoàn thành 2026-09-28, **còn tồn đọng** (người dùng cho phép đóng phase và cập nhật sau). Group 0–6 đã merge; mục chi tiết từng group (`### Phase 1 — Group …`) nằm bên dưới, xen với mục Phase 0 theo thứ tự thời gian.

### Phase 1 — Tổng kết (phase-close) — 2026-09-28
- **Giao được:** CLI `advertest` chạy trọn `dataset import-kitti` → `model register` → `slice create` → `mapping create` → `eval` → `viz`; wrapper YOLOv8n cho ART (model luôn ở eval, bài kiểm tra gradient); converter KITTI, mapping `kitti-coco` có lọc Moderate, slice theo hash; mAP bằng torchmetrics/pycocotools theo `max_det`; cache prediction thô; kho `LocalStore` bất biến.
- **Contract:** `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping`; `IgnoreRegion.source` chấp nhận `difficulty:`. Người duyệt đã chấp nhận.
- **Số liệu cuối:** `make check` pass trên `main` (376 test Python, 94 test nghiệm thu gồm 42 của Phase 1, 36 test Vitest). Baseline KITTI (CPU): mAP@0.5 = 0.533, mAP@0.5:0.95 = 0.304; golden trên fixture 0.5186 / 0.3524.
- **`validation.md`:** 42/42 Automated Tests; 4/7 Manual Checks; Definition of Done 5/6.
- **CI:** xanh sau khi push `main` gồm phần đóng phase (người dùng xác nhận); đánh dấu Definition of Done "Automated Tests pass trên CI".
- **Tồn đọng (cập nhật khi có kết quả):**
  - 3 manual check cần GPU: `eval` trên GPU local (ghi `sec_per_image`, batch size), lần hai trên GPU (cache hit nhanh rõ rệt), theo dõi VRAM và batch size lớn nhất. Máy phát triển hiện không có GPU; baseline đang là số đo CPU.
- **Lưu ý:** các group của người duyệt (0, 6) và việc review, merge do agent làm thay theo ủy quyền của người dùng; review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Replan sau Phase 1 — 2026-09-28
- Phase 2 `requirements.md`: nhãn cho attack lấy từ `SliceLoader` (chỉ số class trong model); mask dựng từ `LetterboxInfo`; mAP sau tấn công qua `CleanMetric` theo `max_det`, mAP sạch từ cache Phase 1; `config_sha256` dùng `LETTERBOX_CONFIG`; `git_commit` lấy như `advertest eval`; câu hỏi mở mới về `Truck`/`bus` trong preset `kitti-coco` (chốt trước golden Phase 2).
- Phase 2 `plan.md` task 19: chuyển `current_git_commit`, `describe_device` sang `ml_core/runner/env.py` để `eval` và `run` dùng chung.
- `roadmap.md` Phase 3: thêm mục "(Từ Phase 1)" (ảnh theo sha256 trên MinIO thay đường dẫn tuyệt đối, `DEFAULT_STORE_DIR`, `import-local` đọc bố cục `LocalStore`, chỉ admin đăng ký model).
- Rủi ro: PGD trên CPU ước khoảng 2 s/ảnh (khoảng 1 giờ cho sweep 6 mức eps trên 300 ảnh); ảnh KITTI của Ultralytics là JPEG mang đuôi `.png` (content-type trên MinIO phải theo định dạng thật).
- Câu hỏi còn mở: YOLOv8 hay YOLOv11.

## Phase 0 — Contract và khung dự án

**Trạng thái:** ✅ hoàn thành 2026-09-28. Group 1–10 đã merge; mọi mục trong `validation.md` và Definition of Done đã đạt.

Ghi chú chung: các group của người duyệt (1, 2, 8, 9) do agent soạn thay theo cho phép của người dùng; mọi nhánh được review trước khi merge, nhưng review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Phase 0 — Group 1 (người duyệt) — 2026-09-27
#### Thêm
- Cấu trúc thư mục theo `tech-stack.md` mục 8; `.gitignore`.
- Python workspace bằng uv: một `pyproject.toml` gốc, 4 package `advertest_contracts`, `ml_core`, `attacks`, `backend`; `uv.lock`.
- Cấu hình ruff và mypy (strict cho `contracts/` và `backend/`), pytest.
- Frontend khung: Vite, React, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, React Router, ESLint, Prettier.
- `Makefile` với các lệnh chung.
#### Thay đổi
- Bỏ theo dõi `.env` trong git (file đã từng được commit và push lên `origin`).
#### Quyết định
- torch chọn biến thể bằng extra `cpu`/`cuda` của uv trong cùng một lockfile (`tech-stack.md` mục 11).
- Target `make` của phần chưa có báo "Chưa có (Group N)" và thoát lỗi; `make check` coi "chưa có test" là pass (ghi trong `Makefile`).
#### Tồn đọng
- Khóa `AI_LOG_API_KEY` vẫn còn trong lịch sử git: cần đổi khóa.

### Phase 0 — Group 2 (người duyệt) — 2026-09-27
#### Thêm
- 16 enum, 7 schema Pydantic (`AttackSpec`, `AttackConfig`, `ExperimentConfig`, `RunResult`, `Manifest`, `SearchResult`, `ProtocolBody`), interface `Perturbation`.
- `canonical_json` theo RFC 8785, `sha256_of`, `compute_fingerprint`, `content_id` (uuid5, namespace cố định trong `advertest_contracts.ids`).
- Mock cho mọi schema (đủ mọi `RunStatus`, `SearchStatus`); seed catalog `fgsm`, `pgd_linf`, `pgd_l2`.
- `scripts/gen_contracts.py`: JSON Schema, TypeScript type (openapi-typescript); `make contracts-check`.
#### Contract
- Schema mới, mọi schema bắt đầu ở `schema_version = 1`. `status_reason.code` có thêm `cancelled`.
#### Quyết định
- `canonical_json` theo RFC 8785; seed chỉ gồm attack của Phase 2; `openapi-typescript`; mã `cancelled` (`requirements.md`, `plan.md` Phase 0, `tech-stack.md`).
- Sau review: `Environment` được phép null; tiền là `Decimal` (chuỗi trong JSON); các ràng buộc schema bổ sung; Phase 1 dùng `content_id` của contract (`requirements.md` Phase 0, `tech-stack.md` mục 4.1, `plan.md` Phase 1).
#### Số liệu đo được
- `canonical_json` khớp `JSON.stringify` của Node trên 60.014 số.

### Phase 1 — kickoff (spec) — 2026-09-27
#### Thay đổi
- Fixture là 5 ảnh KITTI kèm label; ID của slice/mapping sinh từ hash toàn bộ nội dung (`slice_sha256`); CLI dùng Typer, lệnh đặt theo thư mục của từng agent; ground truth dưới mức Moderate của KITTI thành ignore region (`requirements.md`, `plan.md`, `validation.md` Phase 1; `tech-stack.md`).

### Phase 1 — Group 6 (người duyệt) — 2026-09-28
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_01/` (42 test: Chung, Letterbox, Dữ liệu, Model, Metric, Đánh giá và cache), chạy trên fixture thật bằng CPU; luồng dựng qua CLI trong store tạm.
- Golden value `tests/fixtures/golden/phase_01.json`: mAP@0.5 0.5186, mAP@0.5:0.95 0.3524, sai số ±0.01 (dataset `5b3d46a7…`, slice seed 42, CPU).
#### Thay đổi
- `.gitignore`: cho phép commit `tests/fixtures/golden/`.
#### Số liệu đo được (KITTI thật, CPU, máy phát triển không có GPU)
- `dataset import-kitti` trên `data/raw/kitti/training/`: 7.481 ảnh, 40.570 annotation, 11.295 `DontCare`; 10 giây; không có bbox vượt khung. `dataset_version_sha256` = `cfd54b7f9e35d30670a99fa3630ac94ff3a54318d12ba98dde6bd36bea490f25`.
- Slice 300 ảnh seed 42: `slice_sha256` = `19356539b9bd…` (id `37341deb-7761-5c9b-adf1-e84a9d3f53a8`); ground truth sau mapping: `car` 719, `person` 135, `truck` 26.
- **Baseline YOLOv8n:** mAP@0.5 = 0.5332, mAP@0.5:0.95 = 0.3042; AP@0.5 `car` 0.842, `person` 0.570, `truck` 0.188. `supports_gradients = true`.
- Thời gian (CPU 16 luồng, batch 8): 0.065 s/ảnh khi cache miss; 0.0096 s/ảnh khi cache hit.
- `viz` 8 ảnh (`000004`, `000028`, `000057`, `000062`, `000100`, `000169`, `000183`, `000216`): box ground truth và prediction khớp vị trí sau letterbox; ignore region phủ đúng xe bị cắt ở mép ảnh và xe bị che.
#### Quyết định
- Câu hỏi mở về baseline đã trả lời: mAP@0.5 = 0.533 ≥ 0.4 nên không cần fine-tune hay đổi kích thước đầu vào (`requirements.md` Phase 1, Open Questions).
#### Tồn đọng
- Manual check cần GPU (máy này không có): `eval` trên GPU local, cache hit nhanh rõ rệt, theo dõi VRAM, batch size lớn nhất.
- Bản KITTI của Ultralytics là JPEG mang đuôi `.png` (nén lại), baseline có thể lệch nhẹ so với ảnh PNG gốc.
- AP `truck` thấp vì `Truck` của KITTI gồm cả xe buýt (YOLO: `bus`): xem lại preset `kitti-coco` khi replan.
- Câu hỏi mở còn lại: chốt YOLOv8 hay YOLOv11.

### Phase 1 — Group 5 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/cli/`: cache prediction thô (`cache.py`), lệnh `eval` (`evaluate.py`), lệnh `viz` (`viz.py`); `letterbox_info` trong `ml_core/preprocess/`.
#### Quyết định
- Khi cache hit, ground truth tính từ manifest không đọc ảnh; `device` là thiết bị đã tạo prediction, lưu trong file cache (sửa sau review); mặc định GPU nếu có, batch size 8; hết VRAM báo lỗi kèm gợi ý; `git_commit` từ `GIT_COMMIT` hoặc `git rev-parse HEAD`; `viz` vẽ prediction thuộc class đích có score ≥ `operating_conf` (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU)
- `advertest eval`: mAP@0.5 = 0.5186, mAP@0.5:0.95 = 0.3524 (khớp Group 4); cache miss 0.087 s/ảnh, cache hit 0.016 s/ảnh, metric giống hệt.
- `viz` ảnh `000902`: box ground truth và prediction khớp vị trí xe sau letterbox.
#### Tồn đọng
- AP `truck` = 0 trên fixture vì KITTI gán `Truck` cho xe buýt, YOLO nhận là `bus` (không có trong mapping). Xem lại preset `kitti-coco` khi replan, sau khi có baseline KITTI.
- Mỗi khóa cache khoảng 10 MB JSON với slice 300 ảnh.
- Trên máy phát triển luôn có cảnh báo working tree bẩn do `.ai-log/` được git theo dõi.

### Phase 1 — Group 4 (ml-metric) — 2026-09-28
#### Thêm
- `ml_core/metrics/`: `filter_classes`, `filter_ignored` (IoA ≥ 0.5); `CleanMetric` (torchmetrics, backend `pycocotools`); `build_clean_eval_result`.
#### Quyết định
- Giới hạn detection khi tính mAP là `[1, 10, max_det]` (người dùng chốt); AP tính từ tensor `precision` vì `pycocotools.summarize` viết cứng `maxDets=100` cho mAP@0.5:0.95 (người dùng chấp nhận sau review); `per_class` đủ class đích; báo lỗi khi slice không có ground truth (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU, dataset `5b3d46a7…`)
- YOLOv8n trên 5 ảnh: mAP@0.5 = 0.5186, mAP@0.5:0.95 = 0.3524; AP@0.5 `person` 0.832, `car` 0.724, `truck` 0.0 (1 ground truth). Golden value dự kiến cho Group 6.
- Trên fixture, `max_det` 100 hay 300 cho cùng kết quả (sau khi lọc class đích mỗi ảnh còn dưới 100 box).
#### Tồn đọng
- Group 6: so mAP của pipeline với `YOLO.val` của Ultralytics trên cùng slice để phát hiện lệch lớn.

### Phase 1 — Group 2 (ml-data) — 2026-09-28
#### Thêm
- `ml_core/data/`: parser label KITTI và `import_kitti`; lưu dataset và thư mục nguồn; preset `kitti-coco`, `apply_mapping` (`unmapped`, `difficulty`), `build_mapping`; slice theo bộ lọc tự mô tả; `SliceLoader`; lệnh `dataset import-kitti`, `mapping create`, `slice create`.
#### Quyết định
- Thư mục nguồn của ảnh ghi trong store, loader kiểm tra sha256 từng ảnh; `--root` trỏ thẳng tới thư mục có `image_2/`, `label_2/`; `categories` là 8 class KITTI cố định; lấy mẫu slice bằng `random.Random(seed)`; `labels` của loader là chỉ số class trong model; thiếu `truncated`/`occluded` thì không xét; CLI in JSON (`requirements.md` Phase 1).
#### Số liệu đo được (fixture)
- 5 ảnh, 59 annotation, 7 `DontCare`; sau mapping `kitti-coco`: `car = 14`, `truck = 1`, `person = 6`; ignore region 33 `difficulty`, 5 `unmapped`, 7 `dont_care`.
- `dataset_version_sha256` của fixture theo converter này: `5b3d46a79658bc009e50c69c3e68dedbf49fa0d2e47d913c800e06a5a79f9774` (khác `9f5b413e…` của `tests/fixtures/manifest.json` Phase 0 chỉ ở `file_name` và tên converter; annotation và ignore region giống hệt). Golden value của Group 6 dùng hash mới.
#### Tồn đọng
- Phase 3: store đang lưu đường dẫn tuyệt đối của máy local; thay bằng ảnh theo nội dung trên MinIO.
- Loader import `load_card` từ `ml_core.models.register`, kéo theo ultralytics và ART khi nạp.
- Manual check: `import-kitti` trên 7.481 ảnh KITTI (bbox vượt khung ảnh sẽ bị contract từ chối).

### Phase 1 — Group 3 (ml-model) — 2026-09-28
#### Thêm
- `ml_core/models/`: `UltralyticsDetector` (predict có NMS theo `conf/iou/max_det`, loss `v8DetectionLoss`, model luôn ở eval), `build_estimator` (`PyTorchYolo`), bài kiểm tra gradient, `register_model` và lệnh `advertest model register`.
#### Thay đổi
- `pyproject.toml`: mypy bỏ qua thiếu type stub của `art` (`tech-stack.md` mục 7), người dùng cho phép.
#### Quyết định
- Wrapper tự viết thay cho `is_ultralytics=True` của ART; target của bài kiểm tra gradient là prediction của chính model (score ≥ 0.25); weights chép vào store; đăng ký lại trả card cũ; lỗi khi kiểm tra không ghi card (`requirements.md` Phase 1).
#### Số liệu đo được (fixture, CPU)
- Wrapper khớp `YOLO.predict` trên 5 ảnh: cùng số box (245–293), IoU nhỏ nhất 0.99998, score lệch tối đa 1.4e-6.
- Bài kiểm tra gradient trên YOLOv8n: loss 9.63 → 25.43 sau bước 2/255; state_dict và 114 tensor BatchNorm không đổi; `supports_gradients = true`.
- YOLOv8n khởi tạo ngẫu nhiên không đạt điều kiện "loss tăng" (loss gần như phẳng theo ảnh): unit test chỉ khẳng định gradient hợp lệ và model không đổi; điều kiện này cần có trong test nghiệm thu trên fixture (Group 6).

### Phase 1 — Group 1 (ml-core) — 2026-09-28
#### Thêm
- `ml_core/store/`: `ArtifactStore`, `LocalStore` (key bất biến, ghi nguyên tử), chỉ mục id → sha `index/<kind>/<id>`.
- `ml_core/preprocess/letterbox.py`: letterbox 640×640 (Pillow `BILINEAR`, pad 114/255, căn giữa), `LETTERBOX_CONFIG`, chuyển box hai chiều.
- CLI `advertest` (Typer): nhóm lệnh `model`, `dataset`, `slice`, `mapping`; `eval`, `viz` dạng khung (báo chưa có đến Group 5); tùy chọn chung `--store-dir`.
- Dependency `typer==0.27.2`, `pillow==12.3.0`, `pycocotools==2.0.11`; entry point `advertest` (`tech-stack.md` mục 11).
#### Thay đổi
- `.gitignore`: `data/` → `/data/` (dòng cũ bỏ qua cả `ml_core/data/`), người dùng cho phép.
#### Quyết định
- 3 Typer trong `ml_core/data/cli.py`; chỉ mục id do Group 1 làm; `--store-dir`; key bất biến và không bắt đầu bằng `.`; `LETTERBOX_CONFIG` cho khóa cache và fingerprint (`requirements.md`, `plan.md` Phase 1).

### Phase 1 — Group 0 (người duyệt) — 2026-09-28
#### Contract
- Schema mới, `schema_version = 1`: `ModelCard` (kèm `GradientCheck`), `ClassMapping` (thân `ClassMappingBody`, `compute_mapping_sha256`), `SliceSpec` (`SliceFilter`, `compute_slice_sha256`), `CleanEvalResult` (`InferenceParams`, `EvalMetrics`, `ClassEvalMetrics`, ...); kiểu dùng chung `DifficultyFilter`, `InferenceParams`.
- `IgnoreRegion.source` chấp nhận thêm `difficulty:<class>`; hash manifest fixture không đổi (`9f5b413e...`).
- Validator: mọi `id` phải là `content_id` của hash tương ứng; `ModelCard.supports_gradients == gradient_check.passed`, `details` bắt buộc khi fail; `SliceSpec.image_ids` sắp xếp, không trùng, đúng `size` phần tử; `ap50`/`ap50_95` là null khi và chỉ khi `num_gt = 0`.
- Mock: `model_card` (2), `class_mapping` (1), `slice_spec` (1), `clean_eval_result` (2). Sinh lại JSON Schema, `openapi.json`, `frontend/src/contracts/`.
#### Quyết định
- `len(image_ids) == size`: `slice create` báo lỗi khi không đủ ảnh đạt bộ lọc; AP của class không có GT là `null` (người dùng chốt, 2026-09-28).
- `ModelCard.framework` chỉ nhận `ultralytics` hoặc `torchvision` (phương án dự phòng Faster R-CNN).
- `slice_sha256` hash đúng 5 trường theo `requirements.md` (không gồm `schema_version`); `mapping_sha256` hash mọi trường trừ `id` và chính nó (gồm `schema_version`, cùng cách với `AttackSpec`).
#### Thay đổi
- Test contract `test_dataset_manifest_rejects_inconsistent`: case `difficulty:Car` (trước đây bị từ chối) đổi thành `foo:Car`, vì contract nay chấp nhận `difficulty:`.
#### Sau review
- Các quyết định trên đã ghi vào `requirements.md` Phase 1; `DifficultyFilter` ghi rõ ngưỡng tính cả biên (giữ khi cao ≥ 25, `occluded` ≤ 1, `truncated` ≤ 0.30).

### Phase 1 — kickoff lần 2 (spec) — 2026-09-28
#### Thay đổi
- Group 0 thêm 4 schema `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping` (mỗi schema `schema_version = 1`, không có version chung của gói); `ModelCard.lib_versions` dùng `LibVersions`; pattern `IgnoreRegion.source` chấp nhận `difficulty:.+` (`requirements.md`, `plan.md`, `validation.md` Phase 1).
- Bộ lọc slice tự mô tả (`classes`, `difficulty`, `min_objects`, mặc định từ preset `kitti-coco`); `slice create` không cần model hay mapping (`requirements.md`, `plan.md`, `validation.md` Phase 1).
- Cấu trúc file `ClassMapping` được định nghĩa (`requirements.md` Phase 1).
#### Quyết định
- Backend của `MeanAveragePrecision` là `pycocotools`; Group 1 thêm vào `pyproject.toml` (`tech-stack.md` mục 2, `plan.md` task 8).
#### Tồn đọng
- Group 0 chưa merge: Group 2–4 bị chặn.
- Lỗ hổng độ phủ chưa có test trong `validation.md`: `LocalStore` và chỉ mục id → sha, đầu ra dataset loader, letterbox căn giữa, `mapping_sha256` đổi khi đổi ngưỡng, các thành phần khác của khóa cache, thông báo hết VRAM, `mapping create --model`.

### Phase 0 — Group 3 (backend) — 2026-09-27
#### Thêm
- SQLAlchemy 2, Alembic, model ORM và migration `0001` cho 23 bảng; enum Postgres khớp contract.
- Role `advertest_owner`/`advertest_app` tạo bằng `docker/postgres/init/01-roles.sh`; migration cấp quyền (bảng chỉ-thêm chỉ có `SELECT`, `INSERT`; `runs` không có `DELETE`).
- Trigger chặn tự review; unique `(experiment_id, fingerprint)`; CHECK trạng thái bất thường phải có lý do.
- Script seed (`backend/admin_cli/seed.py`); `make test-db`.
#### Quyết định
- psycopg 3, argon2-cffi, Postgres 17; Alembic đọc `MIGRATION_DATABASE_URL`, ứng dụng đọc `DATABASE_URL`; mỗi migration tự `GRANT` (`tech-stack.md` mục 4, 4.1, 11; `requirements.md` Phase 0; `CLAUDE.md`).
#### Tồn đọng
- Phase 3: luật "chỉ worker ghi kết quả" phải chặn ở API (DB vẫn cho `advertest_app` sửa `runs`).
- Phase 4: chuyển email về chữ thường khi đăng ký.

### Phase 0 — Group 4 (backend) — 2026-09-27
#### Thêm
- App FastAPI: 16 nhóm endpoint công khai (mỗi nhóm một endpoint đại diện), 6 endpoint worker, `/health`; security scheme cookie `advertest_session` và bearer cho worker.
- Body lỗi thống nhất `ErrorResponse` cho `501`; `contracts/openapi.json` sinh bằng `make contracts`.
#### Contract
- Đề xuất 001 (đã duyệt): enum `ErrorCode` (`not_implemented`), `ErrorResponse`, `HealthResponse`.
#### Quyết định
- Khung API tối thiểu thay cho "request/response model đầy đủ"; `/health` luôn trả `200`, không lộ chi tiết lỗi nội bộ; boto3, httpx (dev); biến môi trường của API (`requirements.md` Phase 0, `tech-stack.md` mục 4, 4.1, 7, 11).
#### Tồn đọng
- Phase 3: `lease` trả `204` hoặc `WorkerJobBundle`. Phase 4: mô tả cookie (phiên phía server) và mọi lỗi dùng `ErrorResponse`.
- Starlette cảnh báo `httpx` với `TestClient` đã lỗi thời, khuyên dùng `httpx2`: chưa quyết.

### Phase 0 — Group 5 (frontend) — 2026-09-27
#### Thêm
- `frontend/src/contracts/api.ts` sinh từ `contracts/openapi.json`; mảng giá trị enum trong `schemas.ts`.
- Lớp gọi API (TanStack Query), chế độ mock `VITE_USE_MOCKS`; `StatusBadge` dùng chung cho 3 enum trạng thái; trang `/dev/contracts` chỉ có ở dev; `verify:build`; Vitest.
#### Quyết định
- Cấu hình `StatusBadge` ở một nơi; nguồn type của frontend; biến `VITE_*`; quy ước test Vitest (`tech-stack.md` mục 5.1, 7).
#### Tồn đọng
- Manual check: `/dev/contracts` ở viewport 375px không có thanh cuộn ngang.
- Phase 5: `useRun` dừng polling khi run kết thúc.

### Phase 0 — Group 6 (ml-core) — 2026-09-27/28
#### Thêm
- `ml_core/fixtures.py`, `scripts/fetch_fixtures.py` (`make fixtures`): tải, kiểm tra sha256, chỉ đặt file khi khớp.
- `tests/fixtures/checksums.json`: weights YOLOv8n, 5 ảnh và 5 label gốc KITTI; `tests/fixtures/LICENSE.md`.
- `tests/fixtures/manifest.json` (schema `DatasetManifest`): 5 ảnh, 59 annotation, 7 ignore region `dont_care`.
- Test nghiệm thu: smoke test YOLOv8n trên CPU, manifest đối chiếu với ảnh và label gốc, fixture phủ đủ trường hợp.
#### Contract
- Đề xuất 002 (đã duyệt): `DatasetManifest` và các model con; `schema_version = 1`.
#### Quyết định
- Nơi lưu fixture: GitHub Release `fixtures-v1` của repo (repo chuyển sang public); tên file đính kèm phẳng, mỗi mục khai `url` riêng.
- Nguồn KITTI: ảnh từ bản Ultralytics, label gốc từ KITTI (label YOLO mất `DontCare`, `truncated`, `occluded`) (`requirements.md` Phase 0, Phase 1).
- 5 ảnh `000902`, `002571`, `004499`, `004965`, `005866` chọn tự động theo độ phủ lớp và số object.
#### Số liệu đo được
- Smoke test YOLOv8n trên 5 ảnh letterbox 640×640, CPU: khoảng 1,5 giây.
- Trong 5 ảnh: 38/59 object dưới mức Moderate (sẽ thành ignore region khi áp mapping ở Phase 1).
- `dataset_version_sha256` của fixture: `9f5b413eb8a78a6a4b216011c2cf26e5b877728f7a160bbb80964a917d976069`.
#### Tồn đọng
- Tải 5 file `kitti_label_2_*.txt` lên release `fixtures-v1` (trước khi push, nếu không CI fail ở `make fixtures`).

### Phase 0 — Group 7 (backend) — 2026-09-27
#### Thêm
- `docker/compose.yaml`: `postgres`, `minio`, `minio-init` (tạo 4 bucket), `api`, `frontend`, có healthcheck; `docker/api/Dockerfile`; `.env.example`.
- `api` chạy migration bằng role owner rồi chạy uvicorn bằng role app; frontend gọi API qua proxy `/api` của Vite.
#### Quyết định
- MinIO bản Chainguard pin theo digest (image chính thức ngừng phát hành); uvicorn; image api python-slim + torch CPU ở Phase 0 (`tech-stack.md` mục 4, 6, 11).
#### Số liệu đo được
- `make up` lần đầu (gồm build image api): khoảng 3 phút 10 giây trên máy phát triển.
#### Tồn đọng
- Phase 3: user MinIO riêng thay cho root; image CUDA dùng chung với worker. Phase 11: pin image nền theo digest.

### Phase 0 — Group 8 (người duyệt) — 2026-09-27
#### Thêm
- `.github/workflows/ci.yml`: job `python`, `frontend`, `contracts`, `acceptance` (Postgres service container); cache uv, pnpm, fixture.
#### Quyết định
- Cấu trúc CI (`tech-stack.md` mục 6).
#### Sửa lỗi (2026-09-28)
- Lần chạy CI đầu tiên (run 36336331689): job `python`, `contracts`, `acceptance` fail ở "Set up job" vì `astral-sh/setup-uv` không có tag major `v10`; đổi sang `@v10.2.0`.
#### Tồn đọng
- Manual check: CI xanh trên GitHub sau khi push. Phase 11: pin action theo SHA.

### Phase 0 — Group 9 (người duyệt) — 2026-09-27
#### Thay đổi
- `CLAUDE.md`: thêm lệnh `make test-db`, `make contracts-check`, `verify:build`, `ENV_FILE`; quy tắc sửa `scripts/` và file gốc; quy ước `canonical_json`, tiền, `GRANT`.
#### Thêm
- `CHANGELOG.md` (file này).

### Phase 0 — Group 10 (người duyệt) — 2026-09-27
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_00/`: `test_contracts.py`, `test_database.py` (marker `db`), `test_api.py`, `test_fixtures.py`.
- `make test-db` dựng thêm MinIO (cùng digest với compose) để test `/health` với Postgres và MinIO thật; job `acceptance` của CI chạy MinIO bằng `docker run` và chạy test nghiệm thu `db`.
#### Thay đổi spec
- `tech-stack.md` mục 4.1: hash ghi rõ theo RFC 8785.
#### Thay đổi
- `make test-acceptance` chạy `make fixtures` trước và bỏ qua test `db` (test `db` chạy trong `make test-db`).
#### Quyết định
- Test manifest.json và smoke test YOLOv8n viết cùng phần còn lại của Group 6; test `/health` dùng MinIO thật (người dùng chốt, 2026-09-27).
#### Số liệu đo được
- Test nghiệm thu: 49 test không cần DB pass; 13 test `db` pass (cùng 28 test DB của backend: 41 pass).
- Thử lỗi giả: cấp thêm `UPDATE` cho bảng chỉ-thêm làm 10 test fail; MinIO sai cổng làm test `/health` fail.
- Rà `contracts/`: tên trường của 9 schema khớp bảng trong `requirements.md`; `FingerprintInputs` đủ 11 đầu vào.
#### Manual check đã chạy (trên máy phát triển, 2026-09-27)
- `make up`: 4 service healthy; MinIO có đủ 4 bucket; MinIO console và `/docs` trả `200`; OpenAPI có đủ các nhóm endpoint; `/dev/contracts` phục vụ được ở chế độ mock.
#### Tồn đọng
- Manual check người duyệt tự làm: `/dev/contracts` ở viewport 375px; CI xanh trên GitHub; đọc lại `contracts/` đối chiếu `mission.md` mục 4.
- Group 6: 5 ảnh KITTI, `manifest.json`, smoke test và hai test nghiệm thu tương ứng.
- Phase 0 chưa đánh dấu hoàn thành trong `roadmap.md` (còn mục fixture và CI).

### Phase 0 — kiểm tra Definition of Done (phase-close) — 2026-09-27
- `validation.md`: đánh dấu 30 mục Automated Tests có bằng chứng (`make check`, `make test-db`, `verify:build`, test nghiệm thu) và 2 mục DoD (`CLAUDE.md` đã dùng thật; `tech-stack.md` mục 11 đã ghi phiên bản pin).
- Manual check `make up`, MinIO 4 bucket, `/docs`: agent đã chạy ở Group 10; người dùng chấp nhận là đạt.
- **Phase 0 chưa đóng.** Còn thiếu: 3 test fixture (Group 6: ảnh KITTI, `manifest.json`, smoke test); manual check `/dev/contracts` (badge, viewport 375px), CI xanh trên GitHub, đọc lại `contracts/`; DoD "Automated Tests pass trên CI", "người duyệt chấp nhận `contracts/` và migration". Người dùng chọn để sau.

### Phase 0 — kiểm tra Definition of Done lần 2 (phase-close) — 2026-09-28
- Đánh dấu thêm: `make fixtures` tải đủ 11 file (job acceptance của CI và tải thử từ thư mục trống); người dùng xác nhận `/dev/contracts` hiển thị badge đúng và CI xanh cả 4 job (run 36336874119, commit `7471b62`), kéo theo DoD "Automated Tests pass trên CI".
- **Phase 0 vẫn chưa đóng.** Còn thiếu: `/dev/contracts` ở viewport 375px; đọc lại `contracts/` đối chiếu `mission.md` mục 4 và `tech-stack.md` mục 4.3, 4.4; người duyệt chấp nhận `contracts/` và migration `0001` (kéo theo DoD "Toàn bộ Manual Checks").

### Phase 0 — Tổng kết (phase-close) — 2026-09-28
- **Đóng phase.** Người dùng xác nhận 2 manual check cuối (`/dev/contracts` ở viewport 375px; đã đọc lại `contracts/`). `validation.md` đủ 44/44 mục; `roadmap.md` đánh dấu Phase 0 hoàn thành.
- **Giao được:** monorepo với uv và pnpm; contract Pydantic (16 enum + `ErrorCode`, 10 schema, sinh JSON Schema, OpenAPI, TypeScript); DB 23 bảng với phân quyền chống sửa kết quả và trigger chặn tự review; API khung FastAPI; frontend khung; Docker Compose (Postgres, MinIO, API, frontend); CI 4 job; fixture KITTI 5 ảnh kèm manifest; 52 test nghiệm thu (13 cần DB).
- **Contract:** đề xuất 001 (`ErrorResponse`, `HealthResponse`) và 002 (`DatasetManifest`) đã duyệt và áp dụng.
- **Số liệu cuối:** `make check` pass; `make test-db` 41 test pass; CI run 36336874119 xanh cả 4 job.
- **Lưu ý:** các group của người duyệt do agent soạn thay theo cho phép của người dùng; review do chính agent thực hiện nên không phải review độc lập.
- **Tồn đọng chuyển sang phase sau:** xem `roadmap.md` (mục "Từ Phase 0" ở Phase 3, 4, 5, 11); câu hỏi mở về đơn vị tiền tệ mặc định.

### Phase 0 — kiểm tra Definition of Done lần 3 (phase-close) — 2026-09-28
- Người duyệt chấp nhận `contracts/` và migration `0001`.
- **Phase 0 vẫn chưa đóng.** Còn thiếu: `/dev/contracts` ở viewport 375px; đọc lại `contracts/` đối chiếu `mission.md` mục 4 và `tech-stack.md` mục 4.3, 4.4 (kéo theo DoD "Toàn bộ Manual Checks").

### Replan sau Phase 0 (lần 2) — 2026-09-28
- Fixture sau mapping `kitti-coco` và lọc Moderate còn `car = 14`, `truck = 1`, `person = 6` ground truth; ghi vào `validation.md` Phase 1. AP từng lớp trên fixture nhiễu (đặc biệt `truck`), golden value chỉ nên so mAP tổng.

### Replan sau Phase 0 — 2026-09-27
- Phase 1: Group 2–5 phụ thuộc Phase 0 Group 6 (fixture KITTI); Group 1 thêm `typer`, `pillow` và entry point `advertest` vào `pyproject.toml`; contract Phase 1 dùng lại `Sha256Hex`, `GitCommit`, `LibVersions`, `UtcDatetime` (`plan.md`, `requirements.md` Phase 1).
- Phase 2: ID ghép và `experiment_id` tính bằng `content_id(sha256_of(...))`; seed Phase 0 đã khớp bảng catalog (`requirements.md`, `plan.md` Phase 2).
- Tồn đọng của Phase 0 đưa vào `roadmap.md` ở Phase 3, 4, 5, 11.
- Câu hỏi còn mở: đơn vị tiền tệ mặc định (VND hay USD).

### Số liệu chung của Phase 0 đến thời điểm này
- `make check`: 176 test Python (trừ test `db`), 49 test nghiệm thu và 36 test Vitest pass.
- `make test-db`: 41 test pass trên Postgres 17 và MinIO.
