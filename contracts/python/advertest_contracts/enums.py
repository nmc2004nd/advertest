"""Enum dùng chung giữa ML core, backend, worker và frontend."""

from enum import StrEnum


class Role(StrEnum):
    ENGINEER = "engineer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DISABLED = "disabled"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STOPPED_LIMIT = "stopped_limit"
    CANCELLED = "cancelled"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SearchStatus(StrEnum):
    FOUND = "found"
    NOT_REACHED = "not_reached"
    BELOW_MIN = "below_min"
    STOPPED_LIMIT = "stopped_limit"
    NON_MONOTONIC = "non_monotonic"
    FAILED = "failed"  # Phase 7: mAP sạch bằng 0, không còn object cho ASR, lỗi không phục hồi


class StopReason(StrEnum):
    BUDGET = "budget"
    TIME = "time"


class SkipReason(StrEnum):
    CACHED = "cached"
    INCOMPATIBLE = "incompatible"
    EARLY_STOP = "early_stop"  # Phase 6: level nhỏ hơn của cùng attack đã làm model sụp


class ComputeKind(StrEnum):
    LOCAL = "local"
    RENTED = "rented"


class BillingMode(StrEnum):
    NONE = "none"
    HOURLY = "hourly"


class LimitKind(StrEnum):
    BUDGET = "budget"
    TIME = "time"


class AttackKind(StrEnum):
    ATTACK = "attack"
    CORRUPTION = "corruption"
    OCCLUSION = "occlusion"


class AttackAccess(StrEnum):
    WHITE_BOX = "white_box"
    BLACK_BOX = "black_box"
    NOT_APPLICABLE = "not_applicable"  # Phase 6: corruption và occlusion (không phải kẻ tấn công)


class RunMode(StrEnum):
    GRID = "grid"
    SEARCH = "search"


class ThresholdKind(StrEnum):
    RELATIVE_DROP = "relative_drop"
    ABSOLUTE_DROP = "absolute_drop"
    ATTACK_SUCCESS_RATE = "attack_success_rate"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    CHANGES_REQUESTED = "changes_requested"
    REJECT = "reject"


class ErrorCode(StrEnum):
    # Phase 3 thêm các mã cho API nội bộ của worker (401, 403, 404, 409, 422).
    # Phase 4 thêm các mã của xác thực và phân quyền.
    NOT_IMPLEMENTED = "not_implemented"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_REQUEST = "invalid_request"  # 422: dữ liệu hợp lệ về cú pháp nhưng sai nghiệp vụ
    INVALID_CREDENTIALS = "invalid_credentials"  # 401: sai email hoặc mật khẩu
    ACCOUNT_PENDING = "account_pending"  # 403: đúng mật khẩu, tài khoản chờ duyệt
    ACCOUNT_REJECTED = "account_rejected"
    ACCOUNT_DISABLED = "account_disabled"
    RATE_LIMITED = "rate_limited"  # 429
    CSRF_FAILED = "csrf_failed"  # 403
    VALIDATION_ERROR = "validation_error"  # 422: body không đúng schema
    # Phase 5: experiment trên web; lỗi máy chủ không xử lý được.
    NOT_SUPPORTED_YET = "not_supported_yet"  # 422: tính năng chưa có ở phase này (mode = search)
    QUEUE_LIMIT_REACHED = "queue_limit_reached"  # 409: đã có 3 experiment đang chờ
    INTERNAL_ERROR = "internal_error"  # 500: không kèm chi tiết (chi tiết chỉ ghi log server)
    # Phase 8: protocol, review.
    NOT_COMPLIANT = "not_compliant"  # 422: experiment không tuân thủ protocol; kèm `compliance`
    EXPERIMENT_LOCKED = "experiment_locked"  # 409: experiment đã gửi duyệt (bị khóa)
    # 409: approve khi checklist chưa đủ; kèm `checklist`.
    CHECKLIST_INCOMPLETE = "checklist_incomplete"
    # Phase R2: thử nhanh.
    QUICK_TRY_BUSY = "quick_try_busy"  # 429: người gọi đã có một lượt queued/running
    GONE = "gone"  # 410: kết quả thử nhanh đã hết hạn và bị xóa


class ProtocolStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    DEV = "dev"  # Protocol phát triển (dev-open, Phase 3): không bao giờ được gửi duyệt.


class CaseSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"


class DisplayMode(StrEnum):
    """Cách hiển thị ảnh failure case (Phase 5; Phase 6 thêm làm mờ theo từng case)."""

    NORMAL = "normal"  # dataset đã ẩn danh, hoặc case đã làm mờ (Phase 6): có URL ảnh
    HIDDEN_UNANONYMIZED = "hidden_unanonymized"  # dataset và case chưa làm mờ: không cấp URL ảnh
    DEV_UNBLURRED = "dev_unblurred"  # chưa làm mờ nhưng server bật DEV_ALLOW_UNBLURRED


class RunPhase(StrEnum):
    """Giai đoạn của run đang chạy (Phase 6): run patch train trước khi đánh giá."""

    TRAINING = "training"
    EVALUATING = "evaluating"


class SearchStage(StrEnum):
    """Giai đoạn của một lần tìm ngưỡng (Phase 7, requirements.md mục Thuật toán)."""

    COARSE = "coarse"  # quét thô trên tập con
    BISECT_SUBSET = "bisect_subset"  # chia đôi trên tập con
    CONFIRM = "confirm"  # xác nhận hai đầu khoảng trên toàn slice
    BISECT_FULL = "bisect_full"  # dịch khoảng rồi chia đôi trên toàn slice
    DONE = "done"  # kết quả cuối (status có giá trị)


class EvalScope(StrEnum):
    """Tập ảnh mà run đánh giá (Phase 7)."""

    FULL = "full"  # toàn slice (mọi run quét lưới)
    SUBSET = "subset"  # tập con cố định của tìm ngưỡng


class PerturbationImageKind(StrEnum):
    """Nội dung ảnh thứ ba của failure case (Phase 6)."""

    AMPLIFIED_NOISE = "amplified_noise"  # nhiễu khuếch đại (FGSM, PGD)
    DIFFERENCE = "difference"  # vùng khác biệt |δ| (corruption, occlusion)
    PATCH_LOCATION = "patch_location"  # vị trí patch


# ---------------------------------------------------------------- Phase 8: protocol, review, report


class CaseVerdictKind(StrEnum):
    """Loại verdict của một failure case (Phase 8)."""

    SAFETY_RELEVANT = "safety_relevant"  # ảnh hưởng an toàn: bắt buộc có mitigation
    ACCEPTABLE = "acceptable"
    ANNOTATION_ISSUE = "annotation_issue"  # lỗi nhãn của dataset, không phải lỗi model


class ModelVerdict(StrEnum):
    """Kết luận của reviewer về model; tách khỏi quyết định chấp nhận bài test (Phase 8)."""

    MEETS_CRITERIA = "meets_criteria"
    DOES_NOT_MEET = "does_not_meet"
    CONDITIONAL = "conditional"


class CriterionKind(StrEnum):
    MAX_DROP_AT_LEVEL = "max_drop_at_level"  # attack quét lưới: đại lượng tại level ≤ ngưỡng
    MIN_BREAKING_POINT = "min_breaking_point"  # attack tìm ngưỡng: điểm gãy ≥ level


class CriterionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ReportStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class CommentTargetType(StrEnum):
    EXPERIMENT = "experiment"
    RUN = "run"
    FAILURE_CASE = "failure_case"


class ComplianceCode(StrEnum):
    """Mục kiểm tra tuân thủ protocol khi ước lượng, tạo experiment và gửi duyệt (Phase 8)."""

    PROTOCOL_ACTIVE = "protocol_active"  # protocol `active` (hoặc `dev`) khi tạo experiment
    ATTACK_PRESENT = "attack_present"  # attack bắt buộc có mặt
    SPEC_SHA256 = "spec_sha256"  # đúng version spec
    MODE = "mode"  # đúng chế độ (quét lưới / tìm ngưỡng)
    GRID_LEVELS = "grid_levels"  # chứa mọi level bắt buộc
    SEARCH_THRESHOLD = "search_threshold"  # cùng threshold_kind, threshold, class_filter
    SEARCH_RANGE = "search_range"  # dải bao phủ [lo, hi] của protocol
    SEARCH_TOL = "search_tol"  # tol ≤ max_tol
    SEARCH_BOOTSTRAP = "search_bootstrap"  # bootstrap_samples ≥ min_bootstrap_samples
    MIN_SLICE_SIZE = "min_slice_size"
    MODEL_GRADIENTS = "model_gradients"  # model hỗ trợ gradient khi attack bắt buộc cần


class ChecklistCode(StrEnum):
    """Điều kiện trạng thái phía server trước khi chấp nhận (Phase 8, kickoff: chỉ gồm điều kiện
    trạng thái; trường nhập thiếu là 422, sai người là 403)."""

    PROTOCOL_NOT_DEV = "protocol_not_dev"
    REQUIRED_CASES_REVIEWED = "required_cases_reviewed"  # mọi case bắt buộc có verdict hiện hành


class SubmitCheckCode(StrEnum):
    """Điều kiện gửi duyệt (Phase 8, `POST /experiments/{id}/submit`), hiển thị trong hộp gửi
    duyệt trước khi gửi."""

    EXPERIMENT_COMPLETED = "experiment_completed"
    PROTOCOL_NOT_DEV = "protocol_not_dev"
    RUNS_FINAL = "runs_final"  # mọi run của attack bắt buộc có trạng thái cuối
    NO_DIRTY_RUNS = "no_dirty_runs"  # chỉ khi protocol có forbid_dirty_runs
    REQUIRED_CASES_VISIBLE = "required_cases_visible"  # không case bắt buộc nào bị ẩn


class ReviewQueueFilter(StrEnum):
    """Nhóm của hàng đợi review (`GET /reviews?status=`)."""

    WAITING = "waiting"  # submitted_for_review: chờ nhận
    MINE = "mine"  # in_review do người gọi đang nhận
    DECIDED = "decided"  # approved, changes_requested, rejected


class ReportNoteCode(StrEnum):
    """Lưu ý bắt buộc ở mục 2 của report (Phase 8, requirements.md mục Report)."""

    TEST_ENVIRONMENT_ONLY = "test_environment_only"  # mission.md nguyên tắc 8
    # eps, corruption tính trên ảnh letterbox dạng float, không lượng tử hóa 8-bit.
    INPUT_SPACE = "input_space"
    OCCLUSION_STRESS = "occlusion_stress"  # occlusion là phép thử chịu tải
    PATCH_FIXED_POSITION = "patch_fixed_position"  # patch ở vị trí cố định
    ANONYMIZATION = "anonymization"  # phương pháp làm mờ ảnh
    GIT_DIRTY = "git_dirty"  # có run chạy từ code chưa commit (protocol cho phép)
    EXCLUDED_CLASSES = "excluded_classes"  # class bị loại khỏi metric (class mapping)


# ---------------------------------------------------------------- Phase R2


class AttackSpecStatus(StrEnum):
    """Vòng đời spec trong catalog (Phase R2, requirements.md mục Catalog attack)."""

    DRAFT = "draft"
    CHECKING = "checking"  # đang chờ hoặc đang chạy job spec_check
    CHECK_FAILED = "check_failed"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    RETIRED = "retired"


class ModelStatus(StrEnum):
    CHECKING = "checking"
    CHECK_FAILED = "check_failed"
    READY = "ready"  # chỉ model ready được dùng trong experiment và thử nhanh


class ExperimentMode(StrEnum):
    """Suy ra từ protocol: status dev → exploration (mission.md nguyên tắc 11)."""

    EXPLORATION = "exploration"
    OFFICIAL = "official"


class ConclusionCode(StrEnum):
    NO_DATA = "no_data"  # chưa run nào có metric
    ROBUST = "robust"  # không có điểm yếu nào
    WEAK = "weak"
    WEAK_CLASS = "weak_class"  # mức sụt của một class ≥ 2 lần toàn bộ


class ToolJobKind(StrEnum):
    """Job công cụ của worker `--tools`; thứ tự lease: quick_try, rồi model_check và spec_check
    theo thứ tự tạo."""

    SPEC_CHECK = "spec_check"
    MODEL_CHECK = "model_check"
    QUICK_TRY = "quick_try"


class ToolJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SpecCheckName(StrEnum):
    """Bảy mục tự kiểm tra spec, theo thứ tự (requirements.md Phase R2)."""

    RUNS = "runs"  # build và apply không lỗi tại min, giữa, max
    VALUE_RANGE = "value_range"  # float32 trong [0, 1], đúng shape
    PAD_UNCHANGED = "pad_unchanged"  # mask = 0 giữ nguyên tuyệt đối
    IDENTITY = "identity"  # level "không biến đổi" cho ảnh y hệt (bỏ qua khi min > 0)
    BATCH_INVARIANT = "batch_invariant"  # batch 1 và batch 4 khớp nhau
    NORM_BOUND = "norm_bound"  # kind = attack: chuẩn nhiễu ≤ eps
    DETERMINISTIC = "deterministic"  # hai lần cùng seed cho ảnh giống hệt


class QuickTryObjectStatus(StrEnum):
    KEPT = "kept"
    LOST = "lost"  # object sạch không còn ghép được (IoU ≥ 0.5 cùng class)
    NEW = "new"  # object chỉ có trên ảnh bị tấn công
