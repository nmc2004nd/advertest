# Requirements: Phase 2 — Attack white-box đầu tiên

## Scope

Chạy được tấn công white-box FGSM và PGD từ đầu đến cuối trên CLI, đo mức suy giảm, chọn failure case, và ghi đủ thông tin để tái lập. Kết quả của phase gồm:

1. **Adapter ART → `Perturbation`**: bọc attack của ART theo interface chung, có mask giới hạn vùng nhiễu.
2. **Ba attack**: `fgsm`, `pgd_linf`, `pgd_l2` theo catalog đã seed ở Phase 0.
3. **Metric sau tấn công**: mAP sau tấn công, mức sụt tương đối và tuyệt đối, tỷ lệ tấn công thành công.
4. **Chọn failure case** và lưu artifact để review sau này.
5. **Fingerprint và manifest** cho mỗi run.
6. **CLI** `advertest run` chạy quét lưới cho một hoặc nhiều attack, xuất `RunResult` đúng contract.

Cuối phase: mAP trước và sau PGD ở nhiều mức eps trên slice KITTI, và chạy lại cho kết quả khớp trong sai số.

## Out of Scope

- Patch attack, corruption, occlusion (Phase 6).
- Tự tìm ngưỡng (Phase 7).
- Worker, API, Postgres, MinIO (Phase 3). Phase này dùng `LocalStore`.
- Giới hạn thời gian, dừng sớm khi mAP gần 0 (Phase 3 và 6).
- Thumbnail cho failure case (Phase 3).
- PGD có random init (xem Decisions).
- Tấn công có mục tiêu (targeted).
- Lượng tử hóa ảnh về 8-bit trước khi đánh giá.

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

1. **Interface `Perturbation`** thêm tham số `mask`:

   ```python
   def apply(self, images: np.ndarray, targets: list[dict], level: float,
             seed: int, mask: np.ndarray | None = None) -> np.ndarray: ...
   ```

   `mask` có shape `(N, 1, H, W)`, giá trị 1 ở vùng ảnh thật, 0 ở vùng pad của letterbox. Cập nhật `tech-stack.md` mục 3.1 tương ứng.

2. **`Manifest.fingerprint_inputs`** thêm `git_dirty: bool`. Không thay đổi cách tính fingerprint ngoài việc trường này nằm trong input.

3. **Schema mới `FailureCaseRecord`**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid | ✓ | `content_id(sha256_of({"fingerprint": ..., "image_id": ...}))` |
| `run_id` | uuid | ✓ | |
| `fingerprint` | sha256 | ✓ | Fingerprint của run; để schema tự kiểm tra `id` (`compute_failure_case_id`) |
| `image_id` | string | ✓ | |
| `lost_objects` | int | ✓ | Số object bị mất sau tấn công |
| `new_false_positives` | int | ✓ | Số detection sai mới xuất hiện |
| `severity_score` | number | ✓ | > 0, bằng `lost_objects + 0.5 × new_false_positives` (xem Behaviour) |
| `detections` | object | ✓ | `ground_truth`, `clean`, `attacked`: list `{bbox, class_name, score}` (class đích của mapping; `score` null với ground truth, bắt buộc với prediction); `ignore_regions`: list `{bbox, source}` như `IgnoreRegion`. Box xyxy pixel trong không gian letterbox |
| `artifacts` | object | ✓ | Khóa lưu trữ của `clean_png`, `adversarial_png`, `perturbation_png` |

4. **`RunMetrics.attack_success_rate`** đổi thành `UnitFloat | None` (null khi `|C| = 0`, xem Behaviour).

### Catalog attack (giá trị trong `contracts/seeds/attack_specs.json`)

| Spec | `art_class` | Tham số chính | Dải | Tham số cố định |
|---|---|---|---|---|
| `fgsm` | `FastGradientMethod` | `eps` (đơn vị 1/255) | 0–32 | `norm = inf` |
| `pgd_linf` | `ProjectedGradientDescent` | `eps` (đơn vị 1/255) | 0–32 | `norm = inf`, `max_iter = 10`, `eps_step_ratio = 0.25`, `num_random_init = 0` |
| `pgd_l2` | `ProjectedGradientDescent` | `eps` (chuẩn L2, ảnh [0,1]) | 0–16 | `norm = 2`, `max_iter = 10`, `eps_step_ratio = 0.25`, `num_random_init = 0` |

Nếu giá trị đã seed ở Phase 0 khác bảng này, người duyệt sửa seed và tăng `version` của spec.

### Cấu hình chạy local (không thuộc contract)

CLI đọc file YAML (PyYAML, `yaml.safe_load`) theo schema `LocalRunConfig` trong `ml_core/runner/`:

| Field | Notes |
|---|---|
| `model_id`, `slice_id`, `mapping_id` | Từ Phase 1 |
| `attacks` | List `AttackConfig` (contract), Phase 2 chỉ hỗ trợ `mode = grid` |
| `device`, `batch_size` | |
| `failure_cases_per_run` | Mặc định 20 |

`experiment_id` của run chạy qua CLI = `content_id(sha256_of(cấu hình))` (`advertest_contracts.ids`). `ExperimentConfig` đầy đủ (có protocol, compute target, giới hạn) chỉ dùng từ Phase 3.

## Behaviour

### Chạy attack
- Mỗi cặp (attack, level) là một run.
- Ảnh đầu vào là batch letterbox từ `SliceLoader` của Phase 1; nhãn đưa vào attack là **ground truth đã map class** (không gồm ignore region), lấy nguyên `targets` của loader: `boxes` xyxy letterbox, `labels` là chỉ số class trong model.
- Đổi đơn vị: `eps = level / 255` với L∞; `eps = level` với L2. `eps_step = eps × eps_step_ratio` (thiếu `eps_step_ratio` thì dùng 0.25); FGSM dùng `eps_step = eps`.
- `level` nằm ngoài `[min, max]` của spec → lỗi (`ValueError`), run đó `failed`.
- Nhiễu **chỉ nằm trong vùng ảnh thật**: truyền `mask` vào attack của ART **và** áp lại mask sau `generate` (vùng mask = 0 lấy nguyên ảnh gốc); điểm ảnh ở vùng pad không đổi. Lý do: ART 1.20.1 bỏ qua `mask` trong `FastGradientMethod` khi estimator là object detector. Mask dựng từ `LetterboxInfo` của từng ảnh (`pad` và kích thước sau resize, `ml_core.preprocess`).
- Ảnh sau tấn công được cắt lại về `clip_values` của estimator ([0, 1]) sau `generate`.
- `level = 0` cho ảnh sau tấn công trùng ảnh gốc.
- Nếu spec yêu cầu gradient mà `ModelCard.supports_gradients = false` → run có trạng thái `skipped`, `status_reason.code = incompatible`, không chạy.

### Metric
- mAP sau tấn công tính bằng đúng pipeline của Phase 1 (`CleanMetric`: cùng `inference_params`, lọc class, lọc ignore region, giới hạn detection theo `max_det`). mAP sạch lấy từ cache prediction của Phase 1 (`prediction_cache_key`, `load_predictions`); nếu chưa có cache thì chạy như `advertest eval`.
- `absolute_drop = map50_sạch − map50_tấn_công` (có thể âm nếu attack làm mAP tăng).
- `relative_drop = absolute_drop / map50_sạch`; nếu `map50_sạch = 0` thì trả `null`.
- **Lọc trước khi ghép** (người dùng chốt, Group 2): prediction trên cả ảnh sạch và ảnh sau tấn công được lọc như pipeline mAP (chỉ class đích; bỏ prediction có IoA ≥ 0.5 với ignore region) trước khi tính tập C và FP mới.
- **Tỷ lệ tấn công thành công:**
  1. Tập C = các object ground truth được detect đúng trên ảnh sạch: có prediction với score ≥ `operating_conf` (0.25), cùng class, IoU ≥ 0.5 (tính cả biên), ghép một-một theo thứ tự score giảm dần (sắp xếp ổn định); mỗi prediction ghép với ground truth chưa ghép có IoU lớn nhất.
  2. Một object trong C bị tính là **mất** nếu không được ghép khi chạy cùng phép ghép một-một trên ảnh sau tấn công (người dùng chốt, Group 2).
  3. `attack_success_rate = số object mất / |C|`; nếu `|C| = 0` thì trả `null`.
- `new_false_positives` của một ảnh = số prediction sau tấn công (score ≥ `operating_conf`) không ghép được với ground truth nào và không nằm trong ignore region, trừ đi số tương ứng trên ảnh sạch (tối thiểu 0).

### Failure case
- `severity_score = lost_objects + 0.5 × new_false_positives`.
- Mỗi run giữ `failure_cases_per_run` ảnh có `severity_score` cao nhất (lớn hơn 0), cùng điểm thì ưu tiên `image_id` nhỏ hơn (so theo chuỗi) để kết quả xác định.
- Box trong `FailureCaseRecord.detections`: ground truth của loader; `clean`, `attacked` là prediction đã lọc (class đích, score ≥ `operating_conf`, ngoài ignore region); ignore region kèm `source`.
- Lưu cho mỗi case: ảnh sạch và ảnh sau tấn công dạng PNG (letterbox), ảnh nhiễu khuếch đại dạng PNG (cắt về [0, 1]: `0.5 + δ / (2·eps)` với L∞; `0.5 + δ / (2·max|δ|)` của chính ảnh đó với L2, δ = 0 thì toàn ảnh 0.5), và `FailureCaseRecord`.
- Metric luôn tính trên ảnh float, không tính lại từ PNG.

### Fingerprint và manifest
- `fingerprint_inputs` đúng như contract, trong đó `config_sha256` là hash của cấu hình **riêng run đó**: `spec_sha256`, `level`, `fixed_params`, `inference_params`, cấu hình letterbox (`LETTERBOX_CONFIG`), `class_mapping_sha256`.
- `git_commit` lấy như `advertest eval` của Phase 1 (biến `GIT_COMMIT`, không thì `git rev-parse HEAD`); nếu working tree có thay đổi chưa commit (bỏ qua `.ai-log/` và file chưa theo dõi, dùng pathspec `:(exclude).ai-log`) thì `git_dirty = true` và CLI in cảnh báo. Có biến `GIT_COMMIT` (image Docker không có `.git`) thì `git_dirty = false`. `advertest eval` dùng cùng cách kiểm tra.
- `docker_image_digest` lấy từ biến `DOCKER_IMAGE_DIGEST` (dạng `sha256:<64 hex>`), không có thì `"none"`. Phase 3 đặt biến này khi build image.
- `environment` ghi GPU, CUDA, driver (null khi chạy trên CPU; driver lấy bằng `nvidia-smi` nếu có); `compute_target_id = null` khi chạy bằng CLI.
- **Bố cục store** (người dùng chốt, Group 3), store bất biến:
  - `runs/<fingerprint>/`: kết quả `completed` đầu tiên (`manifest.json`, `result.json`, `cases/<image_id>/{clean,adversarial,perturbation}.png`, `cases/<image_id>/record.json`). `result.json` được ghi sau cùng: có `result.json` nghĩa là run đã ghi đủ artifact.
  - `runs/<fingerprint>/reruns/<run_id>/`: chạy lại bằng `--force` khi đã có kết quả (chưa có thì `--force` ghi vào thư mục chính).
  - `runs/<fingerprint>/attempts/<run_id>/`: run `failed` và `skipped` (`incompatible`), gồm `manifest.json` và `result.json`.
- `run_id` là uuid4.

### Cache theo fingerprint
- Trước khi chạy, CLI kiểm tra `runs/<fingerprint>/result.json`. Nếu đã có kết quả `completed`: không chạy lại, xuất `RunResult` mới với `status = skipped`, `status_reason.code = cached`, `run_id` mới (uuid4), `manifest_uri` trỏ tới manifest cũ; `metrics`, `failure_case_ids`, `progress` chép từ kết quả cũ, `gpu_seconds = 0`. `RunResult` này chỉ in ra (bảng tóm tắt và JSON trên stdout), không ghi vào store; `runs/<fingerprint>/` không đổi. Khi mọi run đều cached và đã có cache prediction ảnh sạch, model không được nạp.
- Cờ `--force` bỏ qua cache và chạy lại, ghi vào thư mục `runs/<fingerprint>/reruns/<run_id>/` (không ghi đè kết quả cũ).

### CLI
- `advertest run --config <yaml> [--force]`: chạy tuần tự mọi run, in tiến độ theo batch, cuối cùng in bảng tóm tắt (attack, level, mAP sạch, mAP sau tấn công, relative drop, ASR, trạng thái). stdout là mảng JSON các `RunResult`; tiến độ, cảnh báo và bảng tóm tắt in ra stderr.
- `advertest run show <fingerprint>`: in `RunResult` của thư mục chính ra stdout, đường dẫn artifact và các lần chạy khác (`reruns/`, `attempts/`) ra stderr; fingerprint không có run nào thì mã thoát 1.
- `gpu_seconds` = thời gian thực của phần tấn công và inference trên thiết bị; `cost = null`.
- Một run lỗi (ngoại lệ, kể cả khi dựng attack) có `status = failed` kèm thông điệp lỗi; các run khác vẫn tiếp tục.

### Tái lập
- Sai số tái lập: `map50` ±0.005, `attack_success_rate` ±0.01.
- Kết quả không phụ thuộc batch size (trong sai số trên).

## Decisions

- **PGD không dùng random init trong MVP (`num_random_init = 0`).** *Lý do:* random init của ART lấy số ngẫu nhiên theo cả batch, nên kết quả sẽ phụ thuộc batch size, mà batch size lại khác nhau giữa các máy. Điều đó phá vỡ việc dùng lại kết quả giữa các máy theo fingerprint. Biến thể có random init sẽ là một spec riêng sau này.
- **Nhãn cho attack là ground truth, không phải prediction của model.** *Lý do:* đo khả năng làm model sai so với sự thật. Dùng prediction thì object vốn đã bị model bỏ sót sẽ không bị tấn công.
- **Nhiễu chỉ trong vùng ảnh thật.** *Lý do:* với KITTI, vùng pad chiếm khoảng 70% ảnh letterbox. Cho phép nhiễu ở đó vừa phi thực tế (camera không chụp vùng pad) vừa làm attack mạnh giả tạo.
- **Nhiễu áp dụng trong không gian đầu vào của model (sau letterbox).** *Lý do:* đây là mô hình tấn công số chuẩn. Report sau này phải ghi rõ eps tính trên ảnh đã thu nhỏ, không phải ảnh gốc.
- **Metric tính trên ảnh float, PNG chỉ để hiển thị.** *Lý do:* lượng tử hóa về 8-bit làm mất nhiễu ở eps nhỏ; mô phỏng lưu ảnh thật là một tùy chọn có thể thêm sau.
- **Chạy lại với `--force` không ghi đè kết quả cũ.** *Lý do:* nguyên tắc 3 trong `mission.md`: kết quả không bị xóa hay thay thế.
- **`attacks/` không phụ thuộc `ml_core/`.** Adapter nhận estimator ART qua factory `build_perturbation(spec, estimator)`. *Lý do:* giữ ranh giới thư mục giữa các agent và cho phép thay model mà không sửa attack.
- **Mask được áp lại sau `generate` cho mọi attack ART** (Group 1). *Lý do:* ART 1.20.1 bỏ qua `mask` trong `FastGradientMethod` với object detector (đã xác nhận: nhiễu 8/255 ở vùng pad). Với FGSM L∞ mỗi điểm ảnh độc lập qua `sign`, nên che sau cho kết quả như che gradient; PGD vẫn nhận mask để chuẩn hóa L2 đúng.
- **Lọc prediction như pipeline mAP trước khi ghép, ghép một-một cho cả ảnh sạch và ảnh sau tấn công** (người dùng chốt, Group 2). *Lý do:* nhất quán với mAP; prediction của class không đích (ví dụ `bird`) không bị tính là FP mới.
- **Run lỗi và run không tương thích ghi vào `attempts/<run_id>/`** (người dùng chốt, Group 3). *Lý do:* store bất biến; nếu ghi vào `runs/<fp>/result.json` thì lần chạy lại không ghi được kết quả `completed`, còn không ghi thì mất dấu vết lỗi (nguyên tắc 3).
- **Preset `kitti-coco` giữ nguyên, không gộp `bus` của model vào `truck`** (người dùng chốt, 2026-09-28). *Lý do:* slice KITTI chỉ có 26 ground truth `truck`; đổi preset làm đổi `mapping_sha256`, baseline và golden Phase 1. Report ghi rõ hạn chế về AP `truck`.

## Context

- `mission.md` nguyên tắc 3, 4 (bất biến, tái lập) và 6 (trạng thái rõ ràng).
- `tech-stack.md` mục 2.3 (định nghĩa metric), 3 (attack), 4.3 (enum), 4.4 (fingerprint).
- Phase 0: contract, `canonical_json`, `compute_fingerprint`, seed catalog, fixture.
- Phase 1: loader, letterbox, estimator ART, `ModelCard`, pipeline metric, cache prediction sạch, `LocalStore`.

## Open Questions

- [ ] Dải `eps` của `pgd_l2` (0–16) cần hiệu chỉnh sau khi có kết quả thật trên KITTI.
- [ ] Số failure case mỗi run (mặc định 20) có đủ cho reviewer không.
- [x] Preset `kitti-coco`: có map thêm class `bus` của model cho `Truck` của KITTI không (Phase 1: AP `truck` = 0.188 vì KITTI gán `Truck` cả cho xe buýt). → Giữ nguyên, xem Decisions (2026-09-28).
