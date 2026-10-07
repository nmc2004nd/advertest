# Requirements: Phase R1 — Refactor lớp chạy giữ hành vi

## Scope

Tách lớp chạy thành các thành phần có trách nhiệm đơn lẻ. Attack và model được cắm qua registry, không còn rẽ nhánh theo loại cụ thể. **Hành vi không đổi.** Kết quả của phase gồm:

1. **Điểm thay thế chính thức (seam)** cho cả hai runner: dựng perturbation, provenance (git, lib, digest) và nạp model được truyền qua tham số, không còn patch tên ở cấp module.
2. **`PerturbationRegistry`** (`attacks/`): mỗi loại phép biến đổi là một builder đăng ký theo tên adapter. Spec hiện có được ánh xạ sang adapter từ `kind` và `art_class`. Patch cũng đi qua registry. Factory không còn union `AnyPerturbation`.
3. **`ModelAdapter`** (`ml_core/models/`): một Protocol có khai báo năng lực, adapter Ultralytics bọc wrapper và estimator hiện có, cùng `ModelProvider` nạp lười có cache.
4. **Lõi dùng chung** (`ml_core/runner/`) cho CLI và worker: `FingerprintService` (kèm provenance), `ManifestBuilder`, chính sách lỗi tập trung, và đường dẫn artifact.
5. **Điều phối mỏng**: `JobRunner` (worker) chỉ còn lease, heartbeat, directive và gọi API. `Runner` (CLI) chỉ còn đọc cấu hình và ghi store.

Cuối phase: golden R1 (CLI và worker) vẫn pass. Mọi test nghiệm thu của Phase 0–8 vẫn pass. Thêm một builder giả mà không phải sửa factory hay runner.

## Out of Scope

- **Thay đổi contract.** Trường `adapter` và `adapter_params` của attack spec, metadata hiển thị, `ModelCard.framework` mới thuộc R2. R1 suy ra adapter từ dữ liệu hiện có.
- Adapter model `torchvision_detection` và `onnx`; đăng ký model qua web (R2).
- Thêm khả năng mới cho CLI: tìm ngưỡng, patch (vẫn chỉ chạy qua worker).
- Lập danh sách run ở backend (`backend/app/services/experiments.py`): giữ nguyên, R1 chỉ đụng phía chạy.
- Ghim số luồng torch hoặc ghi số luồng vào `Environment` (xem Open Questions).
- Đổi định dạng checkpoint, manifest, artifact hoặc layout store.

## Data / Fields

Không thay đổi contract, DB hay OpenAPI. Mọi interface mới là Python nội bộ.

### Interface mới (nội bộ, chữ ký gợi ý; agent có thể đổi tên nếu giữ trách nhiệm)

```python
# attacks/builders.py (agent attack)
class PerturbationBuilder(Protocol):
    adapter: ClassVar[str]                     # "art.evasion", "corruption.imagecorruptions",
                                               # "occlusion.bbox", "patch.robust_dpatch"
    requires: ClassVar[frozenset[str]]         # {"gradients"} với attack white-box
    image_kind: ClassVar[PerturbationImageKind]
    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation: ...
    def linf_eps(self, spec: AttackSpec, level: float) -> float | None: ...

@dataclass(frozen=True)
class BuildContext:
    estimator: BaseEstimator | None            # None khi model không hỗ trợ gradient
    patch: PatchArray | None = None            # patch đã train, chỉ với patch.*
    area_ratio: float | None = None

class PerturbationRegistry:
    def __init__(self, resolver: Callable[[AttackSpec], str] = effective_adapter) -> None: ...
    def register(self, builder: PerturbationBuilder) -> None: ...   # trùng tên adapter → ValueError; giữ builder đăng ký trước
    def builder_for(self, spec: AttackSpec) -> PerturbationBuilder: ...
    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation: ...
def effective_adapter(spec: AttackSpec) -> str  # (kind, art_class) → tên adapter
DEFAULT_REGISTRY: PerturbationRegistry          # 4 builder hiện có

# ml_core/models/adapter.py (agent ml-model)
@dataclass(frozen=True)
class Capabilities:
    gradients: bool
class ModelAdapter(Protocol):
    card: ModelCard
    capabilities: Capabilities
    def class_names(self) -> list[str]: ...
    def predict(self, images: ImageBatch, batch_size: int | None = None) -> list[Prediction]: ...  # None: cả lô một batch
    def estimator(self) -> BaseEstimator: ...  # NoGradients khi capabilities.gradients = False
class ModelProvider:                            # cache theo (weights_sha256, InferenceParams, device)
    def get(self, card: ModelCard, params: InferenceParams, device: str) -> ModelAdapter: ...

# ml_core/runner/ (agent worker)
class Provenance(Protocol):                     # mặc định: git_state(), lib_versions(), docker_image_digest()
    def git(self) -> GitState: ...
    def lib_versions(self) -> LibVersions: ...
    def docker_image_digest(self) -> str: ...
class FingerprintService:                       # build_fingerprint_inputs + provenance, dùng chung
class ManifestBuilder:
class ErrorPolicy:                              # exception → (RunStatus, code, message, dừng experiment?)
```

## Behaviour

### Giữ hành vi

- Với cùng đầu vào và cùng provenance, `FingerprintInputs`, `fingerprint`, manifest, `RunResult`, failure case và trạng thái run giống hệt trước refactor (`tech-stack.md` mục 9, luật 8; golden ở `tests/fixtures/golden/phase_r1_*.json`).
- `spec_sha256` của 10 spec trong catalog không đổi; `effective_adapter` chỉ đọc `kind` và `art_class`.
- Thứ tự run, dừng sớm, tìm ngưỡng, calibration, checkpoint và chạy tiếp, giảm batch khi hết VRAM, giới hạn thời gian, hủy và mất lease giữ nguyên ngữ nghĩa và thông điệp lỗi.
- Checkpoint do code trước R1 ghi phải được code sau R1 đọc và chạy tiếp.

### Seam (Group 1, trước mọi thay đổi khác)

- `JobRunner` nhận thêm tham số tùy chọn `perturbation_factory` và `provenance`. `Runner` và `run_config` (CLI) nhận thêm `provenance` và `clean_predictor` (`perturbation_factory` đã có). Mặc định giữ hành vi hiện tại.
- Tới hết Group 2, giá trị mặc định của seam là `None`: lúc gọi vẫn tra tên ở cấp module (`build_perturbation`, `git_state`, `lib_versions`, `docker_image_digest`, `predict_slice`) để các patch cũ trong test nghiệm thu còn chạy. Sau Group 2, mặc định đổi thành `EnvProvenance()`, `build_perturbation` và `predict_slice`.
- `PerturbationFactory` tạm được khai báo ở cả `ml_core/runner/run.py` và `job.py`, để worker không phải import module CLI. Group 5 gom về lõi dùng chung.
- Từ Group 2, test nghiệm thu chỉ thay thế qua seam, không patch tên ở cấp module nữa. Agent được đổi tên hay xóa các tên module cũ **sau khi** Group 2 xong.
- Từ Group 5, `Runner`, `run_config` và `JobRunner` nhận thêm seam `registry` (`PerturbationRegistry`, mặc định `DEFAULT_REGISTRY`) và `model_provider` (`ModelSource.get(card, params, device)`, mặc định `ModelProvider`). `registry` là seam chính: `linf_eps` và `image_kind` lấy từ builder của nó. `perturbation_factory(spec, estimator | None)` giữ chữ ký nhưng phải nhất quán với `registry`: builder mới phải được đăng ký vào `registry` truyền vào, không chỉ truyền qua `perturbation_factory`.

### Registry

- `builder_for` tìm tên adapter qua `resolver` của registry. Registry mặc định dùng `effective_adapter`; test truyền resolver riêng để chọn builder giả.
- `builder_for` báo `UnsupportedAttack` khi không có adapter, với thông điệp như hiện tại.
- Builder có `requires` chứa `gradients` mà `ctx.estimator is None` → `IncompatibleAttack` (run `skipped`, `incompatible`), như Phase 2.
- `linf_eps` và `image_kind` lấy từ builder. `ml_core/runner/executor.py::linf_eps` và `ml_core/runner/images.py::perturbation_kind` không còn rẽ nhánh theo loại cụ thể.
- `ml_core/runner/` và `backend/worker/advertest_worker/` không import lớp perturbation cụ thể (`ArtPerturbation`, `CorruptionPerturbation`, `OcclusionPerturbation`, `PatchPerturbation`).
- Train patch (`obtain_patch`) vẫn ở worker. Kết quả train đi vào `BuildContext.patch`, rồi builder `patch.robust_dpatch` dựng adapter. Calibration (`calibrate.py`) cũng dựng qua registry.

### Model

- `ModelProvider` thay `JobRunner._estimator` và `Runner.estimator`, nạp model một lần cho mỗi khóa cache.
- Model có `supports_gradients = false` → `Capabilities.gradients = false`. Thông điệp `skipped` giữ như hiện tại.
- Khóa cache `(weights_sha256, InferenceParams, device)`. Worker không dùng lại estimator giữa các bundle khác `InferenceParams` (trước R1 cache theo sha). Cache không giới hạn; xét giới hạn ở R2.

### Chính sách lỗi

- Một bảng duy nhất ánh xạ exception sang kết quả, thay các khối `except` rải trong `job.py::_run_one` và `run.py::_run_one`:

| Exception | Kết quả |
|---|---|
| `IncompatibleAttack` | run `skipped`, `incompatible` |
| `PatchInterrupted` | `cancelled` hoặc `stopped_limit` theo directive; dừng experiment |
| `LeaseLost` | dừng experiment, không gửi gì thêm |
| Hết VRAM | giảm batch một bậc rồi chạy lại batch (như `_shrink_batch`) |
| Exception khác | run `failed` (`error`), các run khác chạy tiếp |

- Cài đặt hai tầng: `CORE_POLICY` (`ml_core/runner/errors.py`) dùng chung cho CLI và worker; worker dùng `WORKER_POLICY = CORE_POLICY.with_rules(...)` cho `LeaseLost`, `StopExperiment`, `PatchInterrupted`. Hết VRAM ở batch 1 hoặc ngoài vòng batch → run `failed`.
- `IncompatibleAttack` ném ra khi đang chạy batch cũng cho `skipped` (`incompatible`); trước R1 là `failed`. Đây là khác biệt có chủ đích và không xảy ra với catalog hiện tại.

### Điều phối

- `job.py` không còn import `build_fingerprint_inputs`, `Manifest`, `ml_core.models.estimator`, hay module `attacks` nào ngoài `attacks.builders` (registry perturbation) và `attacks.registry` (catalog). `UnsupportedAttack` và `IncompatibleAttack` được export lại từ `attacks.builders`. Phần patch (`patch_key`, train) rời `job.py` ở Group 6.
- Đường dẫn artifact (`runs/<fp>/…` ở CLI, `runs/<run_id>/…` ở worker) gom vào một chỗ; layout không đổi.

## Decisions

- **R1 không đổi contract.** *Lý do:* refactor giữ hành vi phải chứng minh được bằng golden; đổi contract cùng lúc thì không tách được nguyên nhân khi golden lệch. Trường `adapter` thuộc R2.
- **Seam trước, tách sau; người duyệt chuyển test nghiệm thu sang seam ở Group 2.** *Lý do:* 7 chỗ trong `tests/acceptance` đang patch tên nội bộ (`job_module.build_perturbation` ×4, `job_module.git_state`, `run_module.git_state`, `run_module.predict_slice`); tách code trước sẽ làm vỡ test mà agent không được sửa. Người dùng chốt 2026-10-06.
- **Số luồng torch nằm ngoài phạm vi R1.** *Lý do:* R1 không đổi hành vi run thật. Người dùng chốt 2026-10-06.
- **Golden chạy torch 1 luồng với `use_deterministic_algorithms`.** *Lý do:* trên CPU nhiều luồng, failure case của PGD không tất định giữa các process; đo ngày 2026-10-06.
- **Test nghiệm thu R1 được thêm theo group:** người duyệt thêm từng test ngay trước group làm nó pass, nên `make check` luôn xanh (`plan.md` bước 7). Người dùng chốt 2026-10-06 (kickoff).
- **Registry nhận resolver tiêm vào được.** *Lý do:* chọn được builder giả khi chưa có trường `adapter`; R2 chỉ cần thay resolver. Người dùng chốt 2026-10-06 (kickoff).
- **`predict_slice` chuyển sang seam `clean_predictor`.** *Lý do:* không còn patch tên cấp module nào trong test nghiệm thu. Người dùng chốt 2026-10-06 (kickoff).
- **Tên nhánh `phaser1-<agent>`, test ở `tests/acceptance/phase_r1/`.** *Lý do:* các skill dùng `NN` như chỗ điền tên.
- **Nhánh R1 merge vào `dev`, không vào `main`.** *Lý do:* `main` chưa có `dev` (spec R1, Group 0/1); merge thẳng vào `main` kéo theo 127 file ngoài group. Người dùng chốt 2026-10-07.
- **`attacks.factory.build_perturbation` giữ nguyên tên đến hết R1.** *Lý do:* test nghiệm thu phase_06/07/08/r1 import tên này làm mặc định của seam `perturbation_factory`; agent không được sửa test. Người dùng chốt 2026-10-07.
- **`ModelProvider.get` báo `ValueError` khi `ModelCard.framework` khác `ultralytics`, cho tới khi R2 thêm adapter.** *Lý do:* R1 chỉ có adapter Ultralytics; báo lỗi rõ ràng tốt hơn nạp sai. Người duyệt chốt 2026-10-07 (review Group 4).
- **`registry` là seam chính của việc dựng perturbation; `perturbation_factory` phải nhất quán với nó.** *Lý do:* `linf_eps`/`image_kind` đọc từ builder của `registry`; builder chỉ truyền qua `perturbation_factory` sẽ báo `UnsupportedAttack`. Người duyệt chốt 2026-10-07 (review Group 5, phát hiện 2).
- **Lỗi `ModelProvider.get` trong phép kiểm gradient của worker (`job.py:491`, `job.py:246`) để R2 sửa.** *Lý do:* R1 chỉ có ultralytics nên lỗi chưa xảy ra được; khi có adapter khác thì lỗi này phải chỉ làm run `failed`, không dừng cả experiment. Người duyệt chốt 2026-10-07 (review Group 5, phát hiện 3).

## Context

- `mission.md` nguyên tắc 3, 4 và 6; `tech-stack.md` mục 9, luật 8 (golden).
- Hiện trạng, khảo sát 2026-10-06:
  - `backend/worker/advertest_worker/job.py` (963 dòng): `JobRunner` ôm estimator, fingerprint (`_inputs`, `_Provenance`), dừng sớm (`_skip_early_stop`), tìm ngưỡng (`_search`, `_JobSearchHooks`), train patch (`_patch_perturbation`), checkpoint (`_executor`, `_drop_checkpoint`), OOM (`_shrink_batch`), manifest và gửi trạng thái (`_Finisher`).
  - `ml_core/runner/run.py` (408 dòng): `Runner` lặp lại fingerprint, estimator, dựng perturbation và xử lý lỗi.
  - Đã tách sẵn: `ml_core/runner/executor.py::RunExecutor` (batch, checkpoint) và `ml_core/runner/candidates.py` (ứng viên failure case, làm mờ).
  - `attacks/factory.py::AnyPerturbation` là union 3 loại. Patch không đi qua factory (`job.py:655`, `calibrate.py:147`). `executor.py:216` dùng `isinstance(ArtPerturbation)`.
  - Golden R1: commit `6861ca8`. CLI: 9 spec × 2 level trên 5 ảnh. Worker: 9 spec × 2 level, cộng patch × 2 level, cộng một lần tìm ngưỡng PGD L∞.

## Open Questions

- [ ] Số luồng torch ảnh hưởng tới failure case của attack lặp (PGD) trên CPU nhưng không có trong fingerprint hay `Environment`. Nên ghi vào `Environment`, để runner tự ghim, hay chấp nhận như hiện tại? Quyết ở R2 hoặc trước khi chạy experiment chính thức trên nhiều máy.
