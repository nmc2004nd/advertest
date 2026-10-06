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
