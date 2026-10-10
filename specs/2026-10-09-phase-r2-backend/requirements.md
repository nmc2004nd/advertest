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
class QuickTryCreate:                        # POST /quick-tries (multipart: field theo QuickTryCreate + file image)
    model_version_id; attack_spec_id; preset: str = "standard"
class QuickTryObject:  bbox: PixelBBox; class_name; clean_score | None; attacked_score | None; status: QuickTryObjectStatus  # kept | lost | new
class QuickTryLevel:   level; label: str | None; image_url; objects: list[QuickTryObject]
class QuickTryView:
    id; status: ToolJobStatus
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

### Chốt ở Group 0 (2026-10-09)

Chi tiết contract (nguồn sự thật: `contracts/python/advertest_contracts/models.py`, mock trong `contracts/mocks/`, seed trong `contracts/seeds/`):

- **Attack spec.** `adapter` có dạng `a.b[.c]` (`AdapterName`). `SpecCheckItem.name` là enum `SpecCheckName`, gồm 7 mục theo thứ tự ở mục Tự kiểm tra spec. `SpecCheckResult` thêm `error` cho trường hợp quá 120 giây hoặc lỗi ngoài các mục; khi đó `items` có thể thiếu. `passed = true` khi và chỉ khi đủ 7 mục, mọi mục pass và không có `error`. Mục bỏ qua thì ghi `passed = true` kèm `details`.
- **Metadata.** Khóa của `level_labels` so khớp theo giá trị số, nên `"1"` và `"1.0"` là cùng một level, không được trùng. Spec seed chưa có metadata nên `metadata = null`. `GET /attack-specs` trả `AttackSpecView` (là `AttackSpec` cộng `metadata`).
- **Endpoint catalog bổ sung.**
  - `GET /attack-specs/pending` (`attack_catalog.approve`) cho reviewer xem spec chờ duyệt, vì `GET /admin/attack-specs` chỉ dành cho admin.
  - `POST /admin/attack-specs/{id}/check` chạy lại kiểm tra từ `check_failed`.
  - `POST /attack-specs/{id}/reject` nhận `AttackSpecReject {reason}`.
- **Model.**
  - `ModelSummary` thêm `status` (mặc định `ready`) và `check: ModelCheckResult | None`.
  - `POST /models/uploads` trả `ModelUpload {upload_id, url, expires_at}`.
  - `ModelUploadCreate` chặn ngay ở schema phần mở rộng khác `.onnx`/`.safetensors` và file quá 500 MB.
  - `ModelCard` với `framework = onnx` không được có `supports_gradients = true`.
- **Insight.**
  - `Weakness` thêm `level_label` (lấy từ metadata) và `class_relative_drop`, mức sụt của `class_name` dùng để xét `weak_class`.
  - Ô của ma trận có `max_relative_drop = null` khi và chỉ khi `runs = 0`.
  - `conclusion.code = robust` khi và chỉ khi có dữ liệu mà không có điểm yếu.
  - Hằng số nằm ở `models.py`: `WEAKNESS_DROP`, `WEAKNESS_VISIBLE_DROP`, `MAX_WEAKNESSES`, `ROBUSTNESS_BANDS`.
- **Bản nháp.** `ExperimentClone` thêm `notes: list[DraftNote]`, hiện có một code là `slice_too_small`. `CloneWarning` vẫn chỉ dùng khi đổi version spec. `promote` và `draft` đều trả `ExperimentClone`.
- **Template.** `TemplateAttack` dùng `grid.level_ratios` hoặc `search {threshold_kind, threshold, lo_ratio, hi_ratio, max_tol_ratio}`. `ProtocolTemplate` thêm `min_slice_size`, và `title` được dùng làm tên protocol của bản nháp. Cách tính khi dựng bản nháp:
  - Level là `round(min + r·(max − min), 6)`. Tham số rời rạc thì lấy giá trị gần nhất trong `values` (hòa thì lấy giá trị nhỏ hơn), rồi bỏ level trùng.
  - `max_tol = max_tol_ratio · (hi − lo)`.
  - "Level bắt buộc giữa" của tiêu chí là phần tử thứ `(n − 1) // 2` của danh sách level bắt buộc đã sắp xếp.
  - Tiêu chí dùng `threshold_kind = relative_drop` và `class_filter = null`. Tiêu chí của attack tìm ngưỡng dùng cùng ngưỡng với cấu hình tìm ngưỡng.
- **Preset.**
  - `ExperimentPreset` thêm `title`, `description` và `search: PresetSearch {threshold_kind, threshold, subset_size}`; `search` có khi và chỉ khi `use_search`.
  - Dải tìm ngưỡng là `[min, max]` của spec, `tol = (hi − lo) / 256` như wizard.
  - `deep` chạy tìm ngưỡng thay cho quét lưới, như mục Template, preset, gợi ý tiêu chí. Người dùng chốt 2026-10-09.
  - `ExperimentDraftRequest` thêm `limit`, vì `ExperimentCreate` bắt buộc trường này. `preset` là `Literal["fast", "standard", "deep"]`.
- **Thử nhanh.**
  - `POST /quick-tries` nhận multipart: các field của `QuickTryCreate` cộng file `image`. Cần dependency `python-multipart`; người dùng chốt 2026-10-09.
  - Ảnh trả về là `ArtifactUrl` (`/artifacts/<token>`), như ảnh failure case.
  - `QuickTryObject.bbox` là `PixelBBox`, không dùng `CaseBox` để khỏi lặp class và score. `clean_score = null` khi và chỉ khi `new`; `attacked_score = null` khi và chỉ khi `lost`.
  - `QuickTryView` thêm `model_version_id`, `attack_spec_id`, `preset`, `created_at`; `status` dùng `ToolJobStatus`.
  - Mã lỗi mới: `quick_try_busy` (429) và `gone` (410).
- **Job công cụ.**
  - `GET /internal/worker/tool-jobs/{id}` trả `ToolJobBundle`, trong đó `payload` là một trong `SpecCheckPayload`, `ModelCheckPayload`, `QuickTryPayload`, phân biệt theo `kind`. Payload thử nhanh gồm URL tải ảnh gốc và các presigned PUT cho ảnh đã làm mờ.
  - `POST /internal/worker/tool-jobs/{id}/heartbeat {lease_id}` trả 204, hoặc 409 khi đã mất lease.
  - `POST .../result` nhận `ToolJobResult`: đúng một trong `report` hoặc `error`. Kiểm tra fail vẫn gửi `report` với `passed = false`; `error` dành cho lỗi hạ tầng.
- **Danh sách experiment.** `GET /experiments` có tham số `?mode=`. Từ Group 0, `ExperimentSummary.mode` đã được suy từ status của protocol.
- **Fixture.** `scripts/make_r2_fixtures.py` sinh fixture một lần qua `uv run --with onnx`; gói `onnx` không vào lock. Fixture gồm `yolov8n.onnx` (từ `yolov8n.pt`) và `fcos_resnet50_fpn_coco.safetensors` (weights COCO của torchvision). Người duyệt upload lên release `fixtures-v2`; sha256 ghi trong `tests/fixtures/checksums.json`.
- **Bản nháp experiment (bổ sung khi viết test).**
  - `POST /experiments` đã kiểm compliance ngay lúc tạo (Phase 8). Vì vậy bản nháp có slice nhỏ hơn `min_slice_size` vẫn dựng được và ghi `notes`, nhưng tạo experiment từ nó bị chặn với 422 `not_compliant`. Mục Mode và nâng lên chính thức ghi "chặn khi gửi duyệt"; câu đó được hiểu theo hành vi hiện có này.
  - `ExperimentDraftRequest` thêm `training_slice_id`. Khi `attack_spec_ids = null`, bản nháp gồm toàn bộ catalog `active` trừ spec cần train. Chọn rõ spec cần train, hoặc protocol bắt buộc spec đó, thì phải có `training_slice_id`; thiếu thì 422.
  - Tìm ngưỡng của preset dùng `subset_size = min(preset.search.subset_size, số ảnh của slice)`.
- **Câu kết luận.** Mức sụt trong `text` viết dạng phần trăm, làm tròn số nguyên (0.42 → "42%"). `weak_class` áp dụng khi `class_relative_drop ≥ 2 · relative_drop`, tính cả trường hợp bằng đúng 2 lần.
- **Audit log.** Các action mới: `attack_spec.created`, `attack_spec.approved`, `attack_spec.rejected`, `attack_spec.metadata_updated`, `model.registered`, `experiment.promoted` (với `after.promoted_from`) và `quick_try.create`.
- **Lưu trữ thử nhanh.** Mọi object của một lượt nằm dưới `quick-tries/<id>/` trong bucket `artifacts`.
- **Job công cụ.** Job mất lease được xếp lại; sau lần mất lease thứ 3 thì `failed`. Khi đó spec chuyển `check_failed`, model chuyển `check_failed`, thử nhanh chuyển `failed` kèm `error`. Heartbeat bằng lease cũ trả 409.

#### Bổ sung sau review Group 0 (2026-10-09)

- **Quyền của endpoint mới** (`x-permission` trong `contracts/openapi.json`, test `test_permissions_r2.py`):

  | Endpoint | Permission |
  |---|---|
  | `GET /experiments/{id}/insight`, `GET /experiment-presets` | `experiment.read` |
  | `POST /experiments/{id}/promote`, `POST /experiments/draft` | `experiment.create` |
  | `GET /protocol-templates` | `protocol.read` |
  | `GET /protocol-templates/{key}/draft` | `protocol.manage` |
  | `GET /attack-adapters`, `POST /admin/attack-specs`, `POST /admin/attack-specs/{id}/check`, `PATCH /admin/attack-specs/{id}/metadata` | `attack_catalog.manage` |
  | `GET /attack-specs/pending`, `POST /attack-specs/{id}/approve`, `POST /attack-specs/{id}/reject` | `attack_catalog.approve` |
  | `POST /models/uploads`, `POST /models` | `model.manage` |
  | `POST /quick-tries`, `GET /quick-tries/{id}` | `quick_try.use` |

  Endpoint `/internal/worker/tool-*` dùng token worker, không có `x-permission` (nguyên tắc 3).
- **Thử nhanh chỉ người tạo xem được.** Người khác, kể cả có `quick_try.use`, gọi `GET /quick-tries/{id}` nhận 404.
- **Thời hạn của job công cụ.** Lease 60 giây, mỗi heartbeat gia hạn thêm 60 giây. Presigned URL trong `ToolJobBundle` hết hạn sau 15 phút.
- **Câu kết luận khi điểm yếu đầu tiên là `search`.** Điểm yếu tìm ngưỡng có `relative_drop = null`, nên `text` nêu attack và điểm gãy (`breaking_point`, kèm `level_label` nếu có) thay cho mức sụt. Code là `weak`; `weak_class` chỉ xét điểm yếu quét lưới.

#### Interface cho test nghiệm thu (`tests/acceptance/phase_r2/`)

Test gọi trực tiếp các tên dưới đây. Đổi tên hoặc chữ ký thì phải qua người duyệt.

- **Group 1.** `backend.app.insight.phrases.conclude(weaknesses, *, has_data) -> Conclusion` là hàm thuần.
- **Group 2.** Trong `attacks.builders`:
  - `adapter_of(spec) -> str` trả `spec.adapter`, hoặc `effective_adapter(spec)` khi `adapter` là null. Đây là resolver mặc định của `PerturbationRegistry`.
  - `InvalidSpec(ValueError)`.
  - `PerturbationRegistry.validate(spec)` báo `InvalidSpec` khi adapter không có trong registry, khi `kind` khác `kind` của builder, hoặc khi `fixed_params` sai `params_schema`.
  - `PerturbationRegistry.adapters() -> list[AttackAdapterInfo]`, sắp theo tên.
  - Builder có thêm `kind: ClassVar[AttackKind]` và `params_schema: ClassVar[dict]`. Builder thiếu hai thuộc tính này, như builder giả của test R1, vẫn đăng ký và dựng được.
  - Schema của `corruption.imagecorruptions` có `properties.corruption.enum` là đúng 5 hàm hiện có.
- **Group 2.** Trong `attacks.selfcheck`:
  - `SelfcheckInputs(images, masks, targets, estimator)` với 4 ảnh letterbox; `estimator` là null khi không cần gradient.
  - `run_selfcheck(spec, inputs, *, registry=DEFAULT_REGISTRY, seed=0, timeout_s=120.0)` trả object có `items: list[SpecCheckItem]` và `error: str | None`.
  - Level dùng cho từng mục:
    - Mục 1 chạy tại `min`, level giữa và `max`.
    - Mục 4 chạy tại `min`.
    - Các mục còn lại chạy tại level giữa: `min + 0.5·(max − min)`; tham số rời rạc thì lấy `values[(n − 1) // 2]`.
  - Mục 5 so batch 1 với batch 4 trên cùng một perturbation. Mục 7 so hai perturbation dựng độc lập.
  - Chuẩn nhiễu tính bằng `level_to_eps` và `fixed_params.norm`.
  - Spec cần train thì dùng patch ngẫu nhiên có seed cố định.
- **Group 3.** Trong `ml_core.models.adapter`:
  - `open_adapter(card, weights: Path, params, device) -> ModelAdapter`, chọn adapter theo `framework`.
  - `ModelProvider(store, *, load_model=None, max_models=2)` cache LRU theo khóa hiện có.
  - Fixture torchvision có tên class trùng (`N/A`); test đánh số các tên trùng để thỏa ràng buộc không trùng.
- **Group 4.** `backend.app.services.quick_tries.purge_expired(session, buckets, now) -> int` trả số lượt đã dọn. Cách gọi định kỳ (CLI hoặc tiến trình nền) do Group 4 chọn.
- **Group 5.** `advertest_worker.tools.ToolRunner(client, cache, device, *, url_http, clock)` có `run_next() -> bool`, trả false khi không còn job. `advertest-worker --tools` lặp `run_next`.

Test của group chưa làm chỉ có trên nhánh `phaser2-reviewer`. Test gọi interface mới qua import trong thân hàm, nên khi interface chưa có thì từng test fail riêng, không chặn cả lượt chạy.

### Chốt ở Group 1 (2026-10-09)

Quyết định sau review Group 1 (`.claude/handoff/phaser2-g1-review.md`):
- **Run trúng cache có trong insight.** Run `skipped` vì `cached` mang metric chép từ run gốc, nên được tính như run đã chạy: ở `has_data`, điểm yếu và ma trận.
- **Ô ma trận của level dừng sớm.** Level `skipped` vì `early_stop` lấy `relative_drop` của run kích hoạt (`status_reason.trigger_run_id`), như ranking Phase 6, và được đếm vào `runs` của ô. Ô chỉ `null` khi dải không có level nào.
- **Kiểm `promoted_from`.** `POST /experiments` với `promoted_from` trỏ tới experiment không phải Khám phá, hoặc chưa kết thúc, trả 422 và không ghi audit `experiment.promoted`. Experiment không tồn tại cũng trả 422.
- **Nguồn "đã kết thúc"** là experiment `completed` hoặc `cancelled`. `stopped_limit` là trạng thái của run, không phải của experiment.
- **Version attack bắt buộc.** `promote` dùng spec version mà protocol ghim trong `required_attacks`, không phải version đang `active`. Nếu version đó đã `retired`, bản nháp vẫn dựng được, còn `POST /experiments` trả 422.
- **Protocol không `active`.** `POST /experiments/draft` với protocol `draft` hoặc `retired` trả 409. Gửi `attack_spec_ids` kèm protocol không phải `dev` trả 422.
- **`training_slice_id`.** `promote` không tự điền `training_slice_id` cho attack bắt buộc cần train mà nguồn không có. Người dùng phải điền; nếu thiếu thì lỗi hiện ở `POST /experiments`.
- **Attack bắt buộc tìm ngưỡng** trong bản nháp: `tol = min((hi − lo)/256, max_tol)`, `bootstrap = max(200, min_bootstrap)`.
- **Thứ tự điểm yếu.** Khi cùng `level_ratio` và cùng mức sụt, điểm gãy (`relative_drop = null`) xếp sau điểm quét lưới.
- **`level_label`** luôn `null` cho tới Group 4 (cột `attack_specs.metadata`). Group 4 nối nhãn vào insight; validation Group 4 kiểm nhãn trong insight.
- **Migration tách đôi.** `0011` (Group 1) chỉ thêm `experiments.promoted_from`; phần DB còn lại của R2 ở `0012` (Group 4).

### Chốt ở Group 4 (2026-10-10)

Quyết định sau review Group 4 (`.claude/handoff/phaser2-g4-review.md`, lượt 1 và 2):
- **Cột thêm ngoài mục DB.** `quick_tries` thêm `model_version_id`, `attack_spec_id`, `preset`, `created_at`. `tool_jobs` thêm `attempts`, `leased_by`, `error`, `finished_at`. ORM giữ `is_active` dạng hybrid, suy ra từ `status`.
- **`architecture` của model web** nằm trong payload job `model_check` rồi ghi vào `card.json` khi check pass. Không thêm cột.
- **Status mặc định** cho bản ghi chèn qua seed hoặc CLI: spec `active`, model `ready`.
- **Dọn thử nhanh** là vòng lặp nền 10 phút trong lifespan của API (chỉ khi có `MINIO_ENDPOINT`), kèm lệnh `advertest-admin purge-quick-tries`.
- **Thiếu cấu hình MinIO.** Mọi endpoint dùng storage, kể cả endpoint worker, trả 500 `internal_error`; chi tiết chỉ ghi log. Kiểm quyền chạy trước nên 401/403 không đổi. Lỗi 500 này trả trước lỗi 422 của body, vì FastAPI giải dependency trước khi kiểm body; chỉ xảy ra khi máy chủ cấu hình sai.
- **Job công cụ lease toàn cục**, chỉ target `local` nhận; target khác (máy thuê) nhận 204.
- **Spec bị reject về `draft` là ngõ cụt.** Không chạy lại kiểm tra được (`recheck` chỉ nhận `check_failed`), gửi lại cùng nội dung trả 409 vì trùng sha, và version đó vẫn bị chiếm. Muốn tiếp thì tạo version kế tiếp.
- **Model `check_failed` không kiểm lại được** trong R2: không có endpoint recheck, upload lại cùng file trả 409 vì trùng sha. Recheck model để R3 hoặc sau. Người dùng chốt 2026-10-10.
- **`card.json.lib_versions` lấy theo môi trường của API**, không theo worker đã kiểm model. Hiện khớp vì dùng chung image; sẽ lệch khi tách image hoặc dùng máy thuê (nguyên tắc tái lập). Người dùng chốt 2026-10-10.
- **Rủi ro object mồ côi trong MinIO** (chấp nhận, dọn ở G5 hoặc R3): ảnh gốc chưa làm mờ được `put` trước khi commit, nên transaction lỗi sau đó để lại ảnh không có dòng `quick_tries`; presigned PUT sống 15 phút nên worker vẫn PUT được ảnh kết quả (đã làm mờ) sau khi purge xóa prefix. Cách dọn: lọc theo tuổi các object `quick-tries/` không có dòng tương ứng. Người dùng chốt 2026-10-10.
- **Job mất lease lần 3 chỉ bị chốt `failed` khi có worker gọi lease**, như luật lease của experiment. Không có worker `--tools` nào thì spec, model hay lượt thử nhanh nằm ở `checking`/`running`, và người dùng bị 429 tới khi purge chạy (24 giờ).
- **Thử nhanh từ chối mọi model `supports_gradients = false` gặp attack cần gradient** (422), không chỉ ONNX; ví dụ model torchvision có kiểm gradient fail.

### Chốt ở Group 2 (2026-10-10)

Quyết định ghi lại sau review cả phase (`.claude/handoff/phaser2-review.md`):
- **Mục 5 `batch_invariant` của selfcheck.** Với attack dùng gradient (FGSM/PGD), mục 5 chỉ kiểm batch 1 hợp lệ (giá trị, pad, chuẩn nhiễu) và ghi độ lệch vào `details`, không so sai số 1e-6. Mọi builder khác so tuyệt đối. Thay cho câu "sai số 1e-6 với attack ART" ở Behaviour "Tự kiểm tra spec". Docstring `_spec` trong `test_selfcheck.py` cần sửa theo.
- **Schema `art.evasion`:** `norm` ∈ {`"inf"`, `2`}, cùng `max_iter`, `eps_step_ratio`, `num_random_init`. Cả 4 builder dùng `additionalProperties: false`. Bộ kiểm JSON Schema tự viết (`jsonschema` không có trong tech-stack). Builder thiếu `kind` hoặc `params_schema` không được liệt kê.
- **Giới hạn 120 s của selfcheck là hợp tác**, chỉ kiểm giữa các bước; cắt cứng thuộc về worker (xem Chốt ở Group 5). CLI selfcheck chỉ import `ml_core` trong `main`.
- **`validate` không kiểm `art_class`** thuộc lớp ART được hỗ trợ: tạo spec vẫn 201, lỗi lộ ra ở mục 1 của selfcheck và spec chuyển `check_failed`. Để R3 hoặc backlog.

### Chốt ở Group 3 (2026-10-10)

- **Kiểm gradient torchvision không đạt** thì model vẫn `ready`, với `supports_gradients = false`.
- **Torchvision resize** đặt min = max = 640.
- **Layout ONNX** nhận tự động theo tên và shape đầu ra; đầu ra `boxes/scores/labels` coi là đã qua NMS.
- **Chữ ký `check_model`:** `check_model(card, weights_path, *, worker_target_id, device="cpu", params=DEFAULT_INFERENCE_PARAMS, images=None) -> ModelCheckResult`. Lỗi của model trả trong kết quả, không ném ra; `images` mặc định là ảnh fixture KITTI.
- **`TorchvisionDetector` bỏ box suy biến** khi tính loss.

### Chốt ở Group 5 (2026-10-10)

Quyết định sau review cả phase (`.claude/handoff/phaser2-review.md`); người dùng chốt 2026-10-10:
- **`worker_target_id` do API ghi** theo target đã lease (`job.leased_by`); worker gửi UUID 0.
- **Nhãn của thử nhanh.** Không có ground truth, nên prediction sạch có score ≥ `operating_conf` được dùng làm nhãn; bảng object cũng chỉ xét detection ≥ `operating_conf`.
- **Giới hạn làm mờ của thử nhanh (chấp nhận).** Vùng làm mờ `rule_v1` chỉ lấy từ detection có score ≥ `operating_conf`. Người hay xe mà model bỏ sót ở cả ảnh sạch lẫn ảnh tấn công sẽ không bị làm mờ trong ảnh phục vụ qua URL (nguyên tắc 9). R3 cân nhắc làm mờ rộng hơn.
- **Card của worker công cụ** đặt `supports_gradients = framework != onnx`.
- **Cắt cứng `spec_check`.** Spec chạy trong tiến trình con. Thời gian nạp tối đa 300 s, không tính vào 120 s; nạp lỗi là lỗi hạ tầng. Quá 120 + 15 s thì giết tiến trình, kết quả có `items` rỗng kèm `error`. Tiến trình con chết sau khi báo `ready` (OOM, segfault) tính là spec `check_failed`, không phải lỗi hạ tầng.
- **Worker `--tools` chưa có trong Docker.** `docker/compose.yaml` chưa có service `advertest-worker --tools`, và image worker không chứa `tests/fixtures` mà `spec_check` cần. Demo R2 chạy worker `--tools` ngoài Docker; service và fixture trong image để R3.
- **Backlog R3:** gộp phần dựng fixture của `backend/worker/advertest_worker/spec_check.py` với `attacks/selfcheck.py` qua một hàm công khai (`fixture_inputs(with_estimator=)`), để CLI selfcheck và worker kiểm trên cùng đầu vào.

### DB (migration `0011` của Group 1 và `0012` của Group 4)

- `attack_specs`: thêm `status`, `metadata` (JSONB), `created_by`, `approved_by`, `approved_at`, `check` (JSONB). Spec trong seed được backfill `status = active` (hoặc `retired` nếu `is_active = false`), rồi bỏ cột `is_active`.
- `model_versions`: thêm `status` (backfill `ready`) và `check` (JSONB).
- Bảng mới: `tool_jobs` (kind, payload, status, lease, result, created_by, created_at) và `quick_tries` (id, owner, tool_job_id, input_uri, expires_at, deleted_at). Cột thêm: xem Chốt ở Group 4.
- `experiments`: thêm `promoted_from` (migration `0011`, Group 1). Các thay đổi khác trong mục này ở migration `0012` (Group 4).
- Migration tự `GRANT` quyền cho `advertest_app` trên bảng mới.

## Behaviour

### Insight

- Insight tính từ run đã có metric: `completed`, `stopped_limit` có `partial`, và `skipped` vì `cached` (metric chép từ run gốc). `partial = true` khi có run `stopped_limit` hoặc experiment chưa xong.
- **Điểm yếu (grid):** với mỗi attack quét lưới, chọn level nhỏ nhất có `relative_drop ≥ 0.3`. Nếu không có level nào đạt, chọn level có `relative_drop` lớn nhất. Lấy thêm class có mức sụt AP50 tương đối lớn nhất tại level đó. Run `skipped` vì `early_stop` lấy theo run kích hoạt, như ranking Phase 6.
- **Điểm yếu (search):** điểm gãy `found` của từng attack tìm ngưỡng.
- Sắp xếp điểm yếu: điểm có `level_ratio` nhỏ hơn đứng trước (gãy sớm hơn thì nghiêm trọng hơn); bằng nhau thì `relative_drop` lớn hơn đứng trước, điểm gãy xếp sau điểm quét lưới. Giữ tối đa 5. Chỉ đưa vào điểm có `relative_drop ≥ 0.1` hoặc có điểm gãy.
- **Ma trận:** mỗi attack quét lưới một hàng, 4 dải `level_ratio`. Mỗi ô lấy `relative_drop` lớn nhất của các run thuộc dải; level `skipped` vì `early_stop` lấy mức sụt của run kích hoạt. Dải không có level nào thì ô là `null`.
- **Câu kết luận:** sinh theo luật, cùng đầu vào cho cùng câu. Các code:
  - `no_data`: chưa run nào có metric.
  - `robust`: không có điểm yếu nào.
  - `weak`: có điểm yếu; câu nêu attack, nhãn level (lấy từ metadata nếu có) và mức sụt của điểm yếu đầu tiên (điểm yếu `search` thì nêu điểm gãy thay cho mức sụt).
  - `weak_class`: như `weak`, nhưng mức sụt của một class lớn gấp đôi toàn bộ trở lên.

  Câu viết sẵn trong backend (`backend/app/insight/phrases.py`) để report sau này dùng chung.
- Ngưỡng 0.3 và 0.1 là hằng số trong code, ghi trong Decisions; không phải tham số của người dùng.

### Mode và nâng lên chính thức

- `mode = exploration` khi và chỉ khi protocol của experiment có status `dev`. Gửi duyệt experiment Khám phá trả 409 như hiện tại (nguyên tắc 11).
- `POST /experiments/{id}/promote {protocol_id}` trả `ExperimentClone`, **không tạo experiment**. Người dùng xem ước lượng rồi mới `POST /experiments` với `promoted_from` (nguyên tắc 5).
  - Experiment nguồn phải có `mode = exploration` và đã kết thúc (`completed` hoặc `cancelled`); protocol đích phải `active`. Sai thì trả 409.
  - Config đích giữ model, slice, class mapping và compute target của nguồn. Attack đích là các attack bắt buộc của protocol, với spec version mà protocol ghim, level bắt buộc, cộng các level nguồn đã chạy cho cùng spec. Attack có ở nguồn mà protocol không yêu cầu vẫn được giữ.
  - Slice nhỏ hơn `min_slice_size` không chặn tạo bản nháp; `warnings` ghi rõ, và compliance sẽ chặn khi gửi duyệt.
- Experiment mới không kế thừa run, kết quả hay verdict nào của experiment nguồn. `promoted_from` chỉ để truy vết và ghi audit log. `POST /experiments` kiểm `promoted_from` là experiment Khám phá đã kết thúc; sai thì trả 422.

### Template, preset, gợi ý tiêu chí

- `GET /protocol-templates` trả 4 template. `GET /protocol-templates/{key}/draft` trả `ProtocolCreate` đã điền: spec version đang `active`, level suy từ `level_ratios`, và tiêu chí gợi ý. Reviewer sửa nếu muốn rồi `POST /protocols` như Phase 8. Template không bao giờ tự tạo protocol.
- **Gợi ý tiêu chí:** mỗi attack quét lưới nhận một `max_drop_at_level` (`relative_drop`) tại level bắt buộc giữa. Ngưỡng theo `strictness`: lenient 0.5, standard 0.3, strict 0.15. Mỗi attack tìm ngưỡng nhận một `min_breaking_point` tại `lo + 0.5·(hi − lo)`. Gợi ý chỉ phụ thuộc template và catalog, **không** phụ thuộc kết quả của experiment nào (nguyên tắc 2).
- `POST /experiments/draft` dựng `ExperimentCreate` từ protocol và preset:
  - Level là `min + r·(max − min)` với từng `r` trong `level_ratios`, làm tròn về `values` gần nhất khi tham số rời rạc, hợp với level bắt buộc của protocol.
  - Preset `deep` thêm tìm ngưỡng cho attack hỗ trợ tìm ngưỡng (không áp cho patch). Một experiment không có hai attack cùng spec, nên attack đó chạy tìm ngưỡng **thay cho** quét lưới; attack mà protocol bắt buộc quét lưới vẫn quét lưới với lưới của `deep` (Chốt ở Group 0).
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
  - Spec cần train (patch) hoặc model không có gradient (ONNX, hoặc `supports_gradients = false`) gặp attack cần gradient trả 422.
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

- [x] (Từ R1) Số luồng torch và loại lõi CPU (P/E) ảnh hưởng tới failure case của PGD nhưng không có trong fingerprint hay `Environment`. Các phương án: ghi số luồng vào `Environment` (đổi contract), để runner tự ghim, hoặc chấp nhận như hiện tại. Cần quyết trước khi chạy experiment chính thức trên nhiều máy. → Chuyển sang backlog trong `roadmap.md` (người dùng chốt 2026-10-10).
- [ ] Layout đầu ra ONNX: hai layout ở trên có đủ cho model người dùng dự kiến đăng ký không?
