# Requirements: Phase R2 — Backend: insight, mở rộng qua cấu hình, thử nhanh

## Scope

Phase R2 làm phần **backend, worker, attack và ml-core** cho ba mảng việc. Giao diện của cả ba mảng thuộc Phase R3. Demo của R2 chạy qua API và CLI.

1. **Insight và luồng.** Endpoint insight trả điểm yếu chính, ma trận độ bền và câu kết luận. Có template protocol, preset experiment và gợi ý tiêu chí. Experiment mang `mode` (Khám phá/Chính thức), và có thao tác "Nâng lên chính thức".
2. **Mở rộng attack và model qua cấu hình.** Attack spec có trường `adapter`. Catalog có vòng đời: admin tạo, worker tự kiểm tra, reviewer duyệt. Metadata hiển thị nằm ngoài hash. Có adapter model `torchvision_detection` và `onnx`; đăng ký model qua API chỉ nhận ONNX hoặc safetensors.
3. **Thử nhanh.** API nhận một ảnh, một model và một attack, rồi tính mọi level một lần. Kết quả không tạo experiment và giữ 24 giờ.

Thêm vào đó, R2 xử lý tồn đọng của R1: lỗi `ModelProvider.get` trong phép kiểm gradient, giới hạn cache `ModelProvider`, và câu hỏi mở về số luồng torch.

Cuối phase, golden R1 vẫn pass (spec cũ không đổi `spec_sha256`), và mọi test nghiệm thu Phase 0–8 và R1 vẫn pass.

## Out of Scope

- Mọi giao diện, gồm wizard, trang kết quả, admin catalog, đăng ký model và màn hình thử nhanh (Phase R3).
- Thuật toán attack mới. Spec mới chỉ được dùng adapter đã có trong registry (`mission.md` nguyên tắc 10). Corruption hiện có 5 hàm (`fog`, `snow`, `frost`, `motion_blur`, `contrast`); thêm hàm mới (ví dụ `gaussian_noise`) là việc qua repo.
- Upload `.pt` hay pickle qua web. `.pt` vẫn chỉ đăng ký qua CLI.
- Gradient qua ONNX. Model ONNX luôn có `supports_gradients = false`.
- Report PDF có phần insight (xem xét ở R3 hoặc 11c).
- Dataset riêng (Phase 10). Thử nhanh chỉ nhận một ảnh rời, không nhận dataset.
- Máy thuê và ngân sách (Phase 9). Job công cụ chỉ chạy trên máy local.

## Data / Fields

Đổi contract (Group 0, người duyệt). Mọi trường mới thêm vào schema cũ phải tùy chọn, hoặc bị bỏ khỏi JSON khi mang giá trị mặc định, để hash của dữ liệu cũ không đổi.

### Attack spec

```python
class AttackSpecBody:                        # thêm
    adapter: str | None = None               # exclude_if None; None → effective_adapter(kind, art_class)
# fixed_params giữ vai trò tham số của adapter; không thêm adapter_params (Decisions)

class AttackSpecStatus(StrEnum):             # cột mới attack_specs.status, thay is_active
    DRAFT, CHECKING, CHECK_FAILED, PENDING_APPROVAL, ACTIVE, RETIRED

class AttackSpecMetadata:                    # ngoài spec_sha256 (tech-stack mục 9, luật 9)
    display_name: str
    description: LongText
    realism: Literal["low", "medium", "high"]   # mức sát thực tế
    level_labels: dict[str, str]             # level (chuỗi số) → nhãn dễ đọc, ví dụ "1/255" → "rất nhẹ"

class SpecCheckItem:  name: str; passed: bool; details: str | None
class SpecCheckResult: spec_id; items: list[SpecCheckItem]; passed: bool; checked_at; worker_target_id

class AttackSpecCreate:                      # POST /admin/attack-specs
    body: AttackSpecBody                     # name mới (version 1) hoặc name có sẵn (version kế tiếp)
    metadata: AttackSpecMetadata
class AttackAdapterInfo:                     # GET /attack-adapters
    name: str; kind: AttackKind; params_schema: JsonSchema; requires_gradients: bool
```

`AttackSpecAdminView` thêm `status`, `metadata`, `check: SpecCheckResult | None`, `created_by`, `approved_by`. Trường `is_active` suy ra từ `status == active`.

### Model

```python
ModelCard.framework: Literal["ultralytics", "torchvision", "onnx"]
class ModelStatus(StrEnum): CHECKING, CHECK_FAILED, READY     # cột model_versions.status
class ModelUploadCreate: filename: str; size_bytes: PositiveInt    # → presigned PUT, upload_id
class ModelRegister:                         # POST /models
    name: str; framework: Literal["torchvision", "onnx"]
    architecture: str                        # torchvision: danh sách cho phép; onnx: mô tả tự do
    upload_id: UUID; class_names: list[str]; input_size: PositiveInt
```

Danh sách kiến trúc torchvision cho phép là `fasterrcnn_resnet50_fpn_v2`, `retinanet_resnet50_fpn_v2` và `fcos_resnet50_fpn`.

### Insight

```python
class ExperimentMode(StrEnum): EXPLORATION = "exploration"; OFFICIAL = "official"
ExperimentSummary.mode: ExperimentMode       # suy ra: protocol status dev → exploration
ExperimentCreate.promoted_from: UUID | None  # exclude_if None

class Weakness:
    attack_spec_id; attack_name; kind: Literal["grid", "search"]
    level: float; level_ratio: UnitFloat     # level / primary_param.max
    class_name: str | None                   # None: toàn bộ class
    relative_drop: float | None              # grid
    breaking_point: float | None             # search: điểm gãy
class RobustnessCell: band: int; max_relative_drop: float | None; runs: NonNegativeInt
class RobustnessRow:  attack_spec_id; attack_name; cells: list[RobustnessCell]  # đúng 4 ô
class Conclusion:     code: ConclusionCode; params: dict[str, JsonValue]; text: str   # text tiếng Việt
class ExperimentInsight:                     # GET /experiments/{id}/insight
    experiment_id; mode; weaknesses: list[Weakness]   # tối đa 5
    matrix: list[RobustnessRow]; bands: list[tuple[float, float]]   # [(0,.25],(.25,.5],(.5,.75],(.75,1]]
    conclusion: Conclusion; partial: bool
```

### Template và preset

```python
class ProtocolTemplate:                      # contracts/seeds/protocol_templates.json
    key: Literal["quick", "front_camera", "weather", "full"]
    title: str; description: str
    attacks: list[TemplateAttack]            # attack_spec_name, mode, level_ratios hoặc search
    strictness: Literal["lenient", "standard", "strict"]
class ExperimentPreset:                      # contracts/seeds/experiment_presets.json
    key: Literal["fast", "standard", "deep"]
    level_ratios: list[float]                # tỷ lệ trên [min, max] của primary_param
    use_search: bool                         # deep: thêm tìm ngưỡng với attack hỗ trợ
class ExperimentDraftRequest:                # POST /experiments/draft
    protocol_id; preset: str; model_version_id; slice_id; class_mapping_id; compute_target_id
    attack_spec_ids: list[UUID] | None       # chỉ với protocol dev; None → toàn bộ catalog active
# trả ExperimentClone (config + warnings), không tạo experiment
```

### Thử nhanh

```python
class QuickTryCreate:                        # POST /quick-tries (multipart: ảnh + JSON)
    model_version_id; attack_spec_id; preset: str = "standard"
class QuickTryObject:  box: CaseBox; class_name; clean_score; attacked_score | None; status: Literal["kept", "lost", "new"]
class QuickTryLevel:   level; label: str | None; image_url; objects: list[QuickTryObject]
class QuickTryView:
    id; status: Literal["queued", "running", "completed", "failed"]
    not_a_test_result: Literal[True]
    clean_image_url; levels: list[QuickTryLevel]; expires_at; error: str | None
```

### Job công cụ cho worker

```python
class ToolJobKind(StrEnum): SPEC_CHECK, MODEL_CHECK, QUICK_TRY
class ToolLease: kind: ToolJobKind; job_id; lease_id; lease_expires_at
# POST /internal/worker/tool-lease, GET /internal/worker/tool-jobs/{id}, POST .../result
```

### Quyền

- `attack_catalog.approve` dành cho reviewer: duyệt kích hoạt spec.
- `quick_try.use` dành cho engineer và reviewer.
- Đăng ký model dùng `model.manage` (admin), như hiện tại.

### DB (migration `0011_phase_r2`)

- `attack_specs`: thêm `status`, `metadata` (JSONB), `created_by`, `approved_by`, `approved_at`, `check` (JSONB). Spec trong seed được backfill `status = active` (hoặc `retired` nếu `is_active = false`), rồi bỏ cột `is_active`.
- `model_versions`: thêm `status` (backfill `ready`) và `check` (JSONB).
- Bảng mới: `tool_jobs` (kind, payload, status, lease, result, created_by, created_at) và `quick_tries` (id, owner, tool_job_id, input_uri, expires_at, deleted_at).
- `experiments`: thêm `promoted_from`.
- Migration tự `GRANT` quyền cho `advertest_app` trên bảng mới.

## Behaviour

### Insight

- Insight tính từ run đã có metric (`completed`, hoặc `stopped_limit` có `partial`). `partial = true` khi có run `stopped_limit` hoặc experiment chưa xong.
- **Điểm yếu (grid):** với mỗi attack quét lưới, chọn level nhỏ nhất có `relative_drop ≥ 0.3`. Nếu không có level nào đạt, chọn level có `relative_drop` lớn nhất. Lấy thêm class có mức sụt AP50 tương đối lớn nhất tại level đó. Run `skipped` vì `early_stop` lấy theo run kích hoạt, như ranking Phase 6.
- **Điểm yếu (search):** điểm gãy `found` của từng attack tìm ngưỡng.
- Sắp xếp điểm yếu: điểm có `level_ratio` nhỏ hơn đứng trước (gãy sớm hơn thì nghiêm trọng hơn); bằng nhau thì `relative_drop` lớn hơn đứng trước. Giữ tối đa 5. Chỉ đưa vào điểm có `relative_drop ≥ 0.1` hoặc có điểm gãy.
- **Ma trận:** mỗi attack quét lưới một hàng, 4 dải `level_ratio`. Mỗi ô lấy `relative_drop` lớn nhất của các run thuộc dải; dải không có run thì ô là `null`.
- **Câu kết luận:** sinh theo luật, cùng đầu vào cho cùng câu. Các code:
  - `no_data`: chưa run nào có metric.
  - `robust`: không có điểm yếu nào.
  - `weak`: có điểm yếu; câu nêu attack, nhãn level (lấy từ metadata nếu có) và mức sụt của điểm yếu đầu tiên.
  - `weak_class`: như `weak`, nhưng mức sụt của một class lớn gấp đôi toàn bộ trở lên.

  Câu viết sẵn trong backend (`backend/app/insight/phrases.py`) để report sau này dùng chung.
- Ngưỡng 0.3 và 0.1 là hằng số trong code, ghi trong Decisions; không phải tham số của người dùng.

### Mode và nâng lên chính thức

- `mode = exploration` khi và chỉ khi protocol của experiment có status `dev`. Gửi duyệt experiment Khám phá trả 409 như hiện tại (nguyên tắc 11).
- `POST /experiments/{id}/promote {protocol_id}` trả `ExperimentClone`, **không tạo experiment**. Người dùng xem ước lượng rồi mới `POST /experiments` với `promoted_from` (nguyên tắc 5).
  - Experiment nguồn phải có `mode = exploration` và đã kết thúc (`completed`, `stopped_limit` hoặc `cancelled`); protocol đích phải `active`. Sai thì trả 409.
  - Config đích giữ model, slice, class mapping và compute target của nguồn. Attack đích là các attack bắt buộc của protocol, với spec version đang `active`, level bắt buộc, cộng các level nguồn đã chạy cho cùng spec. Attack có ở nguồn mà protocol không yêu cầu vẫn được giữ.
  - Slice nhỏ hơn `min_slice_size` không chặn tạo bản nháp; `warnings` ghi rõ, và compliance sẽ chặn khi gửi duyệt.
- Experiment mới không kế thừa run, kết quả hay verdict nào của experiment nguồn. `promoted_from` chỉ để truy vết và ghi audit log.

### Template, preset, gợi ý tiêu chí

- `GET /protocol-templates` trả 4 template. `GET /protocol-templates/{key}/draft` trả `ProtocolCreate` đã điền: spec version đang `active`, level suy từ `level_ratios`, và tiêu chí gợi ý. Reviewer sửa nếu muốn rồi `POST /protocols` như Phase 8. Template không bao giờ tự tạo protocol.
- **Gợi ý tiêu chí:** mỗi attack quét lưới nhận một `max_drop_at_level` (`relative_drop`) tại level bắt buộc giữa. Ngưỡng theo `strictness`: lenient 0.5, standard 0.3, strict 0.15. Mỗi attack tìm ngưỡng nhận một `min_breaking_point` tại `lo + 0.5·(hi − lo)`. Gợi ý chỉ phụ thuộc template và catalog, **không** phụ thuộc kết quả của experiment nào (nguyên tắc 2).
- `POST /experiments/draft` dựng `ExperimentCreate` từ protocol và preset:
  - Level là `min + r·(max − min)` với từng `r` trong `level_ratios`, làm tròn về `values` gần nhất khi tham số rời rạc, hợp với level bắt buộc của protocol.
  - Preset `deep` thêm tìm ngưỡng cho attack hỗ trợ tìm ngưỡng (không áp cho patch).
  - Seed cố định là 0.
- Template và preset nằm trong `contracts/seeds/`, do người duyệt sửa.

### Catalog attack

- `POST /admin/attack-specs` (`attack_catalog.manage`):
  - `adapter` phải có trong `GET /attack-adapters`, và `fixed_params` phải hợp `params_schema` của adapter (sai trả 422).
  - Spec mới có status `draft`; server tính `id` và `spec_sha256`.
  - Trùng `spec_sha256` với spec đã có trả 409.
  - Name đã có thì version phải đúng bằng version lớn nhất cộng 1.
- Tạo xong thì backend xếp một job `spec_check`, và spec chuyển `checking`. Kết quả pass chuyển `pending_approval`, fail chuyển `check_failed`. Admin có thể chạy lại kiểm tra từ `check_failed`.
- `POST /attack-specs/{id}/approve` (`attack_catalog.approve`):
  - Chỉ từ `pending_approval`.
  - Người duyệt phải khác người tạo (403 nếu trùng; nguyên tắc 1).
  - Spec chuyển `active`. Version cũ cùng name đang `active` chuyển `retired` trong cùng giao dịch.
- `POST /attack-specs/{id}/reject {reason}` chuyển spec về `draft`. Spec đã `active` không sửa được; muốn đổi thì tạo version mới.
- `PATCH /admin/attack-specs/{id}/metadata` sửa metadata, không đổi `spec_sha256` hay version, có ghi audit log (luật 9).
- `GET /attack-specs` (cho engineer) chỉ trả spec `active`, kèm metadata. Experiment, protocol và preset chỉ được dùng spec `active` (422 nếu không). Experiment cũ đã chốt spec `retired` vẫn đọc được và chạy lại được.
- Bộ registry của worker (`attacks/builders.py`) đọc `spec.adapter` trước, rồi mới tới `effective_adapter`. Mọi spec trong seed giữ `adapter = None` nên `spec_sha256` không đổi.

### Tự kiểm tra spec (`attacks/selfcheck.py`, worker chạy trên ảnh fixture)

Mỗi mục là một `SpecCheckItem`:

1. **Chạy được:** `build` và `apply` không lỗi tại `min`, `max` và giữa dải, trên model fixture (YOLO).
2. **Giá trị:** ảnh ra là `float32` thuộc [0, 1], đúng shape đầu vào.
3. **Vùng pad:** điểm ảnh có `mask = 0` giữ nguyên tuyệt đối.
4. **Không biến đổi:** level ứng với "không biến đổi" (`min` khi `min = 0`) cho ảnh y hệt đầu vào. Bỏ qua mục này (ghi `passed` kèm lý do) khi `min > 0`.
5. **Batch:** kết quả chạy với batch 1 và batch 4 khớp nhau (sai số `1e-6` với attack ART, tuyệt đối với corruption và occlusion), cùng seed.
6. **Chuẩn nhiễu:** với `kind = attack`, `‖x' − x‖` theo `norm` ≤ eps khai báo (+1e-6). Không áp với kind khác.
7. **Tất định:** chạy hai lần cùng seed cho ảnh giống hệt.

Kiểm tra chạy trên CPU với torch 1 luồng, có giới hạn thời gian 120 giây; quá giờ thì `check_failed`.

### Model qua web

- `POST /models/uploads`:
  - Nhận phần mở rộng `.onnx` hoặc `.safetensors` và tối đa 500 MB; trả presigned PUT URL.
  - Kiểm tra nội dung sau khi upload: safetensors thì header JSON hợp lệ; onnx thì protobuf `ModelProto` đọc được ở worker.
  - File khác, gồm pickle, zip và `.pt`, trả 422 (nguyên tắc 10).
- `POST /models`:
  - Tạo `model_versions` với status `checking`, `id = content_id(weights_sha256)`. Trùng sha trả 409.
  - Xếp job `model_check`. Job này nạp model, so sha256, chạy inference trên fixture, kiểm số class khớp `class_names`, và chạy kiểm gradient (chỉ torchvision).
  - Kết quả pass chuyển `ready`, fail chuyển `check_failed` kèm lý do.
- Chỉ model `ready` được dùng trong experiment và thử nhanh.
- Adapter `torchvision_detection` (`ml_core/models/`):
  - Dựng kiến trúc trong danh sách cho phép, `weights=None`, rồi nạp state dict bằng `safetensors.torch.load_file`.
  - Có estimator ART cho gradient (`PyTorchFasterRCNN` hoặc estimator object detection tương ứng).
  - Ảnh vào theo quy ước mục 2.1 (letterbox 640, [0, 1]). Box ra là `xyxy` trong không gian letterbox.
- Adapter `onnx`:
  - Chạy `onnxruntime` CPU (hoặc CUDA nếu có). Đầu ra phải theo một trong hai layout được khai báo: kiểu YOLO `(1, 4+C, N)` hoặc kiểu `boxes/scores/labels`.
  - `capabilities.gradients = false`.
  - NMS dùng chung với Ultralytics adapter nếu đầu ra chưa NMS.
- `ModelProvider`:
  - Cache LRU tối đa 2 model.
  - Lỗi nạp model trong phép kiểm gradient của worker (`job.py`, tồn đọng R1 Group 5) chỉ làm các run cần gradient `failed` (`error`); run khác vẫn chạy.

### Thử nhanh

- `POST /quick-tries` (`quick_try.use`):
  - Nhận ảnh JPEG/PNG tối đa 10 MB, cạnh dài tối đa 4096 px; model `ready` và spec `active`.
  - Spec cần train (patch) hoặc model ONNX gặp attack cần gradient trả 422.
  - Mỗi người tối đa 1 lượt `queued`/`running` (429 nếu vượt).
- Level lấy theo preset (mặc định `standard`). Worker tính mọi level trong một job, rồi lưu ảnh đã làm mờ mặt và biển số (pipeline Phase 6) cùng bảng object.
- Bảng object ghép theo IoU ≥ 0.5 cùng class:
  - object sạch không còn ghép được là `lost`;
  - object chỉ có trên ảnh bị tấn công là `new`;
  - còn lại là `kept`.
- Response luôn có `not_a_test_result = true`. Thử nhanh không tạo experiment, run hay failure case, không vào report hay ranking. Audit log ghi `quick_try.create`.
- Hết 24 giờ, job dọn dẹp (backend, chạy định kỳ) xóa ảnh gốc, ảnh kết quả và đặt `deleted_at`; `GET` sau đó trả 410. Ảnh gốc chưa làm mờ không bao giờ được phục vụ qua API.
- Mục tiêu thời gian: dưới 10 giây với 5 level của corruption hoặc FGSM trên CPU laptop, khi model đã nằm trong cache.

### Job công cụ

- Worker có thêm chế độ `advertest-worker --tools`, là một process riêng chỉ lease job công cụ. Nhờ vậy thử nhanh không phải chờ sau experiment đang chạy.
- Lease, heartbeat và hết hạn lease theo cùng luật của experiment (`tech-stack.md` mục 4). Job mất lease được xếp lại tối đa 2 lần, rồi `failed`.
- Thứ tự lease: `quick_try` trước, rồi `model_check` và `spec_check`, mỗi loại theo thứ tự tạo.
- Worker ghi kết quả qua endpoint `/internal/worker/tool-jobs/{id}/result`; chỉ token worker ghi được (nguyên tắc 3).

## Decisions

- **R2 chỉ làm backend; mọi giao diện thuộc R3.** *Lý do:* gộp phase ngày 2026-10-09; giao diện cơ bản đã có. Người dùng chốt 2026-10-09.
- **R2 làm trước Phase 10.** *Lý do:* R2 không phụ thuộc dataset riêng. Người dùng chốt 2026-10-09.
- **`fixed_params` là tham số của adapter; không thêm `adapter_params`**. *Lý do:* hai chỗ chứa tham số dễ lệch nhau; giữ `fixed_params` thì hash của spec cũ không đổi. Người dùng chốt 2026-10-09.
- **Câu kết luận sinh ở backend, kèm `code` và `params`**. *Lý do:* report sau này dùng cùng câu; frontend vẫn có thể tự dựng câu từ `code` nếu cần. Người dùng chốt 2026-10-09.
- **"Nâng lên chính thức" chỉ trả bản nháp**. *Lý do:* nguyên tắc 5 (người dùng phải thấy ước lượng trước khi chạy), và đi cùng luồng nhân bản Phase 5. Người dùng chốt 2026-10-09.
- **Job công cụ chạy trên một process worker riêng (`--tools`)**. *Lý do:* experiment dài sẽ chặn thử nhanh nếu dùng chung hàng đợi; vẫn dùng chung code và image. Người dùng chốt 2026-10-09.
- **Ngưỡng điểm yếu 0.3, ngưỡng hiển thị 0.1, 4 dải cường độ.** *Lý do:* 0.3 khớp ngưỡng `standard` của gợi ý tiêu chí. Người dùng chốt 2026-10-09.
- **Torchvision cho phép 3 kiến trúc** (`fasterrcnn_resnet50_fpn_v2`, `retinanet_resnet50_fpn_v2`, `fcos_resnet50_fpn`). Người dùng chốt 2026-10-09.
- **Giới hạn vận hành:** upload model ≤ 500 MB, tự kiểm tra spec ≤ 120 giây, cache `ModelProvider` LRU 2 model, thử nhanh < 10 giây trên CPU khi model đã cache; chỉnh lại sau khi đo ở Group 5. Người dùng chốt 2026-10-09.
- **Tên nhánh `phaser2-<agent>`, test ở `tests/acceptance/phase_r2/`; merge vào `dev`.** *Lý do:* như R1.

## Context

- `mission.md` nguyên tắc 1, 2, 3, 5, 9, 10, 11; `tech-stack.md` mục 3, 4, 9 (luật 8, 9) và mục 10 (dependency `onnxruntime`, `safetensors` chờ duyệt và pin).
- R1 đã có `PerturbationRegistry` (resolver tiêm được), `ModelAdapter`/`ModelProvider` và `ErrorPolicy`. `ModelProvider.get` báo `ValueError` với framework khác `ultralytics` (Decisions R1).
- Ranking Phase 6 (`ml_core/metrics/ranking.py`) đã chuẩn hóa level theo `primary_param.max`; insight dùng lại cách này.
- Protocol `dev-open` được seed ở migration 0002 (`backend/app/services/experiments.py:34`).
- `attack_specs.is_active` và `GET /admin/attack-specs` đã có từ Phase 6.

## Open Questions

- [ ] (Từ R1) Số luồng torch và loại lõi CPU (P/E) ảnh hưởng tới failure case của PGD nhưng không có trong fingerprint hay `Environment`. Các phương án: ghi số luồng vào `Environment` (đổi contract), để runner tự ghim, hoặc chấp nhận như hiện tại. Cần quyết trước khi chạy experiment chính thức trên nhiều máy.
- [ ] Layout đầu ra ONNX: hai layout ở trên có đủ cho model người dùng dự kiến đăng ký không?
