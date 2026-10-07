# Changelog

Ghi theo group và phase. Mỗi mục ghi điều đã thêm, đã đổi, thay đổi contract, quyết định (kèm file spec đã ghi nhận), số liệu đo được và việc tồn đọng.

---

## Lưu trữ

Các phase đã đóng trước phase gần nhất nằm trong `changelog/archive/` (không Read nguyên file; dùng `grep -n` rồi đọc theo khoảng dòng):

- [Phase 7 — Tự tìm ngưỡng](changelog/archive/phase-07.md)
- [Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh](changelog/archive/phase-06.md)
- [Phase 5 — Wizard tạo experiment và theo dõi tiến độ](changelog/archive/phase-05.md)
- [Phase 4 — Xác thực và phân quyền](changelog/archive/phase-04.md)
- [Phase 3 — Worker và máy local](changelog/archive/phase-03.md)
- [Phase 2 — Attack white-box đầu tiên](changelog/archive/phase-02.md)
- [Phase 1 — Inference và metric](changelog/archive/phase-01.md)
- [Phase 0 — Contract và khung dự án](changelog/archive/phase-00.md)

---

## Phase R1 — Refactor lớp chạy giữ hành vi

**Trạng thái:** đang làm. Group 0 (golden, `6861ca8`), Group 1, Group 2 (cả bước 7b), Group 3, Group 4 và Group 5 xong.

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

---

## Phase 8 — Protocol, review và report

**Trạng thái:** ✅ Hoàn thành 2026-10-02 theo xác nhận của người dùng. Group 0–7 đã merge; Manual Checks đạt; mục Automated Tests pass trên CI được giữ chưa đánh dấu để test lại và cập nhật sau.

### Phase 8 — Tổng kết (phase-close) — 2026-10-02

- **Giao được:** protocol có version và kiểm tra tuân thủ; gửi duyệt và khóa experiment; tách quyền reviewer; verdict có version; tiêu chí và checklist; report PDF/JSON bất biến sau khi `ready`; trang xác minh công khai; audit toàn bộ vòng đời.
- **Nghiệm thu local:** `make check` pass; `make test-db` 694 test pass; `make test-e2e` 90/90 pass. Manual Checks và các thử nghiệm gian lận đã đạt theo xác nhận của người dùng.
- **Ngoại lệ khi đóng phase:** người dùng yêu cầu đóng Phase 8 nhưng giữ ô CI chưa đánh dấu. GitHub Actions run 59 tại commit đóng Phase 8 còn fail ở job DB/nghiệm thu; run 62 trên `main` còn fail `ruff format --check` tại `scripts/export_demo_data.py` (file thêm sau Phase 8). Cần chạy lại CI và ghi kết quả vào đây.
- **Replan:** các hệ quả cho Phase 9 đã có trong roadmap (định dạng giới hạn ngân sách; report ghi chi phí quyết toán so với ngân sách); Phase 10 đã có luật chặn gửi duyệt với case `hidden_unanonymized`. Hai phase này chưa có thư mục feature spec, nên giữ các yêu cầu chuyển tiếp trong roadmap cho tới kickoff.

### Phase 8 — Group 7 (người duyệt, người dùng giao) — 2026-10-02
#### Thêm
- **Test nghiệm thu `tests/acceptance/phase_08/` (task 34), 94 test, 9 file theo `validation.md`:**
  - protocol, tuân thủ, gửi duyệt và khóa, tách quyền, verdict, tiêu chí, quyết định, report, audit;
  - dữ liệu dựng qua API công khai và worker CPU thật (case được làm mờ thật);
  - tình huống khó tạo được giả lập ngay trong worker: dựng attack lỗi, thời gian xử lý vượt giới hạn, code chưa commit;
  - các trạng thái tìm ngưỡng hiếm (sát ngưỡng, khoảng tin cậy chứa level…) kiểm bằng hàm đánh giá với `SearchResult` của contract.
- **E2E `frontend/e2e/phase_08/` (task 34), 12 kịch bản (4 × 3 kích thước màn hình):**
  - trọn luồng qua giao diện: tạo protocol → wizard theo protocol → gửi duyệt → nhận review → verdict bằng phím tắt (desktop, tablet) hoặc vuốt và bottom sheet (điện thoại) → chấp nhận → report → tải PDF → `/verify` ra "Khớp", sửa 1 byte ra "Không khớp", chọn file không phát request nào mang nội dung file;
  - yêu cầu sửa rồi "Nhân bản để sửa";
  - engineer không thấy nút tải report;
  - người có cả hai role không thấy experiment của mình;
  - không cuộn ngang.
#### Sửa
- **`scripts/e2e.sh`:** tạo thêm bucket `reports` như `minio-init` của compose; trước đây report trong E2E không sinh được.
- **Task 37:**
  - test email Phase 5 lấy mốc từ `next_attempt_at` (giờ DB) nên không còn phụ thuộc ngày chạy;
  - số failure case mỗi run giữ 20.
#### Quyết định (người dùng chốt)
- **`DROP OWNED BY`:** giữ làm cách dựng DB test chính thức cho Phase 7, 8. Run Phase 6 vẫn chặn `downgrade base` của migration 0006, và migration không xóa dữ liệu thật khi downgrade. Đã ghi `validation.md` mục Chung, `roadmap.md`.
- **Thứ tự 403/422:** `403` đứng trước kiểm tra nghiệp vụ (thiếu `inconclusive_justification`). Body sai schema của contract là `422` của framework, kiểm trước mọi thứ: thiếu `conclusion`, `approve` thiếu `mitigation`/`model_verdict`, verdict `safety_relevant` thiếu `mitigation`. Đã ghi `validation.md` mục Nhận review và tách quyền.
- **Câu hỏi mở:** `cases_to_review_per_attack` giữ mặc định 5 (`requirements.md` Open Questions).
#### Thử gian lận (task 36): bằng test tự động gọi API thật bằng tài khoản engineer, mọi cách đều bị chặn
- **Gọi trực tiếp API ra quyết định, ghi verdict:** `403` (`test_review_separation.py::test_non_reviewer_cannot_decide`).
- **Tải report:** `403` (`test_report.py::test_only_report_export_downloads`).
- **Sửa experiment sau khi gửi duyệt:** hủy và gửi lại trả `409 experiment_locked`; sửa trường hay thêm run thẳng trong DB bị trigger chặn (`test_submit_lock.py::test_locked_after_submit`).
- **Gửi duyệt với run chạy từ code chưa commit:** `409` (`test_dirty_runs_blocked_when_protocol_forbids`).
- **Bỏ bớt attack bắt buộc hoặc giảm level:** `422 not_compliant` (`test_compliance.py`).
- **Chạy lại nhiều lần rồi chỉ gửi duyệt lần đẹp nhất:** report liệt kê mọi experiment cùng model và dataset, kể cả `completed` không gửi, `cancelled` và `dev-open` (`test_report.py::test_history_lists_related_experiments`).
- **Sửa file report rồi xác minh:** "Không khớp" (E2E trọn luồng).
#### Số liệu
- `make check` pass.
- `make test-db`: 694 test pass (23,5 phút).
- `make test-e2e`: 90/90 pass (8,1 phút).
#### Tồn đọng tại thời điểm Group 7
- **Manual check cần người thật** (sau đó đã làm và đạt theo xác nhận của người dùng khi phase-close):
  - luồng thật trên KITTI với hai tài khoản (máy dev không có GPU);
  - đọc toàn bộ PDF;
  - PDF và `/verify` trên điện thoại thật qua HTTPS;
  - đọc email gửi reviewer và engineer;
  - phím tắt và vuốt trên thiết bị thật;
  - lỗi `MAX_RUNS` của form protocol.
- **Tính độc lập:** test nghiệm thu và E2E do cùng agent đã viết code Group 1–6 viết; người dùng nên tự đọc lại hoặc chạy `phase-review` ở phiên khác.

### Phase 8 — Group 6 (frontend-report) — 2026-10-02
#### Thêm
- **`/reports` (task 32):** danh sách mới nhất trước; bảng trên desktop, thẻ trên điện thoại; tự cập nhật khi có report đang sinh.
- **`/reports/:id` (task 32):**
  - đủ 9 mục snapshot, dải "BẢN CHÍNH THỨC", mã report, hai hash, link xác minh;
  - nút "Tải PDF", "Tải JSON" và "Sinh lại" (khi `failed`) chỉ cho `report.export`.
- **`/verify/:id` (task 33):** trang công khai; SHA-256 tính bằng Web Crypto trong trình duyệt, file không gửi đi; "Khớp" hoặc "Không khớp" kèm hash vừa tính; báo cần HTTPS khi không có Web Crypto.
- **Điều hướng và liên kết:** mục "Report" (`report.read`); link "Report chính thức" trong tab Review.
- **Mock (`api/mocks.ts`):** `/reports`, `/reports/{id}`, `/reports/{id}/download`, `/verify/{id}`.
- **Test:** `reports/reports.test.tsx` (12): vector chuẩn SHA-256; hash file mẫu so với giá trị tính độc lập bằng Python; `fetch` bị chặn không được gọi.
#### Sửa test cũ
- `pages/app-pages.test.tsx`, `e2e/phase_04/onboarding.spec.ts`: thêm mục "Report" (engineer 6 mục; trên điện thoại "Thêm" có 3 mục).
#### Review (phase-review, 2026-10-02)
- Không có phát hiện chặn.
- **#1 (nên sửa, sửa trước khi merge):** trang report hiện mã tiếng Anh thô cho trạng thái tìm ngưỡng và phạm vi run. Sửa bằng `StatusBadge` và nhãn tiếng Việt; có test.
- **Ghi nhận:** giới hạn loại ngân sách hiện chuỗi số thô (Phase 9 định dạng tiền); mục validation "không gửi request chứa nội dung file" mới kiểm ở mức hàm, Group 7 kiểm thêm bằng E2E.
- Quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 6".
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Số liệu
- `make check` pass: 372 Vitest, 331 test nghiệm thu.
- `make test-e2e` 78/78 (6,8 phút, chạy trước phần sửa #1; phần sửa chỉ đổi nhãn trên trang report, E2E không đi qua trang này); `pnpm verify:build` pass.
#### Tồn đọng
- Kiểm tra tay: tải PDF thật rồi xác minh (Khớp, sửa 1 byte thì Không khớp); `/verify` trên điện thoại qua HTTPS; "Sinh lại" và tự cập nhật khi report đang sinh với backend thật.

### Phase 8 — Group 5 (frontend-review) — 2026-10-02
#### Thêm
- **`/reviews` (task 27):** ba nhóm (chờ nhận, tôi đang review, đã quyết định), sắp theo thời gian gửi hoặc mức sụt lớn nhất; bảng trên desktop, thẻ trên điện thoại, kèm tiến độ case.
- **`/reviews/:id` (task 28):**
  - nhận và trả lại; người tạo experiment không thấy nút nhận;
  - tuân thủ, kết quả tiêu chí (tham khảo), danh sách kiểm tra ✓/✗ kèm lý do;
  - case bắt buộc nhóm theo attack ("3/5 đã review"), run, biểu đồ và bình luận (dùng lại tab Kết quả và tab Review);
  - khung quyết định: "Chấp nhận" khóa kèm lý do, cả ba nút có hộp xác nhận.
- **`/reviews/:id/cases/:caseId` (task 29):**
  - `CaseViewer` kèm form verdict và lịch sử verdict;
  - phím tắt `J`/`K`, `1`–`4`, `S`/`A`/`N`, `Ctrl+Enter`, `?`;
  - điện thoại: vuốt chuyển case, form verdict trong bottom sheet với nút lớn.
- **`/protocols` (task 30):** danh sách gồm bản ngừng dùng; form tạo và tạo version mới (attack bắt buộc, tiêu chí, số case, `forbid_dirty_runs`) kiểm tra theo luật contract; ngừng dùng có xác nhận.
- **Trang chủ và điều hướng (task 31):** khối reviewer (số chờ nhận, danh sách đang review); bật mục "Duyệt" (`review.decide`), thêm mục "Protocol" (`protocol.read`).
- **Mock (`api/mocks.ts`):** `GET /reviews?status=`, `GET /failure-cases/{id}/verdicts`.
- **Test:** `reviews/reviews.test.tsx` (17), `protocols/protocols.test.tsx` (11).
#### Sửa
- **Lỗi Phase 4:** mở menu "Thêm" trên điện thoại làm sập trang (Slot của Radix gộp `className` dạng hàm thành chuỗi). Admin trên điện thoại đã dính lỗi từ Phase 4; Group 5 làm engineer và reviewer cũng có "Thêm". Sửa trong `layout/AppShell.tsx`, có unit test; E2E Phase 4 giờ mở "Thêm" thật.
#### Sửa test cũ
- `pages/app-pages.test.tsx`: khối reviewer trên trang chủ, danh sách mục điều hướng có "Duyệt" và "Protocol".
- `e2e/phase_04/onboarding.spec.ts`: engineer có 5 mục; trên điện thoại kiểm 3 tab và 2 mục trong "Thêm" (người dùng cho phép).
#### Review (phase-review, 2026-10-02)
- **#1 (chặn, đã sửa trước khi merge):** chuyển case bằng `J`/`K` hoặc vuốt giữ bản nháp verdict của case trước, có thể lưu nhầm vào case mới. Sửa: mỗi case một instance (`key`), khóa lưu tới khi tải xong verdict hiện hành; có test.
- **#2 (chấp nhận, ghi vào spec):** chưa có lối vào để review case ngoài danh sách bắt buộc.
- Quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 5".
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Số liệu
- `make check` pass: 360 Vitest, 331 test nghiệm thu.
- `make test-e2e` 78/78 (7,2 phút, chạy trước phần sửa #1; phần sửa chỉ đụng trang verdict, E2E không đi qua trang này); `pnpm verify:build` pass.
#### Tồn đọng
- Kiểm tra tay: phím tắt trên trình duyệt thật, vuốt và bottom sheet trên điện thoại thật, lỗi `MAX_RUNS` của form protocol, menu "Thêm" của admin.

### Phase 8 — Group 4 (frontend-report) — 2026-10-02
#### Thêm
- **Wizard (task 24):**
  - bước 1 hiện mục đích, slice tối thiểu, attack bắt buộc của protocol, cảnh báo khi catalog không còn đúng version;
  - bước 3 ẩn slice nhỏ hơn `min_slice_size`;
  - bước 4: attack bắt buộc tự thêm, có khóa "Theo protocol", không bỏ chọn và không đổi chế độ được; level bắt buộc là chip khóa; ngưỡng tìm kiếm bị khóa;
  - bảng tuân thủ ✓/✗ cập nhật trực tiếp trong tóm tắt.
- **Trang chi tiết (task 25, 26):**
  - nút và hộp gửi duyệt (điều kiện, giải trình từng run, ghi chú);
  - dải "Đã khóa" theo trạng thái;
  - tab Review (người nhận, giải trình, quyết định, bình luận);
  - "Nhân bản để sửa" khi `changes_requested`.
- **Mock (`api/mocks.ts`):** `GET /protocols/{id}`, bình luận; `/protocols` bỏ bản `retired` trừ khi `include_retired=true` (ghi nhận từ review Group 0).
- **Test:** `wizard/protocol.test.tsx` (9), `experiments/review.test.tsx` (8).
#### Review (phase-review, 2026-10-02)
- Không có phát hiện chặn.
- **#1 (nên sửa, chuyển Phase 11):** biểu tượng khóa của chip level dùng `aria-label` trên `span` không có role.
- **Ghi nhận:** mock `attack_spec` thiếu `fgsm` (chế độ mock báo kitti-baseline thiếu attack; người duyệt bổ sung mock); quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 4".
- Review do cùng agent đã viết code thực hiện (không độc lập).
#### Số liệu
- `make check` pass: 1476 test Python, 331 Vitest, 331 test nghiệm thu.
- `make test-e2e` 78/78 (7,1 phút); `pnpm verify:build` pass.

### Phase 8 — Group 3 (backend-report) — 2026-10-02
#### Thêm
- **`backend/app/reports/` (task 19–23):**
  - `snapshot.py` dựng `ReportSnapshot` đủ 9 mục (lịch sử gồm `dev-open`; mọi run kèm giải trình; case đã làm mờ; tái lập từ manifest; lưu ý theo nội dung report);
  - `render.py` render HTML Jinja2 → PDF WeasyPrint, biểu đồ matplotlib, thumbnail đã làm mờ, chân trang mọi trang;
  - `service.py`:
    - sinh nền sau `approve`, thử lại 3 lần, sinh lại khi `failed` (giữ `report_id`), sinh tiếp lúc khởi động;
    - tải bằng token HMAC 10 phút, có audit;
    - `/verify` chỉ trả report `ready`;
  - `views.py` cho `ExperimentDetail.report`.
- **Dependency:** `weasyprint 70.0`, ghi rõ `jinja2 3.1.6`, `matplotlib 3.11.2`; `pypdf 6.19.0` chỉ trong nhóm dev (người dùng chọn). Bucket `reports` thêm vào `Buckets`.
- **Image:** thêm pango, harfbuzz, font DejaVu; sinh sẵn cache font; fontconfig ghi cache vào `/tmp`. Đã kiểm: render PDF tiếng Việt chạy được trong container.
- **Test:** `test_phase08_reports.py` (14 test DB), `tests/reports/test_render.py` (7 test unit).
#### Sửa test cũ
- `test_skeleton.py`: chỉ còn `/budget` là endpoint khung.
- Test nghiệm thu Phase 0 thêm `/reports`, `/verify` vào nhóm đã cài đặt (người duyệt, người dùng cho phép).
#### Review (phase-review, 2026-10-02)
- **#1 (người dùng chọn sửa trước khi merge):** `generate` kiểm tra lại `status` trước khi dựng và trước khi ghi `failed`, nên tiến trình khác đã sinh xong không làm sinh file rác hay lỗi trigger. Có test (không có phần sửa thì test fail).
- **Ghi nhận:** test render trong CI cần pango trên runner `ubuntu-latest`; quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 3".
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Số liệu
- `make check` pass: 1476 test Python, 314 Vitest, 331 test nghiệm thu không cần DB.
- `make test-db`: 599 pass, 1 fail (test email Phase 5 có từ trước, task 37).
- Render report 4 trang trên CPU: khoảng 1 giây. Đã mở xem PDF mẫu: tiếng Việt đúng dấu, đủ 9 mục, biểu đồ rõ.

### Phase 8 — Group 2 (backend-review) — 2026-10-02
#### Thêm
- **`backend/app/reviews/` (task 11–18):**
  - gửi duyệt: điều kiện và giải trình; đặt `locked_at`, `review_submitted_at`; email cho reviewer;
  - `ensure_unlocked` kiểm ở hủy experiment, API worker, tạo run động;
  - nhận / trả lại review; hàng đợi `waiting`/`mine`/`decided`, sắp theo thời gian gửi hoặc mức sụt lớn nhất;
  - case bắt buộc top-N theo attack; verdict có version;
  - đánh giá tiêu chí (`criteria.py`, hàm thuần);
  - checklist và quyết định (`403` → `422` → `409 checklist_incomplete`), lưu tiêu chí và checklist vào `reviews`, email cho engineer;
  - bình luận chỉ thêm; audit đủ các action trong `requirements.md`;
  - `ExperimentDetail` thêm `submit_check`, `runs_requiring_explanation`, `review`.
- **Migration `0010`:** `runs.git_dirty`, ghi lúc run bắt đầu.
- **Test:** `test_phase08_reviews.py` (34 test DB), `tests/reviews/test_criteria.py` (22 test unit).
#### Sửa
- **Downgrade `0009`:** xóa thêm `reviews`, `case_verdicts`. Nếu không, khi test khác hạ cấp về `base`, migration `0002` không xóa được `failure_cases` và khoảng 200 test lỗi dây chuyền.
- **`max_relative_drop`:** bỏ metric JSON `null` (cột JSONB không lưu SQL `NULL`).
- **Test của agent:** dữ liệu `test_migration_0009.py` hợp lệ; `test_skeleton.py`, `test_route_protection_db.py` coi `/reviews` là đã cài đặt.
- **Test nghiệm thu (người duyệt, người dùng cho phép):** Phase 0 thêm `/reviews` vào nhóm đã cài đặt; Phase 4 chờ `review.decide` trả `200`.
#### Review (phase-review, 2026-10-02)
- Không có phát hiện chặn.
- Ghi nhận: hàng đợi tốn N+1 truy vấn (Phase 11); quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 2".
- Review do cùng agent đã viết code thực hiện (không độc lập).
#### Số liệu
- `make check` pass: 1473 test Python, 314 Vitest, 333 test nghiệm thu không cần DB.
- `make test-db` chạy đầy đủ trước khi sửa test nghiệm thu: 583 pass, 3 fail (2 test nghiệm thu đã sửa sau đó, chạy riêng pass; 1 là test email Phase 5 có từ trước, giao ở task 37).

### Phase 8 — Group 1 (backend-review) — 2026-10-02
#### Thêm
- **Migration `0009` (task 7):**
  - bảng mới `run_explanations`, `review_comments`; `advertest_app` chỉ có `SELECT, INSERT`;
  - `case_verdicts`: thêm `kind`, xóa `verdict`; `reviews`: thêm `model_verdict`, `inconclusive_justification`, `criteria_results`, `checklist`;
  - `reports`: chuyển sang dạng có trạng thái; quyền `UPDATE` theo cột; trigger chặn sửa dòng `ready`; mỗi experiment một report;
  - `experiments`: thêm `review_submitted_at`, `submission_note`, `review_assignee_id`, `claimed_at`, `decided_at`; `protocols`: thêm `created_at`; body `dev-open` theo v2;
  - trigger: người nhận review khác người tạo; experiment đã khóa chỉ đổi được trạng thái review và trạng thái quyết định là cuối; không thêm hay sửa run và failure case của experiment đã khóa; không thêm verdict, bình luận, giải trình sau quyết định.
- **Task 7a:** downgrade `0006` xóa `cost_profiles` của spec `not_applicable` trước.
- **`backend/app/protocols/service.py` (task 8, 10):**
  - tạo, tạo version (bản cũ chuyển `retired`, chỉ tạo từ bản mới nhất), ngừng dùng, đọc;
  - kiểm tra cần catalog: spec có thật và đang hoạt động, level và dải trong `primary_param`, patch không tìm ngưỡng, `MAX_RUNS` tính cả `max_points`;
  - audit `protocol.created`, `protocol.versioned`, `protocol.retired`; endpoint `/protocols*`.
- **`backend/app/protocols/compliance.py` (task 9):**
  - dùng chung cho ước lượng (chỉ trả danh sách), tạo experiment (`422 not_compliant` kèm `error.compliance`) và `ExperimentDetail.compliance`;
  - protocol `dev` → danh sách rỗng.
- **Test:** `test_migration_0009.py`, `test_phase08_protocols.py`, `tests/protocols/test_compliance_items.py`.
#### Sửa test cũ (agent)
- `test_migration.py`: seed `dev-open` theo body mới.
- `test_schema.py`: bảng và enum mới.
- `test_skeleton.py`: mẫu thử `501` chuyển sang `/reviews/{id}/claim`.
#### Review (phase-review, 2026-10-02)
- **#1 (người dùng chọn sửa trước khi merge):** trạng thái quyết định là cuối cả ở tầng DB; có test.
- **#2 (người dùng chọn sửa trước khi merge):** tạo protocol trùng `(name, version)` đồng thời trả `409` thay vì `500` (dùng savepoint); có test.
- **Ghi nhận:** quyết định ngầm đã ghi vào `requirements.md` mục "Chốt ở Group 1", gồm cột `review_submitted_at` lệch so với spec.
- Review và phần sửa do cùng một agent làm (không độc lập).
#### Số liệu
- `make check` pass: 1451 test Python, 314 Vitest, 334 test nghiệm thu không cần DB.
- `make test-db`: 551 pass, 1 fail (test email Phase 5 phụ thuộc ngày, có từ trước, giao ở task 37).
#### Việc tiếp theo
- **Task 37:** thử bỏ `DROP OWNED BY` trong `tests/acceptance/phase_07/conftest.py`. Run của spec corruption (Phase 6) có thể vẫn chặn downgrade `0006`.
- **Group 2:** gửi duyệt đặt `locked_at` và `review_submitted_at`, rồi đổi lỗi `check_violation` của trigger thành `409 experiment_locked`.

### Phase 8 — Group 0 (người duyệt) — 2026-10-02
#### Contract
- **`ProtocolBody` v2** (`schema_version = 2`, bỏ `review_severity_threshold`):
  - trường mới: `description`, `required_attacks` (`attack_spec_name`, `spec_sha256`, `mode`, `grid.levels` hoặc `search` gồm `max_tol` và `min_bootstrap_samples`), `pass_criteria` (`kind`, `attack_spec_name`, `level`, ngưỡng), `cases_to_review_per_attack` (mặc định 5), `forbid_dirty_runs` (mặc định `true`);
  - kiểm tra chéo ngay trong contract: tên attack không trùng; tiêu chí tham chiếu attack có thật; `max_drop_at_level` tại level bắt buộc của attack quét lưới; `min_breaking_point` cùng ngưỡng tìm kiếm, `lo < level ≤ hi`;
  - danh sách được rỗng (để `dev-open` hợp lệ); `ProtocolCreate` và `ProtocolVersionCreate` bắt buộc có ít nhất một attack và một tiêu chí.
- **Enum:** `CaseVerdictKind`, `ModelVerdict`, `CriterionKind`, `CriterionStatus`, `ReportStatus`, `CommentTargetType`, `ComplianceCode`, `ChecklistCode`, `SubmitCheckCode`, `ReviewQueueFilter`, `ReportNoteCode`. `ErrorCode` thêm `not_compliant`, `experiment_locked`, `checklist_incomplete`.
- **Schema:**
  - protocol: `ProtocolCreate`, `ProtocolVersionCreate`, `ProtocolView`;
  - gửi duyệt và review: `SubmitForReview`, `CaseVerdictInput`/`View`, `ReviewDecisionInput`, `ReviewCommentCreate`, `ReviewComment`, `ReviewQueueItem`;
  - report: `ReportView`, `ReportDetail`, `ReportSnapshot` (9 mục), `ReportDownload`, `VerifyInfo`;
  - schema lồng: `ComplianceItem`, `ChecklistItem`, `SubmitCheckItem`, `CriterionResult`, `RequiredCase`, `RunExplanation`, `ReviewView`.
- **Mở rộng schema cũ:** `ExperimentDetail` thêm `compliance`, `submit_check`, `runs_requiring_explanation`, `review`, `report`. `EstimateResponse` thêm `compliance`. `ErrorBody` thêm `compliance`, `checklist`.
- **Ma trận quyền:** `review.comment` cho engineer và reviewer. Đã cập nhật bảng trong requirements Phase 4, test nghiệm thu Phase 4 và test contract.
- **Endpoint khung (`501`, đủ `x-permission`)** cho mọi endpoint trong `requirements.md` mục "Chốt ở Group 0". `GET /protocols` có `include_retired` (đã cài đặt).
- **`tech-stack.md`:** thêm Jinja2 và matplotlib (pin phiên bản ở Group 3). Câu hỏi mở về matplotlib đã đóng.
#### Mock
- **Protocol:**
  - `protocol_body`: `default` (kitti-baseline v2), `search` (kitti-search, có tìm ngưỡng, cho phép code chưa commit), `dev_open` (body mới cho migration);
  - `protocol_view`: đủ ba trạng thái;
  - `protocol_summary`: khớp với `protocol_view`. `active.json` nay là kitti-baseline v2, v1 đã `retired`.
- **`experiment_detail/review_*`:**
  - trước gửi duyệt: `completed` sẵn sàng gửi, `completed` bị chặn (code chưa commit, case bị ẩn);
  - đang review: chờ nhận, đang review thiếu verdict, đang review đủ verdict;
  - đã quyết định: `changes_requested`, `rejected`, `approved` với report `ready`/`generating`/`failed`;
  - `criteria_results` đủ ba trạng thái, `checklist` có bản thiếu và bản đủ.
- **Mock `completed` cũ (gắn dev-open):** thêm `submit_check` báo protocol `dev`.
- **Report:** `report_snapshot` `approved_grid` (đủ 9 mục, mọi trạng thái run, lịch sử có experiment `dev-open`) và `search_dirty` (có tìm ngưỡng, ghi chú `git_dirty`), cùng mock hàng đợi, bình luận, verdict, tải report, `verify_info`.
- **`me`:** mock của engineer và reviewer có thêm `review.comment`.
- **Script sinh mock:** chỉ nằm trong scratchpad, không commit. Mock được dựng qua model Pydantic nên luôn validate được.
#### Quyết định (người dùng chọn ở Group 0, đã ghi vào `requirements.md` mục "Chốt ở Group 0")
1. Tạo version mới thì version cũ tự chuyển `retired`; chỉ được tạo version từ bản mới nhất (`409` nếu không).
2. Mỗi attack chỉ một chế độ trong protocol, giống luật Phase 5. Ví dụ ở Manual Checks đổi thành tìm ngưỡng PGD L2.
#### Quyết định của người duyệt khi làm Group 0
- **Ghi verdict qua `POST /reviews/{experiment_id}/cases/{case_id}/verdicts`**, thay cho `POST /failure-cases/{id}/verdicts`: test kiến trúc Phase 3 cấm API người dùng có endpoint ghi dưới `/failure-cases`, và tôi không nới test đó.
- **`ExperimentDetail` thêm `submit_check`, `runs_requiring_explanation`** cho hộp gửi duyệt: frontend không tự biết được `git_dirty` hay case bị ẩn. Contract chỉ kiểm một chiều (chỉ có khi `completed`), để backend Phase 5–7 chưa điền vẫn hợp lệ trước Group 2.
- **Tải report qua route có token `GET /reports/files/{token}` (`report.export`)**, không dùng `/artifacts/{token}`: route artifact chỉ ký khóa `runs/` và đòi `experiment.read`.
- **`/verify/{id}`** trả `404` khi report không có hoặc chưa `ready`.
- **Frontend `src/api/messages.ts`:** thêm thông điệp cho 3 mã lỗi mới (`Record<ErrorCode, string>` bắt buộc đủ mã), giống tiền lệ Phase 7 Group 0 sửa `status-config.ts`.
#### Sửa test cũ (người duyệt)
- **Test contract:** `test_models.py` (`test_protocol_body` theo v2), `test_phase07_models.py` (`PassCriterion` có thêm trường), `test_enums.py`, `test_permissions.py`.
- **Test nghiệm thu (bảng enum, bảng quyền):** Phase 0 `test_contracts.py` (mã lỗi Phase 8), Phase 4 `test_permissions_matrix.py` (`review.comment`).
- **Test backend:** `test_skeleton.py` (body của `POST /protocols` là `ProtocolCreate`), `test_route_protection_db.py` (18 permission có route).
- **Test mới:** `contracts/python/tests/test_phase08_models.py`.
#### Số liệu
- `make check` pass: 1431 test Python, 314 Vitest, 334 test nghiệm thu không cần DB.
- `make test-db`: 486 pass, 1 fail (`phase_05/test_email.py::test_smtp_failure_retried_then_failed_without_touching_experiment`, test phụ thuộc ngày có từ trước, giao ở task 37).
#### Lưu ý
- Group 0 do agent làm thay người duyệt theo ủy quyền của người dùng; review sau đó không độc lập.
- Việc cho Group 1:
  - migration ghi body `dev-open` mới;
  - bảng `reports` có thêm quyền `UPDATE` kèm trigger (kickoff);
  - cột `case_verdicts.verdict` (Phase 0, `NOT NULL`) không còn trong contract, nên migration cần quyết định xóa cột hay cho null.

#### Review (phase-review, 2026-10-02)
- **#1 (người dùng chọn sửa trước khi merge):** `ReportSnapshot` bắt buộc thêm lưu ý theo nội dung report. Có case đã review → `anonymization`; class mapping loại class → `excluded_classes`; có attack occlusion → `occlusion_stress`; có attack `requires_training` (patch) → `patch_fixed_position`. `ReportAttackSpec` thêm `requires_training`. Có test mới.
- **#2 (người dùng chấp nhận, ghi vào `requirements.md`):** `changes_requested` và `reject` được gửi kèm `model_verdict`, `mitigation`, `inconclusive_justification`; backend lưu lại.
- **Ghi nhận, giao Group 1:** test cho `include_retired`; body `dev-open` trong migration khớp mock.
- **Ghi nhận, giao frontend Group 4:** router mock trả cả protocol `retired` cho `/protocols`.
- **Ghi nhận, chấp nhận:** mock experiment review không có `run_view`; `GET /reports` và `GET /reviews` không phân trang.
- Sau khi sửa: `make check` pass (1436 test Python, 314 Vitest, 334 test nghiệm thu không cần DB). Không chạy lại `make test-db` vì phần sửa chỉ đụng contract và mock.
- Review và phần sửa do cùng một agent làm (không độc lập).

### Phase 8 — Kickoff — 2026-10-02
Người dùng chốt 6 câu hỏi (ghi vào `requirements.md`, `plan.md`, `validation.md`):
1. `reports` được `UPDATE` kèm trigger, dòng đã `ready` là bất biến, `report_id` không đổi khi sinh lại.
2. Khi approve: sai người → `403`; thiếu trường nhập → `422`; `checklist` chỉ gồm điều kiện trạng thái → `409`.
3. Level `early_stop` dùng đại lượng của run kích hoạt.
4. Mục Lịch sử của report có cả experiment `dev-open` cùng model version và dataset version.
5. Gửi duyệt bị chặn (`409`) khi có case bắt buộc bị ẩn.
6. Lời giải trình chỉ gửi kèm `submit`.

Bổ sung độ phủ: sửa downgrade migration 0006, bỏ `DROP OWNED BY`, sửa test email phụ thuộc ngày, xem lại số failure case mỗi run, lưu ý eps trên ảnh letterbox float, sinh tiếp report kẹt ở `generating`, test bình luận và kiểm `spec_sha256`.
