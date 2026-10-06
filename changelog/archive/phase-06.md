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
