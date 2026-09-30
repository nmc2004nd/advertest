# Requirements: Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

## Scope

Hoàn thiện bộ phép thử cho MVP, làm cho quét lưới hiệu quả hơn, và đưa tính năng làm mờ ảnh lên trước Phase 8 để report có ảnh failure case. Kết quả của phase gồm:

1. **Corruption:** `fog`, `snow`, `frost`, `motion_blur`, `contrast`, severity 1–5.
2. **Occlusion:** che theo tỷ lệ diện tích bounding box.
3. **Patch attack:** train một lần trên slice huấn luyện riêng, lưu lại, tái sử dụng; quét theo kích thước patch.
4. **Quét lưới thô trước, mịn sau**, và **dừng sớm** khi model đã sụp.
5. **Xếp hạng attack gây hại nhất** trong một experiment.
6. **Làm mờ mặt người và biển số** trên mọi ảnh hiển thị (chuyển từ Phase 10 lên).
7. **Trang admin xem attack catalog** (chỉ đọc).

Cuối phase: một experiment quét toàn bộ catalog trên slice KITTI, ra bảng xếp hạng attack, và failure case hiển thị được với ảnh đã làm mờ.

## Out of Scope

- Tự tìm ngưỡng (Phase 7).
- Patch bám theo từng object (kiểu sticker dán lên xe). Phase này dùng patch ở vị trí cố định trên ảnh.
- Tấn công có mục tiêu, black-box.
- Thêm, sửa, tắt attack spec qua giao diện. Catalog vẫn quản lý bằng file seed và migration.
- Làm mờ bằng model phát hiện mặt và biển số chuyên dụng (xem Decisions).
- Upload dataset, converter YOLO/COCO (vẫn ở Phase 10).

## Data / Fields

### Thay đổi constitution và contract (cần người duyệt chấp nhận)

**`roadmap.md`:** chuyển mục "Làm mờ mặt và biển số" từ Phase 10 sang Phase 6; đổi tên Phase 6 thành "Đủ attack catalog, quét lưới và làm mờ ảnh".

**Contract:**

| Thay đổi | Nội dung |
|---|---|
| `AttackAccess` | Thêm `not_applicable` cho corruption và occlusion |
| `AttackSpec` | Thêm `requires_training: bool`, `training` (tham số huấn luyện, null nếu không cần) |
| `AttackConfig` | Thêm `training_slice_id` (bắt buộc khi spec cần huấn luyện); `grid.early_stop: bool` (mặc định `true`) |
| `SkipReason` | Thêm `early_stop` |
| `PatchArtifact` (mới) | `key`, `spec_sha256`, `weights_sha256`, `training_slice_sha256`, `area_ratio`, `seed`, `patch_sha256`, `png_key`, `npy_key`, `training_seconds`, `objective_history` |
| `Manifest.fingerprint_inputs` | Thêm `patch_key` (null nếu không dùng patch) |
| `ProgressReport` | Thêm `phase` (`training` / `evaluating`), `iterations_done`, `iterations_total` |
| `CostProfile` | Thêm `sec_per_image_iteration` (null nếu spec không cần huấn luyện) |
| API nội bộ của worker | Báo run chưa start là `skipped` với `early_stop` (không cần start trước) |
| `EstimateResponse.runs[]` | Thêm `training_seconds` (null nếu patch đã có sẵn hoặc không cần) |
| `FailureCaseRecord` | Thêm `anonymization`: `applied`, `method`, `version`, `regions_count` |
| `ExperimentDetail` | Thêm `attack_ranking` (xem Behaviour) |
| Interface `Perturbation` | Ghi rõ: mỗi phần tử của `targets` bắt buộc có `image_id` |

**Chi tiết chốt ở Group 0** (người duyệt, 2026-10-01; code trong `contracts/python/advertest_contracts/models.py`):

- **Hash cũ không đổi:** các trường mới có giá trị mặc định (`AttackSpec.requires_training`, `training`; `GridConfig.early_stop`; `AttackConfig.training_slice_id`; `FingerprintInputs.patch_key`; `StatusReason.trigger_run_id`) bị bỏ khỏi JSON khi mang giá trị mặc định (`exclude_if`), và JSON Schema không khai chúng là bắt buộc. `spec_sha256` của 3 spec cũ, `config_sha256` và fingerprint của run không dùng patch giữ nguyên.
- **`AttackSpec.training`** (`TrainingParams`): `max_iter`, `learning_rate` (thang [0, 1]), `sample_size`, `checkpoint_every`, `max_training_images`. Seed `adv_patch`: 200, 0.02, 1, 50, 50. Giới hạn 50 ảnh của slice huấn luyện đọc từ `max_training_images`. Attack không được có `access = not_applicable`.
- **`adv_patch.cost_model = cpu_only`:** giai đoạn đánh giá chỉ dán patch rồi chạy inference; chi phí train tính riêng qua `sec_per_image_iteration`.
- **Dừng sớm:** `StatusReason.trigger_run_id` (có khi và chỉ khi `code = early_stop`) trỏ tới run đã kích hoạt; `RunView.fingerprint` được null với run `skipped` do `early_stop` (run chưa từng start). Endpoint `POST /internal/worker/runs/{id}/skip` (`RunSkipRequest`, `204`). `BundleRun.metrics` để worker tính lại khi chạy tiếp.
- **Patch:** `compute_patch_key` và `patch_prefix` (`patches/<key>/`) trong contract để backend và worker tính cùng khóa. `PatchArtifact` thêm `side_px`, `iterations`, `created_at`; `objective_history` là loss của detector trên ảnh đã dán patch (attack untargeted làm giá trị này tăng). `WorkerJobBundle` thêm `training_slices` (ảnh của chúng có trong `downloads.images`), `patches[]` (`artifact` khi đã train, `checkpoint_key` khi đang dở) và `runs[].patch_key`. `POST /internal/worker/runs/{id}/patch` (`PatchRegistration` → `PatchArtifact`; khóa đã có thì giữ bản cũ và trả bản đó). `artifact-url` nhận thêm khóa trong `patches/<patch_key>/` của run.
- **Tiến độ train:** `ProgressReport` với `phase = training` có `images_done = 0`, `batch_index = 0`, `checkpoint_key` là checkpoint patch mới nhất trong `patches/<key>/` (worker ghi checkpoint ở vòng 0 trước lần báo đầu); file checkpoint tự ghi số vòng lặp đã xong. `RunView` thêm `phase` (chỉ khi `running`) và `training` (`{done, total}`, khi `phase = training`).
- **Ảnh thứ ba:** `FailureCaseRecord.perturbation_kind` (`amplified_noise` / `difference` / `patch_location`, mặc định `amplified_noise` cho case cũ) để trình xem chọn nhãn, không phải suy từ loại attack.
- **Catalog cho admin:** `GET /admin/attack-specs` (`attack_catalog.manage`, `cursor`, `limit`) trả `AttackSpecAdminPage` gồm mọi version, kể cả spec đã tắt (`AttackSpecAdminView` = `AttackSpec` + `is_active`).
- **DB:** migration `0006` chỉ thêm giá trị `not_applicable` vào enum `attack_access` (để seed mới nạp được và test enum khớp contract). Bảng patch, cột `anonymization`, `sec_per_image_iteration` thuộc Group 5.

### Catalog (thêm vào `contracts/seeds/attack_specs.json`)

| Spec | Loại | Tham số chính | Giá trị | Tham số cố định |
|---|---|---|---|---|
| `fog` | corruption | `severity` | 1, 2, 3, 4, 5 | Hàm `fog` của imagecorruptions |
| `snow` | corruption | `severity` | 1–5 | `snow` |
| `frost` | corruption | `severity` | 1–5 | `frost` |
| `motion_blur` | corruption | `severity` | 1–5 | `motion_blur` |
| `contrast` | corruption | `severity` | 1–5 | `contrast` |
| `bbox_occlusion` | occlusion | `occlusion_ratio` | 0–0.9 (liên tục) | Hình chữ nhật cùng tỉ lệ với box, màu 114/255 |
| `adv_patch` | attack | `area_ratio` | 0.02–0.25 (liên tục) | `RobustDPatch` của ART; vị trí: tâm vùng ảnh thật; `max_iter = 200`; `brightness_range = (0.8, 1.2)`; `learning_rate` hiệu chỉnh ở manual check |

Mọi spec corruption và occlusion có `requires_gradients = false`, `access = not_applicable`. `adv_patch` có `requires_gradients = true`, `requires_training = true`.

### Xếp hạng attack (`attack_ranking[]`)

| Field | Ý nghĩa |
|---|---|
| `attack_spec_id`, `name`, `kind` | |
| `auc_drop` | Diện tích dưới đường `relative_drop` theo level chuẩn hóa `x = level / max` của spec |
| `coverage` | `x` lớn nhất được tính (level lớn nhất có kết quả hoặc bị `early_stop`) |
| `max_relative_drop` | Mức sụt lớn nhất đo được |
| `levels_evaluated` | Số level có metric |
| `levels_early_stopped` | Số level bị bỏ qua do `early_stop` (được tính vào đường cong) |
| `partial` | Có run `stopped_limit` hoặc `metrics.partial` |

## Behaviour

### Seed theo từng ảnh
- Mọi phép biến đổi có yếu tố ngẫu nhiên (vị trí che, hạt tuyết, mẫu sương giá) dùng seed riêng cho từng ảnh: `seed_i = hash(seed, image_id)`. Kết quả vì vậy không phụ thuộc batch size hay thứ tự ảnh.

### Corruption
- Áp dụng trong không gian đầu vào của model: cắt vùng ảnh thật (không gồm pad) → chuyển sang uint8 → áp corruption ở severity tương ứng → chuyển về float [0, 1] → đặt lại vào ảnh letterbox. Vùng pad không đổi.
- Mọi hàm corruption phải chạy được với kích thước vùng ảnh thật của KITTI (khoảng 640×193). Nếu phiên bản imagecorruptions đã pin lỗi với numpy/scikit-image hiện tại, dùng bản thay thế tương đương của albumentations hoặc bản vá nội bộ, và ghi vào `tech-stack.md`.

### Occlusion
- Với mỗi object ground truth đã map: đặt một hình chữ nhật cùng tỉ lệ với box, diện tích bằng `occlusion_ratio` × diện tích box, vị trí ngẫu nhiên (theo seed ảnh) nằm hoàn toàn trong box, tô màu 114/255.
- Điểm ảnh ngoài các box và trong ignore region không đổi. `occlusion_ratio = 0` cho ảnh không đổi.
- Đây là phép thử chịu tải (stress test) mô phỏng vật che khuất, không phải năng lực của kẻ tấn công; report phải ghi rõ.

### Patch attack
- **Huấn luyện:** trên `training_slice_id`, slice này **không được giao** với slice đánh giá, cùng dataset version, và có **tối đa 50 ảnh** (kiểm tra khi tạo experiment, `422`). Kích thước patch vuông, diện tích = `area_ratio` × diện tích vùng ảnh thật. Patch nằm hoàn toàn trong vùng ảnh thật.
- **Khóa patch** = hash của (`spec_sha256`, `weights_sha256`, `training_slice_sha256`, `area_ratio`, `seed`). Mỗi khóa chỉ train một lần; lần sau dùng lại từ MinIO.
- Worker train patch khi chưa có, trước khi đánh giá run đó. Thời gian train tính vào giới hạn của experiment. Lưu checkpoint patch mỗi 50 vòng lặp; bị gián đoạn thì train tiếp từ checkpoint.
- **Đánh giá:** dán patch vào vị trí cố định trên mọi ảnh của slice đánh giá, rồi chạy pipeline metric như các attack khác.
- **Tạo slice huấn luyện** (bổ sung ở Group 0): CLI `advertest slice create` thêm `--exclude-slice <id>` để lấy ảnh không thuộc slice đánh giá; `GET /slices` thêm tham số `disjoint_from=<slice_id>` để wizard chỉ liệt kê slice không giao (wizard tự lọc cùng dataset version và kích thước ≤ `max_training_images`).
- `PatchArtifact` lưu patch (PNG và mảng numpy), lịch sử giá trị mục tiêu theo vòng lặp.

### Quét lưới: thứ tự và dừng sớm
- **Nơi đặt logic:** hàm thứ tự và điều kiện dừng sớm là hàm thuần trong `ml_core/runner/grid.py`. Backend gán `ordinal` của run theo thứ tự thô → mịn khi tạo experiment. Worker gọi hàm dừng sớm trước mỗi run và báo `skipped` (`early_stop`) qua API nội bộ. Khi chạy tiếp sau gián đoạn, worker tính lại điều kiện từ metric của các run đã xong trong bundle.
- **Thứ tự:** với mỗi attack, các level xếp tăng dần; lượt một chạy các level ở vị trí chẵn (0, 2, 4, ...), lượt hai chạy các level còn lại. Nhờ vậy khi bị dừng do giới hạn, experiment vẫn có kết quả trải trên toàn dải.
- **Dừng sớm** (khi `grid.early_stop = true`): khi một level cho `map50_tấn_công ≤ 0.05 × map50_sạch`, mọi level **lớn hơn** của cùng attack chưa chạy được đánh dấu `skipped` với `status_reason.code = early_stop`, không chạy.
- Dừng sớm chỉ áp dụng trong cùng một attack.

### Xếp hạng attack
- `auc_drop` tính bằng quy tắc hình thang trên các điểm (`level / max`, `relative_drop`), thêm điểm (0, 0) ở đầu. Diện tích tính đến `coverage`, không ngoại suy ra đến 1; bảng xếp hạng hiển thị `coverage`.
- Level bị `early_stop` được tính với `relative_drop` bằng giá trị của level đã kích hoạt dừng sớm.
- Attack có ít hơn 2 điểm (level có metric cộng level `early_stop`): `auc_drop = null`, xếp cuối, ghi chú "không đủ dữ liệu". Level `early_stop` được đếm (chốt ở Group 0) để attack mạnh sụp ngay ở level đầu không bị xếp cuối.
- Xếp giảm dần theo `auc_drop`. Hàm tính nằm trong `ml_core/metrics/ranking.py`, backend dùng lại để Phase 8 (report) cho cùng kết quả.

### Làm mờ ảnh
- Áp dụng khi **tạo ảnh hiển thị** (ảnh sạch, ảnh sau biến đổi, ảnh thứ ba — nhiễu khuếch đại / vùng khác biệt / vị trí patch —, thumbnail) cho failure case, cùng vùng `rule_v1`, trên mọi dataset có `anonymized = false`.
- Vùng làm mờ (phương pháp `rule_v1`), lấy từ hợp của ground truth, prediction trên ảnh sạch và prediction sau biến đổi (score ≥ 0.25):
  - `person`: 1/3 phía trên của box (vùng đầu);
  - `car`, `truck`: dải 40% phía dưới của box (vùng biển số);
  - toàn bộ ignore region (vùng `DontCare` thường chứa người và xe ở xa).
- Làm mờ bằng Gaussian đủ mạnh để không nhận ra chi tiết (bán kính tỉ lệ với kích thước vùng, tối thiểu 8 px) rồi pixelate.
- **Không lưu bản chưa làm mờ** của ảnh hiển thị. Metric vẫn tính trên ảnh gốc chưa làm mờ.
- `FailureCaseRecord.anonymization.applied = true` với mọi case mới.
- Quy tắc hiển thị ở Phase 5 cập nhật: case có `anonymization.applied = true` → `display_mode = normal` dù dataset chưa ẩn danh. Case cũ chưa làm mờ vẫn `hidden_unanonymized` (trừ khi bật cờ dev).

### Ước lượng
- `training_seconds` của patch = `max_iter` × số ảnh của slice huấn luyện × `sec_per_image_iteration` (từ cost profile của patch), null nếu patch đã có sẵn. `training_seconds` được cộng vào `total_seconds` và vào cận dưới dùng cho `exceeds_limit`.
- Calibration cho `adv_patch` đo thêm `sec_per_image_iteration` (chạy 5 vòng lặp huấn luyện).
- Corruption và occlusion dùng `sec_per_image` của inference (chi phí biến đổi chạy trên CPU được tính gộp).

### Frontend
- **Wizard bước 4** chia ba nhóm: "Tấn công" (FGSM, PGD, Patch), "Biến đổi điều kiện" (các corruption), "Che khuất". Corruption chọn severity bằng chip 1–5. Patch yêu cầu chọn slice huấn luyện (lọc bỏ slice giao với slice đánh giá) và hiển thị thời gian train nếu cần.
- Nút preset "Toàn bộ catalog" chọn mọi attack với level mặc định; riêng `adv_patch` chọn 2 `area_ratio`: 0.1 và 0.25 (mỗi giá trị train một patch).
- Công tắc "Dừng sớm khi model đã sụp" (bật mặc định) kèm giải thích một dòng.
- **Tab Kết quả** thêm:
  - bảng xếp hạng attack (tên, loại, `auc_drop`, mức sụt lớn nhất, số level, `coverage`, cờ partial);
  - biểu đồ cột `auc_drop` theo attack;
  - tùy chọn trục hoành chuẩn hóa (% dải cho phép) để so sánh các attack khác đơn vị.
- Bảng run hiển thị lý do `early_stop` rõ ràng ("Bỏ qua: model đã sụp ở level thấp hơn").
- Tiến độ run patch hiển thị giai đoạn "Đang train patch (x/200)" rồi "Đang đánh giá".
- **Trình xem case:** nhãn ảnh thứ ba theo loại (Nhiễu khuếch đại / Vùng khác biệt / Vị trí patch); hiển thị dải "Đã làm mờ mặt và biển số" khi `anonymization.applied`.
- **Trang `/admin/attacks`** (permission `attack_catalog.manage`): danh sách spec với loại, access, tham số chính và dải, tham số cố định, version, hash (rút gọn, có nút copy), trạng thái; thẻ trên điện thoại.

## Decisions

- **Làm mờ được chuyển lên Phase 6.** *Lý do:* report ở Phase 8 cần ảnh failure case; nếu làm mờ ở Phase 10 thì report sẽ thiếu ảnh hoặc vi phạm `mission.md` nguyên tắc 9.
- **Làm mờ theo quy tắc từ box, không dùng model phát hiện mặt/biển số.** *Lý do:* không thêm model và giấy phép mới; quy tắc thiên về làm mờ thừa hơn thiếu, phù hợp nguyên tắc riêng tư. Có thể nâng cấp lên model chuyên dụng sau (`method` và `version` đã có trong contract).
- **Không lưu ảnh hiển thị chưa làm mờ.** *Lý do:* thứ không lưu thì không thể lộ; ảnh gốc vẫn tái tạo được từ dataset, manifest và seed khi thật sự cần.
- **Corruption áp trong không gian đầu vào của model, trên vùng ảnh thật.** *Lý do:* thống nhất với attack (eps cũng tính trong không gian này) và không làm nhòe vùng pad vào ảnh. Report ghi rõ điều này.
- **Seed theo từng ảnh.** *Lý do:* giữ tính không phụ thuộc batch size đã đặt ra ở Phase 2 cho cả các phép biến đổi ngẫu nhiên.
- **Patch cố định vị trí, train trên slice riêng.** *Lý do:* train và đánh giá trên cùng ảnh sẽ thổi phồng hiệu quả của patch. Vị trí cố định là cách làm chuẩn của DPatch và đơn giản; patch bám object để sau.
- **Dừng sớm chỉ bỏ các level lớn hơn trong cùng attack.** *Lý do:* giả định cường độ tăng thì mức sụt không giảm chỉ hợp lý trong cùng một attack.
- **Xếp hạng dùng diện tích dưới đường cong trên dải chuẩn hóa.** *Lý do:* so sánh được các attack khác đơn vị (eps, severity, tỉ lệ che); một con số duy nhất dễ đọc hơn so từng điểm.
- **Chuẩn hóa `x = level / max`, không ngoại suy** (kickoff). *Lý do:* level 0 luôn là "không biến đổi" với mọi spec; tránh severity 1 trùng điểm (0, 0) như khi dùng `(level − min)/(max − min)`; không tạo dữ liệu ngoài dải đã đo.
- **Dừng sớm: hàm thuần ở ml-core, worker áp dụng, backend gán thứ tự** (kickoff). *Lý do:* worker lease cả experiment và chạy run theo `ordinal`; quyết định dừng sớm phải tính lại được khi worker chạy tiếp sau gián đoạn.
- **Chi phí train tính theo ảnh × vòng lặp; slice huấn luyện tối đa 50 ảnh; preset chọn 2 kích thước patch** (kickoff). *Lý do:* mỗi vòng lặp của `RobustDPatch` đi qua toàn bộ slice huấn luyện, và mỗi `area_ratio` là một patch riêng; giữ thời gian train trên laptop chấp nhận được và ước lượng đúng.
- **Làm mờ cả ảnh thứ ba** (kickoff). *Lý do:* |δ| của corruption (ví dụ `contrast`, `fog`) gần như tái hiện nguyên cảnh (`mission.md` nguyên tắc 9).
- **E2E dùng seed `adv_patch` với `max_iter = 4`** (kickoff). *Lý do:* thấy được giai đoạn train mà vẫn chạy nhanh trên CPU; catalog E2E vẫn đủ 10 spec (chỉ khác `spec_sha256` của patch).

## Context

- `mission.md` nguyên tắc 4 (tái lập), 5 (chi phí), 9 (riêng tư); mục 5 (phạm vi: thời tiết, che khuất, patch).
- `tech-stack.md` mục 3 (attack, quy ước), 3.2 (patch train một lần).
- Phase 2: adapter ART, mask, metric, failure case. Phase 3: executor, checkpoint, cost profile, ước lượng. Phase 5: wizard, tab Kết quả, `CaseViewer`, quy tắc `display_mode`.
- Phase 3 (ảnh hưởng thiết kế): ảnh failure case được tạo ở worker lúc ảnh vào top-K (`StoreCandidates`, `ml_core/runner/candidates.py`), nên làm mờ phải chạy ở đó trước khi upload; `RunExecutor.process_batch` hiện truyền `targets` không có `image_id` vào `Perturbation.apply` (cần sửa cùng thay đổi interface); thời gian train patch phải được worker báo qua `progress` (`processing_seconds_delta`) mới được tính vào giới hạn; thời gian calibration hiện không tính.
- Đo ở Phase 3: PGD trên KITTI thật phụ thuộc nhẹ vào batch size (≤ 0.0006 mAP, ≤ 0.006 ASR giữa batch 2 và batch 8), trái với giả định "không phụ thuộc batch size" của Phase 2; cần kiểm lại khi thêm seed theo ảnh.
- Phase 5 (ảnh hưởng thiết kế):
  - `display_mode` hiện tính lúc đọc trong `backend/app/services/artifacts.py`, chỉ từ `datasets.anonymized` và `DEV_ALLOW_UNBLURRED`. Quy tắc mới theo từng case (`anonymization.applied`) cần lưu `anonymization` cùng failure case trong DB (migration), và `FailureCaseView` phải bỏ khóa MinIO khi ảnh bị ẩn (Phase 5 vẫn trả khóa trong `artifacts`).
  - Ước lượng: `total_seconds` là null khi có run thiếu profile; `exceeds_limit` tính trên cận dưới. `training_seconds` phải cộng vào cả hai.
  - Bộ level gợi ý của wizard (lũy thừa của 2, spec rời rạc lấy mọi giá trị) áp cho preset "Toàn bộ catalog" cho khoảng 45 run, sát trần `MAX_RUNS = 50` (`experiment_config.py`). Thêm spec hoặc severity nữa sẽ vượt trần.
  - Nháp wizard lưu ở `localStorage` khóa `advertest.wizard.v1`, và `loadDraft` chỉ gộp nông. Thêm `training_slice_id` và `early_stop` vào từng attack thì phải điền mặc định cho nháp cũ, hoặc đổi khóa sang `v2`.
  - E2E: 3 viewport chạy tuần tự trên cùng DB nên run trúng cache; worker CPU chạy thật trên fixture 5 ảnh; máy `e2e-offline` không có worker. `scripts/e2e.sh` nạp `adv_patch` với `max_iter = 4` thay cho 200 (xem Decisions).
  - `status_reason.code = early_stop` được đếm vào "bỏ qua" trong câu tóm tắt và email (cùng hàm tóm tắt); bảng run cần thêm nhãn riêng.

## Open Questions

- [ ] `learning_rate` và `max_iter` của patch: hiệu chỉnh sau khi đo trên laptop (thời gian train có chấp nhận được không).
- [ ] Quy tắc `rule_v1` có đủ che mặt và biển số trên KITTI không (trả lời ở manual check).
