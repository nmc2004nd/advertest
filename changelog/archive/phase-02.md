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
