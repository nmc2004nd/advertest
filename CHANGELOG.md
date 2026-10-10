# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Lưu trữ

Các phase đã đóng trước phase gần nhất nằm trong `changelog/archive/` (không Read nguyên file; dùng `grep -n` rồi đọc theo khoảng dòng):

- [Phase 8 — Protocol, review và report](changelog/archive/phase-08.md)
- [Phase 7 — Tự tìm ngưỡng](changelog/archive/phase-07.md)
- [Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh](changelog/archive/phase-06.md)
- [Phase 5 — Wizard tạo experiment và theo dõi tiến độ](changelog/archive/phase-05.md)
- [Phase 4 — Xác thực và phân quyền](changelog/archive/phase-04.md)
- [Phase 3 — Worker và máy local](changelog/archive/phase-03.md)
- [Phase 2 — Attack white-box đầu tiên](changelog/archive/phase-02.md)
- [Phase 1 — Inference và metric](changelog/archive/phase-01.md)
- [Phase 0 — Contract và khung dự án](changelog/archive/phase-00.md)

---

## Phase R2 — Backend: insight, mở rộng qua cấu hình, thử nhanh

**Trạng thái:** ✅ Hoàn thành 2026-10-10 theo xác nhận của người dùng. Group 0–6 xong trên `phaser2-worker` @ `5eb2b08`. Phase R1 vẫn mở (còn Manual Checks và DoD); người dùng chọn đóng R2 trước. Trước khi merge vào `main` còn phải upload fixture `fixtures-v2` (xem Tồn đọng).

### Phase R2 — Tổng kết (phase-close) — 2026-10-10

- **Giao được:**
  - API insight (điểm yếu, ma trận 4 dải, câu kết luận theo quy tắc), template protocol, preset experiment, `POST /experiments/draft` và luồng Khám phá/Chính thức (`mode`, `promote`, `promoted_from`).
  - Attack spec trỏ tới adapter, có `params_schema`. Catalog sống trong DB với vòng đời `draft → checking → pending_approval → active/retired` và selfcheck 7 mục.
  - Adapter model torchvision (safetensors) và ONNX, `ModelProvider` LRU, `check_model`, upload model qua web.
  - Thử nhanh qua API, kèm purge nền.
  - `advertest-worker --tools` chạy `spec_check`, `model_check`, `quick_try`.
  - Xử lý tồn đọng R1: lỗi `ModelProvider.get` khi kiểm gradient chỉ làm run cần gradient `failed`.
- **Nghiệm thu local** @ `5eb2b08`: `make check` exit 0 (unit 1759, frontend 372, nghiệm thu 408); `make test-db` exit 0 (795 pass, gồm golden R1). Manual Checks đạt theo xác nhận của người dùng: demo qua API (worker `--tools` chạy ngoài Docker), thử nhanh trên laptop, đọc 3 câu kết luận trên KITTI.
- **Contract:** 2 permission mới (`attack_catalog.approve`, `quick_try.use`), 21 schema mới, seed `protocol_templates.json` và `experiment_presets.json`. `spec_sha256` của 10 spec seed không đổi.
- **Dependency:** `onnxruntime` 1.30.0, `safetensors` 0.8.0, `python-multipart` 0.0.32.
- **DB:** migration `0011` (`promoted_from`) và `0012` (status/metadata/check của spec, status/check của model, `tool_jobs`, `quick_tries`).
- **Số liệu:** thử nhanh trên i5-1340P, CPU, torch 12 luồng, YOLOv8n đã cache, ảnh KITTI 000902, preset standard, chỉ phần tính toán: FGSM [4, 8, 16, 24, 32] mất 1.35 / 1.17 / 1.17 s (trung vị 1.17 s); fog [1..5] mất 0.71 / 0.80 / 0.83 s (trung vị 0.80 s). Mục tiêu < 10 s đạt. Selfcheck PGD khoảng 46 s/spec trên 1 luồng. `check_model`: FCOS khoảng 7.5 s, ONNX 0.2 s; FCOS inference 0.7 s/ảnh CPU.
- **Quyết định:** ghi trong `requirements.md` ở các mục "Chốt ở Group 0/1/2/3/4/5". Open Question về số luồng torch chuyển sang backlog (người dùng chốt 2026-10-10).
- **Tồn đọng:**
  - **Trước khi merge:** upload `yolov8n.onnx` và `fcos_resnet50_fpn_coco.safetensors` lên release `fixtures-v2` (ngày 2026-10-10 hai URL vẫn trả 404), rồi chạy `make fixtures` trên một clone sạch.
  - Commit phần "Chốt ở Group 2/3/5" trong `requirements.md` (đang nằm trong working tree).
  - R3: service `advertest-worker --tools` trong `docker/compose.yaml` và fixture trong image worker; làm mờ rộng hơn cho thử nhanh; gộp phần dựng fixture giữa `spec_check.py` và `attacks/selfcheck.py`.
  - Backlog: `validate` chưa kiểm `art_class`; `check_model` mở ONNX từ file, còn `ModelProvider` mở từ bytes; `POST /models` đọc cả file vào RAM; các `assert` còn lại trong `backend/app/reviews/*`, `insight/service.py` và `tool_dispatch.py:91`; dọn object MinIO mồ côi; số luồng torch.
  - Phase R1 chưa đóng.

### Phase R2 — Group 5 (worker) — 2026-10-10
### Thêm
- `advertest-worker --tools [--once]`: `ToolRunner` (heartbeat 15 s, mất lease thì bỏ kết quả), client cho `tool_lease/bundle/heartbeat/result`, `cache.ensure_weights`.
- `quick_try.py`: letterbox, predict sạch, chạy mọi level, ghép object theo IoU ≥ 0.5 cùng class, làm mờ `rule_v1`.
- `spec_check.py`: chạy selfcheck trong tiến trình con, có cắt cứng.
### Thay đổi
- `pipeline.py`: phép kiểm gradient đưa vào `try`, lỗi đi qua `WORKER_POLICY` (tồn đọng R1).
- Backend `apply_check` (spec và model) ghi `worker_target_id = job.leased_by` (người dùng cho phép sửa ngoài phạm vi). Sửa review #6: thay `assert` bằng kiểm tra tường minh, trả `Conflict` (`5eb2b08`).
### Quyết định
- `requirements.md` "Chốt ở Group 5": `worker_target_id` do API ghi; nhãn và giới hạn làm mờ của thử nhanh; card worker công cụ; cắt cứng `spec_check`; worker `--tools` chưa có trong Docker.
### Số liệu đo được
- Thời gian thử nhanh, xem phần Tổng kết.
### Tồn đọng
- Service `--tools` trong compose, fixture trong image, gộp `fixture_inputs` (R3).

### Phase R2 — Group 4 (backend) — 2026-10-10
### Thêm
- Migration `0012`, có GRANT. Service `attack_catalog`, `model_uploads`, `quick_tries`, `tool_jobs`, `tool_dispatch`. Purge thử nhanh chạy nền mỗi 10 phút, kèm lệnh `advertest-admin purge-quick-tries`.
### Thay đổi
- Bỏ cột `attack_specs.is_active`; ORM giữ hybrid `is_active`. Insight đọc `level_label` từ metadata. Thiếu cấu hình MinIO thì trả 500 `internal_error` qua `get_storage` (sửa review #2).
### Quyết định
- `requirements.md` "Chốt ở Group 4": các cột thêm, `architecture` nằm trong payload job, job công cụ lease toàn cục chỉ cho target `local`, thử nhanh từ chối mọi model không có gradient gặp attack cần gradient, lỗi thiếu MinIO trả trước lỗi 422.
### Tồn đọng
- `POST /models` đọc cả file vào RAM (backlog: stream).

### Phase R2 — Group 3 (ml-model) — 2026-10-10
### Thêm
- `TorchvisionAdapter` (3 kiến trúc, safetensors strict, `TorchvisionDetector`) và `OnnxAdapter` (layout `yolo` hoặc `boxes_scores_labels`). Thêm `open_adapter`, `ModelProvider` LRU (`max_models=2`), `check_model`. Tách `yolo_postprocess` để dùng chung.
### Quyết định
- `requirements.md` "Chốt ở Group 3".
### Số liệu đo được
- `check_model`: FCOS khoảng 7.5 s, ONNX 0.2 s (CPU).
### Tồn đọng
- `check_model` mở ONNX từ file, `ModelProvider` mở từ bytes (backlog).

### Phase R2 — Group 2 (attack) — 2026-10-10
### Thêm
- Registry đọc `spec.adapter`, có `validate`/`adapters()`, `InvalidSpec`. Mỗi builder khai báo `params_schema`. Bộ kiểm JSON Schema tự viết. `attacks/selfcheck.py` (7 mục, CLI).
### Quyết định
- `requirements.md` "Chốt ở Group 2". Mục 5 với FGSM/PGD chỉ kiểm batch 1 hợp lệ, vì batch 1 lệch batch 4 trên YOLO CPU.
### Tồn đọng
- `validate` chưa kiểm `art_class` (backlog).

### Phase R2 — Group 1 (backend) — 2026-10-10
### Thêm
- `backend/app/insight/` (rules, phrases, service), `?mode=`, template, preset, draft, `promote`. Migration `0011` (`promoted_from`, audit `experiment.promoted`).
### Thay đổi
- Sửa theo review: insight tính run trúng cache; ô ma trận của level `early_stop` lấy mức sụt của run kích hoạt; kiểm `promoted_from` (422).
### Quyết định
- `requirements.md` "Chốt ở Group 1".

### Phase R2 — Group 0 (người duyệt, Claude làm theo ủy quyền) — 2026-10-09
### Contract
- Enum và model R2, 2 permission, 21 schema, mock, seed template/preset. Endpoint khung 501. Sửa mô tả `DraftNote.slice_too_small`.
### Thêm
- Fixture `yolov8n.onnx` và `fcos_resnet50_fpn_coco.safetensors` (sha256 trong `tests/fixtures/checksums.json`). Test nghiệm thu `tests/acceptance/phase_r2/`.
### Quyết định
- `requirements.md` "Chốt ở Group 0". Dependency ghi ở `tech-stack.md` mục 10–11.
### Tồn đọng
- Release `fixtures-v2` chưa upload.

---

## Phase R1 — Refactor lớp chạy giữ hành vi

**Trạng thái:** đang làm. Group 0 (golden, `6861ca8`), Group 1 đến Group 6 xong (Group 2 gồm cả bước 7b); Group 7 xong task 19; còn task 20 (đóng phase), chờ Manual Checks.

### Phase R1 — Group 7 task 19 (người duyệt) — 2026-10-09
Kiểm tra cuối trên `dev` @ `2cf490e` (sau khi merge `phaser1-worker` Group 6). Mỗi nhánh đã được review bằng `phase-review` trước khi đóng group tương ứng (xem các mục Group 1–6).
### Số liệu đo được
- `make check` @ `2cf490e`: exit 0; unit 1510 passed (1:54); nghiệm thu 344 passed (3:34), gồm Phase 0–8 và `phase_r1` (`test_architecture_r1` 5, `test_golden_cli` 1, `test_registry` 7).
- `make test-db` @ `2cf490e` (ghim P-core theo `test-db.sh`): exit 0, 699 passed (23:46).
- `make contracts` không tạo thay đổi; `git diff 6861ca8..2cf490e -- contracts/` rỗng.
### Tồn đọng
- Task 20 (đánh dấu R1 trong roadmap, tổng kết, replan R2) làm khi đóng phase.
- Manual Checks chưa làm: KITTI toàn catalog sau R1 so baseline bước 7b; thời gian chênh dưới 5%. Mục "ghi `job.py`" đã có số liệu ở mục Group 6, chờ người duyệt xác nhận.
- DoD "pass trên CI" chưa có bằng chứng (CI Phase 8 run 59/62 chưa xanh theo handoff kickoff).

### Phase R1 — Group 6 (worker) — 2026-10-09
Nhánh `phaser1-worker` @ `8cf49cd` (tách từ `phaser1-reviewer` @ `5dec5e1` = `dev` `5c1a5e4` + test G6), 6 commit: `5dec5e1` (test kiến trúc `job.py`, agent viết theo ủy quyền của người duyệt), `d3b9539`, `9bb0516`, `a368f0f`, `cd0e93c`, `8cf49cd`. Diff so với `dev`: 13 file, +1091/−801.
### Thêm
- `advertest_worker/pipeline.py`: `RunPipeline` (chạy một run); `finish.py`: `RunFinisher` (thay `_Finisher`); `state.py`: `JobState`, `DirectiveBox`; `search_hooks.py`: `JobSearchHooks`, `read_predictions_file`; `patch.py`: `patch_perturbation`; `early_stop.py`: `skip_early_stop`; `calibrate.py`: `calibrate_bundle`.
- Phần `job.py` của `tests/acceptance/phase_r1/test_architecture_r1.py` (`5dec5e1`); trước G6 1 test fail (`job.py:69 attacks.patch.geometry`), sau G6 5 passed.
### Thay đổi
- `job.py` 962 → 237 dòng. Trách nhiệm còn lại: `Heartbeat`; `JobRunner.__init__` (nối seam); `calibrate_bundle` (ủy quyền); `run_lease` (bundle, cache, heartbeat, `LeaseLost`); `_run_bundle` (`JobState`, dựng `FingerprintService`/`ManifestBuilder`, thứ tự run, directive, dừng sớm, tìm ngưỡng); `_search` (`SearchDriver`). `job.py` export lại `DirectiveBox`, `BatchHook`, `PerturbationFactory` qua `__all__` nên import cũ ở phase_03/05 và `backend/app/tests` vẫn chạy.
- Review so từng hàm: chỉ chuyển code, không đổi logic (`job.apply(directive)` và `JobState.stop_requested()` tương đương code cũ).
- Unit test worker `test_patch_job`, `test_early_stop`, `test_search_job` đổi theo tên mới; review xác nhận không bị làm yếu, `test_patch_job` thêm kiểm "không nạp model trước khi đối chiếu khóa".
- `docker/postgres/test-db.sh` (`8cf49cd`): trên CPU lai (có `/sys/devices/cpu_core/cpus`) chạy test qua `taskset -c <P-core>` và đặt `OMP_NUM_THREADS` = số lõi vật lý nếu chưa đặt; `ADVERTEST_TEST_NO_PIN=1` để tắt; áp dụng cả `make test-e2e`. Agent worker sửa `docker/` theo ủy quyền của người duyệt (review phát hiện 8).
### Contract
- Không đổi.
### Quyết định
- Dừng sớm và tìm ngưỡng chỉ có ở worker; CLI chỉ dùng chung `ml_core/runner/grid.py` (thêm dừng sớm cho CLI sẽ đổi hành vi). Review phát hiện 4; ghi tại `requirements.md` `## Decisions`.
- Test kiến trúc `5dec5e1` do agent viết theo ủy quyền của người duyệt, không độc lập; người duyệt đã đọc và chấp nhận nội dung (review phát hiện 1, 2026-10-08).
- Golden worker lệch 36↔37 (`grid:pgd_linf@4.0` `new_false_positives`, `search … #subset/1` 32↔30, checkpoint `000902` 36↔37) do oneDNN chọn cách chia khối theo loại lõi (P/E) chạy phép tính torch đầu tiên của process trên i5-1340P, không do refactor. Người duyệt chọn ghim test-db vào P-core (2026-10-08); golden R1 tái lập trên nhánh oneDNN P-core. Ghi tại `requirements.md` `## Decisions`.
- 3 lần `make test-db` pass @ `8cf49cd` (có ghim) được coi là đạt điều kiện "≥2 lần pass" của quyết định #6 (người duyệt chốt 2026-10-09).
### Số liệu đo được
- `make check TORCH=cpu` @ `8cf49cd`: exit 0, nghiệm thu 344 passed.
- `make test-db TORCH=cpu` @ `cd0e93c` (chưa ghim): agent 699 passed (26:45); reviewer lần 1 699 passed (24:40), lần 2 2 failed (24:42).
- `make test-db TORCH=cpu` @ `8cf49cd` (ghim P-core 0–7, `OMP_NUM_THREADS=12`): 699 passed ba lần (23:01, 23:09 agent; 23:28 reviewer).
- Probe PGD L∞ eps 4, ảnh `000902`, seed 0, 1 luồng: `taskset cpu0` 60 FP, `cpu8` 78 FP, ổn định qua nhiều process. Tắt `torch.backends.mkldnn` cho kết quả giống nhau trên hai loại lõi nhưng PGD chậm ~20% (3.9 s so với 3.2 s) và khác golden hiện tại.
- Ghim P-core mà không đặt số luồng (torch 8 luồng): phase_08 `test_max_drop_uses_trigger_run_for_early_stop` fail ổn định; với `OMP_NUM_THREADS=12` pass trên cả P và E.
### Tồn đọng
- `test-db.sh:57`: không kiểm `lscpu`; thiếu `lscpu` thì `OMP_NUM_THREADS=0` (review phát hiện 10, để sau). Số luồng 12 trên 8 CPU logic gây oversubscription nhẹ (có chủ đích).
- Worker production trên CPU lai vẫn cho failure case PGD khác nhau theo loại lõi; loại lõi và số luồng không có trong fingerprint hay `Environment` (phát hiện 9). Test dừng sớm Phase 8 phụ thuộc 12 luồng (phát hiện 11). Đã mở rộng Open Question số luồng torch trong `requirements.md`.
- Phương án dự phòng chưa dùng: tắt oneDNN trong `pinned_threads` (không phụ thuộc loại lõi, chậm ~20%, phải ghi lại golden).
- `run.py` còn alias `run_prefix`, `result_key` cho `ml_core/cli/run.py`; `attacks/factory.py` chưa xóa.
- `JobRunner` vẫn giữ thứ tự run, `_search` và việc dựng `FingerprintService`/`ManifestBuilder` (task 18 nói "chỉ còn lease, heartbeat, directive, API"); review chấp nhận vì test kiến trúc đạt.
- Manual Checks R1 (KITTI toàn catalog so baseline bước 7b, thời gian chênh dưới 5%) chưa làm; mục "ghi `job.py` vào CHANGELOG" có số liệu ở trên, chờ người duyệt xác nhận ở Group 7.

### Phase R1 — Group 5 (worker) — 2026-10-07
Nhánh `phaser1-worker` @ `a20936e` (tách từ `phaser1-reviewer` @ `86d71dc`), 5 commit: `86d71dc` (test nghiệm thu trước G5, agent viết theo ủy quyền của người duyệt), `65b5953`, `ec79b6a`, `702f8dc`, `a20936e`; code chỉ sửa `ml_core/runner/` và `backend/worker/`. Diff so với `dev`: 21 file, +1090/−388.
### Thêm
- `FingerprintService` (thay `job._inputs`, `run._fingerprint_inputs`) và `ManifestBuilder` (thay `_Finisher._manifest`, `run._write_manifest`) dùng chung CLI và worker.
- `ml_core/runner/errors.py`: `ErrorPolicy`, `CORE_POLICY`; `advertest_worker/errors.py`: `WORKER_POLICY = CORE_POLICY.with_rules(...)` (`LeaseLost`, `StopExperiment`, `PatchInterrupted`). `_run_one` của CLI và worker dùng chung.
- `ml_core/runner/paths.py`: gom đường dẫn artifact (`runs/`, `cases/`, `candidates/`); layout không đổi.
- Seam mới `registry` (`PerturbationRegistry`) và `model_provider` (`ModelSource.get(card, params, device)`) cho `Runner`, `run_config`, `JobRunner`.
- Test nghiệm thu `tests/acceptance/phase_r1/test_architecture_r1.py` (phần runner/worker; phần `job.py` để G6) và `test_registry.py` (builder giả qua runner CLI, white-box với `ModelProvider` giả).
### Thay đổi
- Runner CLI, worker và `calibrate.py` dựng perturbation qua registry (patch qua `BuildContext.patch`), nạp model qua `ModelProvider`; bỏ `isinstance` trong `executor.linf_eps` và rẽ nhánh `kind` trong `images.perturbation_kind`.
- Mặc định seam đổi thành `EnvProvenance()` và `predict_slice`.
- `job.py` 983 → 962 dòng; `run.py` 430 → 384 dòng.
- Unit test worker (`test_run`, `test_executor`, `test_calibrate`, `test_patch_job`, `test_search_job`) chuyển từ patch tên module sang seam; review xác nhận không test nào bị làm yếu.
- Hành vi khác có chủ đích: `IncompatibleAttack` ném ra giữa lúc chạy batch cho `skipped` thay vì `failed`; `ModelProvider` cache theo `(sha, params, device)` nên worker không dùng lại estimator giữa các bundle khác `InferenceParams`.
### Contract
- Không đổi.
### Quyết định
- `registry` là seam chính (nguồn `linf_eps`/`image_kind`); `perturbation_factory(spec, estimator | None)` giữ chữ ký, phải nhất quán với `registry`. Người duyệt chốt 2026-10-07 (review phát hiện 2); ghi tại `requirements.md` `### Seam` và `## Decisions`.
- `ErrorPolicy` hai tầng `CORE_POLICY`/`WORKER_POLICY`; hết VRAM ở batch 1 hoặc ngoài vòng batch → `failed`; `IncompatibleAttack` lúc chạy → `skipped`. Ghi tại `requirements.md` `### Chính sách lỗi`.
- Khóa cache `ModelProvider` `(weights_sha256, InferenceParams, device)`, cache không giới hạn. Ghi tại `requirements.md` `### Model`.
- Lỗi `ModelProvider.get` trong phép kiểm gradient của worker để R2 sửa. Người duyệt chốt 2026-10-07 (review phát hiện 3); ghi tại `requirements.md` `## Decisions` và `roadmap.md` Phase R2.
- Người duyệt xác nhận đã ủy quyền cho agent viết test nghiệm thu ở `86d71dc` (review phát hiện 1).
### Số liệu đo được
- `make check TORCH=cpu` tại `a20936e`: exit 0, nghiệm thu 343 passed.
- `make test-db TORCH=cpu` tại `a20936e`: 699 passed (lần chạy của reviewer 25 phút); gồm golden worker, checkpoint, chính sách lỗi.
- Test R1 mới: trước G5 có 3 test fail (2 kiến trúc, 1 `ModelProvider` giả), sau G5 0 fail.
### Tồn đọng
- Chưa xóa `attacks/factory.py` (Decisions giữ tên tới hết R1; thư mục của agent attack).
- `run.py` còn alias `run_prefix`, `result_key` cho `ml_core/cli/run.py` (ngoài phạm vi); dọn ở G6/G7.
- `job.py` còn import `attacks.patch.geometry`; mục kiến trúc `job.py` để G6.
- R2: đưa `ModelProvider.get` trong phép kiểm gradient (`job.py:491`, `job.py:246`) vào `try` để lỗi chỉ làm run `failed`; xét giới hạn cache `ModelProvider`.
- `ErrorPolicy.decide` trả `failed` cho cả `BaseException` không khớp luật (vô hại vì nơi gọi chỉ bắt `Exception`); có thể cho fallback ném tiếp.
- Chạy riêng một phần test DB thì phải đặt `backend/worker` trước `tests/acceptance` (fixture nghiệm thu xóa `attack_specs`).
- Manual Checks R1 (KITTI toàn catalog so baseline bước 7b, thời gian chênh dưới 5%) chưa làm.

### Phase R1 — Group 2 bước 7b (người duyệt) — 2026-10-07
Baseline KITTI toàn catalog trước refactor, làm mốc cho Manual Checks của `validation.md` (metric lệch trong sai số, thời gian chênh dưới 5%).
### Cách chạy (lần đo sau R1 phải giữ nguyên)
- Code: git worktree tại `6861ca8`; worker chạy trên máy (`advertest-worker run --once`, `--extra cpu`, `WORKER_DEVICE=cpu`, `GIT_COMMIT` = `6861ca8…`), cache worker trống riêng (`CACHE_DIR`); stack compose riêng (`-p advertest-r1base`, volume mới), DB mới seed.
- Dữ liệu: KITTI training đầy đủ (dataset `cfd54b7f…`); slice đánh giá 50 ảnh seed 42 (`536c007e-e845-5bf1-802a-ac1594c354d2`); slice huấn luyện patch 50 ảnh seed 43, `--exclude-slice` slice đánh giá (`e0387847-2f82-53fb-8f96-077b8e592133`); model YOLOv8n `81686f0e…`, mapping kitti-coco `820ed6c7…`.
- Config: preset "Toàn bộ catalog" của wizard (43 run): `fgsm`, `pgd_linf` eps 4, 8, 16, 32; `pgd_l2` 2, 4, 8, 16; 5 corruption × severity 1–5; `bbox_occlusion` 0.225, 0.45, 0.675, 0.9; `adv_patch` 0.1, 0.25; seed 0, `early_stop` bật, `--time-limit 86400`. File ở `data/r1-baseline/catalog50.yaml` (không commit); kết quả từng run ở `data/r1-baseline/runs.json`.
### Số liệu đo được
- Experiment `705c482b-1e14-47eb-ae40-6b763bd573cf`: `completed`; 37 run `completed`, 6 run `skipped` (`early_stop`: `pgd_linf` sụp ở eps 4, `pgd_l2` sụp ở 2); `git_dirty = false`.
- Thời gian: tổng thời gian xử lý batch 5131,1 s; wall clock của worker 1:36:02 (gồm calibration lần đầu khoảng 1,3–1,4 s/ảnh); RSS tối đa 5,2 GB. Train và đánh giá `adv_patch` chiếm 4880 s (95%).
- mAP sạch (mọi run): mAP50 0,4698, mAP50-95 0,2865.
- mAP50 / mAP50-95 sau tấn công (thời gian xử lý của run), theo level:
  - `fgsm`: 4: 0.1408 / 0.0424 (9.4 s); 8: 0.1252 / 0.0404 (9.4 s); 16: 0.0827 / 0.0318 (8.8 s); 32: 0.0296 / 0.0112 (9.4 s)
  - `pgd_linf`: 4: 0.0033 / 0.0008 (59.9 s); 8: early_stop; 16: early_stop; 32: early_stop
  - `pgd_l2`: 2: 0.0123 / 0.0036 (65.5 s); 4: early_stop; 8: early_stop; 16: early_stop
  - `fog`: 1: 0.4594 / 0.2620 (3.0 s); 2: 0.4452 / 0.2541 (3.1 s); 3: 0.4330 / 0.2379 (3.1 s); 4: 0.4320 / 0.2391 (3.0 s); 5: 0.4147 / 0.2259 (3.0 s)
  - `snow`: 1: 0.4164 / 0.2176 (3.3 s); 2: 0.2564 / 0.1437 (3.2 s); 3: 0.2756 / 0.1419 (3.2 s); 4: 0.2270 / 0.1034 (3.2 s); 5: 0.2110 / 0.1106 (3.1 s)
  - `frost`: 1: 0.4264 / 0.2425 (2.3 s); 2: 0.4069 / 0.2078 (2.3 s); 3: 0.3210 / 0.1641 (2.3 s); 4: 0.2974 / 0.1499 (2.4 s); 5: 0.2577 / 0.1279 (2.3 s)
  - `motion_blur`: 1: 0.4507 / 0.2151 (4.8 s); 2: 0.3623 / 0.1501 (5.4 s); 3: 0.2075 / 0.0831 (4.3 s); 4: 0.1183 / 0.0478 (4.5 s); 5: 0.0928 / 0.0330 (4.7 s)
  - `contrast`: 1: 0.4632 / 0.2656 (2.3 s); 2: 0.4427 / 0.2522 (2.3 s); 3: 0.4031 / 0.2186 (2.3 s); 4: 0.3153 / 0.1632 (2.4 s); 5: 0.1332 / 0.0725 (2.4 s)
  - `bbox_occlusion`: 0.225: 0.3220 / 0.1750 (2.5 s); 0.45: 0.0984 / 0.0540 (2.5 s); 0.675: 0.0303 / 0.0150 (2.5 s); 0.9: 0.0113 / 0.0051 (2.5 s)
  - `adv_patch`: 0.1: 0.0722 / 0.0466 (2486.4 s); 0.25: 0.0497 / 0.0344 (2394.0 s)

### Phase R1 — Group 4 (ml-model) — 2026-10-07
Nhánh `phaser1-ml-model` @ `6ddf3df` (tách từ `dev` @ `6e97bc2`), 2 commit (`ec24bb8`, `6ddf3df`); code chỉ sửa `ml_core/models/`.
### Thêm
- `ml_core/models/adapter.py`: `Capabilities(gradients)`, `NoGradients(RuntimeError)`, `ModelAdapter` (Protocol: `card`, `capabilities`, `class_names()`, `predict(images, batch_size=None)`, `estimator()`), `UltralyticsAdapter` (nạp lười, chỉ dựng `build_estimator(load(card), params, device)` ở lần gọi `predict`/`estimator` đầu tiên; `class_names()` lấy từ card), `ModelProvider(store, *, load_model=None)` cache theo `(weights_sha256, InferenceParams, device)`, `store_loader(store)` đọc `models/<sha>/weights.pt`.
- `ml_core/models/tests/test_adapter.py` (5 test): cache trả cùng instance theo khóa, nạp lười một lần, `NoGradients`, `predict` khớp estimator, framework khác ultralytics → `ValueError`.
### Thay đổi
- Không (chưa nơi nào ngoài `ml_core/models/` dùng adapter; tích hợp ở Group 5).
### Contract
- Không đổi.
### Quyết định
- `ModelProvider.get` báo `ValueError` khi `ModelCard.framework` khác `ultralytics`, cho tới khi R2 thêm adapter. Người duyệt chấp nhận 2026-10-07 (review phát hiện #3); ghi tại `requirements.md` `## Decisions`.
- `ModelAdapter.predict(images, batch_size: int | None = None)`, mặc định cả lô trong một batch (khác chữ ký gợi ý trong `requirements.md`, spec cho phép). Ghi tại `requirements.md` `## Data / Fields`.
- `store_loader` chép logic của `ml_core/cli/evaluate.py::load_model_from_store` để `ml_core/models` không import ngược `ml_core.cli`; trùng code tạm thời.
### Số liệu đo được
- `make check` tại `6ddf3df`: exit 0 (mypy 307 file; nghiệm thu không db 337 passed).
- `make test-db` tại `6ddf3df`: lần chạy của agent 697 passed, 2 failed (`phase_r1/test_golden_worker.py`, `phase_r1/test_checkpoint_compat.py`: failure case PGD lệch `new_false_positives` 37≠36, 32≠30); chạy riêng 2 file pass trên cả nhánh lẫn `dev`. Lần chạy của reviewer: 699 passed, 0 failed, 24m49s.
### Tồn đọng
- Golden worker có thể không ổn định khi chạy cả suite `make test-db` (1/2 lần lệch ở trên). Nếu lặp lại ở Group 5, xử lý theo Open Question về số luồng torch trước khi đi tiếp.
- Cho Group 5: thay `Runner.estimator`/`JobRunner._estimator` bằng `provider.get(card, params, device)`; không gọi `estimator()` cho corruption/occlusion (model không gradient báo `NoGradients`, validation "corruption trên cùng model → completed" sẽ fail); truyền đúng batch size hiện tại cho `predict`; xác nhận khóa cache `(sha, params, device)` không đổi kết quả golden (worker hiện cache theo sha).
- Cho Group 5/6: cho `load_model_from_store` dùng lại `store_loader` hoặc bỏ.
- Adapter giữ `card` của lần gọi đầu cho mỗi khóa; hai card cùng sha khác `supports_gradients` sẽ nhận capabilities cũ. Chấp nhận vì card định danh theo sha.

### Phase R1 — Group 3 (attack) — 2026-10-07
Nhánh `phaser1-attack` @ `1107b4b` (tách từ `phaser1-reviewer` @ `da010c9`), 3 commit của agent (`f3738a0`, `10bc702`, `fe5a9b7`) và 1 commit spec của người duyệt (`1107b4b`); code chỉ sửa `attacks/`. Nhánh mang theo `4912d86`, `da010c9` (phần registry thuần của `test_registry.py`, plan bước 7).
### Thêm
- `attacks/builders.py`: `PerturbationBuilder`, `BuildContext`, `PerturbationRegistry` (có resolver), `effective_adapter`, 4 builder mặc định (`art.evasion`, `corruption.imagecorruptions`, `occlusion.bbox`, `patch.robust_dpatch`) kèm `linf_eps` và `image_kind`, `DEFAULT_REGISTRY`; export lại `UnsupportedAttack`, `IncompatibleAttack`.
- `attacks/art_adapter.py::level_to_eps` (tách ra, giữ nguyên công thức).
- `attacks/tests/test_builders.py` (18 test): builder giả, trùng tên, thiếu estimator, `linf_eps`, `image_kind`, cả 10 spec catalog.
### Thay đổi
- `attacks/factory.py::build_perturbation` chuyển tiếp qua `DEFAULT_REGISTRY`, trả `Perturbation`; bỏ `AnyPerturbation`. Giữ tên và chữ ký đến Group 5.
- Kiểu lỗi của `build_perturbation` (người duyệt chấp nhận 2026-10-07): spec white-box với estimator `None` báo `IncompatibleAttack("{name} cần gradient nhưng model không hỗ trợ gradient")` thay cho `UnsupportedAttack`; `adv_patch` không có patch đã train báo `ValueError("... patch đã train")` thay cho `UnsupportedAttack` (patch chỉ truyền qua `BuildContext`). Runner không tới hai đường này (CLI kiểm `supports_gradients` trước và chặn `requires_training`; worker đi `_patch_perturbation`), golden không đổi. Sửa 2 unit test trong `attacks/tests/test_factory.py` theo đó.
### Contract
- Không đổi (`make contracts-check` pass).
### Quyết định
- Đăng ký trùng tên adapter báo `ValueError`, registry giữ builder đăng ký trước. Người duyệt chốt 2026-10-07; ghi tại `requirements.md` `### Registry` (`1107b4b`).
- `effective_adapter`: `kind=attack` với `art_class == "RobustDPatch"` → `patch.robust_dpatch`, `art_class` khác → `art.evasion` (art_class lạ vẫn ra thông điệp cũ của `ArtPerturbation`). Khác `perturbation_kind` cũ (dựa `requires_training`) nhưng cho cùng kết quả trên catalog hiện có.
### Số liệu đo được
- `make check` tại `fe5a9b7`: pass (1499 Python + 372 frontend; nghiệm thu không db 337 passed, gồm `phase_r1/test_registry.py` 5 passed).
- `make test-db` tại `fe5a9b7`: 699 passed, exit 0, 24m48s (người duyệt chạy lại 2026-10-07).
### Tồn đọng
- Cho Group 5: `PatchBuilder.requires={"gradients"}` nên khi dựng patch phải truyền estimator khác `None`; dựng patch qua `DEFAULT_REGISTRY.build(spec, BuildContext(estimator, patch=..., area_ratio=run.level))`, calibration dùng `area_ratio = primary_param.max`; thay `executor.linf_eps`/`images.perturbation_kind` bằng `builder.linf_eps(spec, level)`/`builder.image_kind`.
- Cho Group 5: `executor.linf_eps` hiện chỉ trả eps với `ArtPerturbation`, nên các test phase_07/08/r1 bọc perturbation qua seam đang có eps `None`; sau khi chuyển sang `builder.linf_eps`, ảnh nhiễu khuếch đại của failure case trong các test đó sẽ có eps. Golden mặc định không ảnh hưởng; review Group 5 kiểm lại.
- R2 có thể xem lại `PatchBuilder.requires` (đánh giá patch đã train không dùng estimator).
- Validation `### Registry` còn 2 mục tích hợp qua runner (builder giả qua `perturbation_factory`, `ModelProvider` giả) và mục kiến trúc `AnyPerturbation` (đã không còn theo grep, chờ `test_architecture_r1.py`): test viết trước Group 5.

### Phase R1 — Group 2 (người duyệt, Claude làm theo ủy quyền) — 2026-10-07
Nhánh `phaser1-reviewer` @ `b2034e7` (tách từ `dev` @ `e192dbd`), 2 commit; chỉ sửa `tests/acceptance/` và `tests/fixtures/golden/`. Claude viết test và review thay người duyệt theo ủy quyền của người dùng (2026-10-07); review không độc lập với con người. Người dùng chấp nhận các test này là test nghiệm thu của người duyệt.
### Thêm
- `phase_r1/test_checkpoint_compat.py` và fixture `tests/fixtures/golden/phase_r1_checkpoint.json` (ghi bằng worktree tạm tại `6861ca8`, `ADVERTEST_RECORD_GOLDEN=1`; run PGD dừng ở batch 0, ảnh 000902, fingerprint `4d82f99c…`).
- `phase_r1/test_error_policy.py`: builder lỗi ở run thứ hai qua seam `perturbation_factory`; provenance giả `dirty = true` → `git_dirty` trong manifest.
### Thay đổi
- `phase_05/conftest.py`: `Api` có `perturbation_factory`, `provenance` (mặc định `None`), truyền vào `JobRunner`; phase 6–8 dùng lại.
- phase_06/07/08: spy/flaky gán `api.perturbation_factory` (bọc `api.perturbation_factory or attacks.factory.build_perturbation`, giữ thứ tự chồng spy); `dirty_tree` dùng `api.provenance`. Bỏ patch `run_module.git_state` ở phase_08 vì manifest worker lấy git từ `fingerprint_inputs` (patch đó vốn không tác dụng; assertion giữ nguyên).
- phase_02: `run_config(..., clean_predictor=no_predict)`.
- Không còn `setattr(job_module|run_module, ...)` trong `tests/acceptance`; không đổi assertion, không nới sai số.
### Contract
- Không đổi.
### Quyết định
- Nhánh R1 merge vào `dev`, không vào `main` (`main` chưa có `dev`). Người dùng chốt 2026-10-07; ghi tại `requirements.md` `## Decisions`.
- `attacks.factory.build_perturbation` giữ nguyên tên đến hết R1 (test nghiệm thu phase_06/07/08/r1 import tên này làm mặc định của seam). Người dùng chốt 2026-10-07; ghi tại `requirements.md` `## Decisions`.
- Giới hạn của test checkpoint: chỉ JSON checkpoint do code trước R1 ghi; artifact ứng viên batch 0 do code hiện tại ghi (R1 không đổi layout artifact). Ghi tại `validation.md` `### Checkpoint`.
### Số liệu đo được
- `make check` tại `b2034e7`: pass (1481 Python + 372 frontend; nghiệm thu không db 332 passed).
- `make test-db` đầy đủ: 699 passed, 25 phút (theo báo cáo review).
- Thử đột biến test checkpoint: đổi version trong fixture thành 99 → test fail đúng.
### Tồn đọng
- ~~Bước 7b~~: đã chạy, xem mục "Group 2 bước 7b".
- Phần registry thuần của `test_registry.py` (catalog → adapter, trùng tên): phải có trước khi giao Group 3.
- `test_architecture_r1.py` (AST, gồm "không còn test patch cấp module"): trước Group 5.
- Sau Group 2, agent đổi mặc định seam thành `EnvProvenance()`, `build_perturbation`, `predict_slice` (`requirements.md` `### Seam`).
- Còn patch cấp lớp/module ngoài phạm vi 7 chỗ: `UltralyticsDetector.forward`, `SearchDriver._bootstrap` (phase_07/conftest.py:214-215), `env_module.REPO_ROOT` (phase_02). `ModelAdapter` ở Group 5 có thể đi vòng qua `forward` và làm sai số đếm lần gọi model ở phase_07; theo dõi khi review Group 5.
- Lỗi có từ trước: chạy test db của phase_r1 trước phase_06 trong cùng phiên thì phase_06 lỗi FK khi setup; thứ tự mặc định pass.

### Phase R1 — Group 1 (worker) — 2026-10-07
Nhánh `phaser1-worker` @ `d032885` (tách từ `dev` @ `e1840c5`), 5 commit; chỉ sửa `ml_core/runner/` và `backend/worker/`.
### Thêm
- `ml_core/runner/provenance.py`: `Provenance` (Protocol: `git`, `lib_versions`, `docker_image_digest`) và cài đặt mặc định `EnvProvenance` đọc env và git.
- Seam `provenance`, `clean_predictor` (alias `CleanPredictor`) cho `Runner` và `run_config`.
- Seam `perturbation_factory`, `provenance` cho `JobRunner`; hai chỗ dựng perturbation (calibration, run) đi qua `_build_perturbation`; provenance vẫn đọc một lần mỗi experiment.
- Unit test: provenance qua env; seam provenance và clean_predictor ở CLI; seam factory và provenance ở worker (`db`: build lỗi ở run 2 → `failed`, run 1 `completed`; `git_dirty` vào manifest; provenance đọc một lần).
### Thay đổi
- Không đổi hành vi; giữ nguyên các tên module cũ (7 chỗ patch trong `tests/acceptance` vẫn chạy).
### Contract
- Không đổi.
### Quyết định
- Seam mặc định `None` (tra tên cấp module lúc gọi: `build_perturbation`, `git_state`, `lib_versions`, `docker_image_digest`, `predict_slice`) cho tới hết Group 2; sau đó đổi mặc định thành `EnvProvenance()`, `build_perturbation`, `predict_slice`. Người duyệt chấp nhận 2026-10-07; ghi tại `requirements.md` `### Seam`.
- `PerturbationFactory` tạm khai báo ở cả `ml_core/runner/run.py` và `backend/worker/advertest_worker/job.py` để worker không import module CLI; Group 5 gom về lõi dùng chung (`requirements.md` `### Seam`).
- Plan ghi 3 chỗ dựng perturbation, thực tế 2 (search đi qua đường run).
### Số liệu đo được
- Unit: 1481 Python + 372 frontend pass; nghiệm thu không db 332 passed; `make test-db` 696 passed (24 phút, theo báo cáo agent).
### Tồn đọng
- `make check` đỏ ở `ruff format --check` của `scripts/export_demo_data.py:17` (có sẵn trên `dev` từ `660e631`); người duyệt format trên `dev` trong commit riêng.
- Group 2: fixture `JobRunner` trong conftest `phase_03`/`phase_05` cần truyền seam; chuyển 7 chỗ patch cấp module sang seam.
- Lỗ hổng độ phủ từ kickoff (người duyệt tự quyết): chưa có test cho `LeaseLost`, `PatchInterrupted`, thông điệp `UnsupportedAttack`, calibration qua registry.
