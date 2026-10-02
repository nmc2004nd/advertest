# Requirements: Phase 8 — Protocol, review và report

## Scope

Hiện thực hóa quy trình kiểm thử độc lập: tiêu chí được chốt trước, người chạy test không tự duyệt, kết quả được khóa khi gửi duyệt, và report chính thức chỉ ra đời sau khi reviewer chấp nhận. Kết quả của phase gồm:

1. **Protocol có version** do reviewer tạo: attack bắt buộc, tiêu chí đạt, số case phải review, các ràng buộc khác.
2. **Kiểm tra tuân thủ protocol** khi tạo experiment; wizard điền sẵn và khóa phần bắt buộc.
3. **Gửi duyệt**: điều kiện gửi, giải trình cho run không hoàn thành, khóa experiment.
4. **Hàng đợi và không gian review**: nhận review, đánh giá tiêu chí tự động, danh sách kiểm tra trước khi duyệt, bình luận.
5. **Verdict cho failure case** có version, với phím tắt và thao tác chạm.
6. **Quyết định review**: chấp nhận, yêu cầu sửa, từ chối; kết luận về model.
7. **Report chính thức** PDF và JSON sinh ở server khi được chấp nhận, có mã hash, và **trang xác minh công khai**.
8. **Audit log** cho toàn bộ vòng đời.

Cuối phase: engineer gửi duyệt; một reviewer khác review và chấp nhận; report được sinh; trang xác minh báo file khớp.

## Out of Scope

- Chi phí tiền trong report (Phase 9). Report chỉ ghi thời gian xử lý.
- Thu hồi report đã phát hành.
- Chữ ký số bằng khóa bí mật (report dùng hash và trang xác minh).
- Phân công reviewer tự động.
- Thông báo trong ứng dụng; email cho sự kiện review ngoài các email dưới đây.
- So sánh nhiều experiment (Phase 11).

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

**`ProtocolBody`** (thay thế định nghĩa ở Phase 0):

| Field | Type | Notes |
|---|---|---|
| `description` | string | Mục đích của protocol |
| `required_attacks` | list | Mỗi phần tử: `attack_spec_name`, `spec_sha256`, `mode`; với `grid`: `levels` bắt buộc phải có; với `search`: `threshold_kind`, `threshold`, `class_filter`, `lo`, `hi`, `max_tol`, `min_bootstrap_samples` (mặc định 200) |
| `min_slice_size` | int | |
| `pass_criteria` | list | Mỗi phần tử: `kind` (`max_drop_at_level` / `min_breaking_point`), `attack_spec_name`, `level`, `threshold_kind`, `threshold`, `class_filter` |
| `cases_to_review_per_attack` | int | Mặc định 5 |
| `forbid_dirty_runs` | bool | Mặc định `true` |

Trường `review_severity_threshold` của Phase 0 bị bỏ.

**Enum mới:**

| Enum | Giá trị |
|---|---|
| `CaseVerdictKind` | `safety_relevant`, `acceptable`, `annotation_issue` |
| `ModelVerdict` | `meets_criteria`, `does_not_meet`, `conditional` |
| `CriterionStatus` | `pass`, `fail`, `inconclusive` |
| `ReportStatus` | `generating`, `ready`, `failed` |

**Schema mới:**

| Schema | Nội dung chính |
|---|---|
| `ComplianceItem` | `code`, `satisfied`, `detail` |
| `SubmitForReview` | `note`, `run_explanations` (map `run_id` → lời giải trình) |
| `CaseVerdictInput` | `severity` (`CaseSeverity`), `kind` (`CaseVerdictKind`), `mitigation` |
| `CaseVerdictView` | Input + `version`, `reviewer`, `created_at` |
| `CriterionResult` | `index`, `status`, `value`, `detail` |
| `ChecklistItem` | `code`, `satisfied`, `detail` |
| `ReviewDecisionInput` | `decision` (`ReviewDecision`), `model_verdict`, `conclusion`, `mitigation`, `inconclusive_justification` |
| `ReviewComment` | `id`, `author`, `body`, `target_type` (`experiment` / `run` / `failure_case`), `target_id`, `created_at` |
| `ReportSnapshot` | Toàn bộ nội dung report dạng JSON (xem mục Report) |
| `ReportView` | `id`, `experiment_id`, `status`, `approved_by`, `approved_at`, `json_sha256`, `pdf_sha256`, URL tải (chỉ khi có quyền) |
| `VerifyInfo` | `report_id`, `issued_at`, `json_sha256`, `pdf_sha256` |

`EstimateResponse` và `ExperimentDetail` thêm `compliance[]`. `ExperimentDetail` thêm `review` (người nhận review, thời điểm, quyết định, kết luận, `criteria_results`, `checklist`) và `report` (`ReportView`, nếu có).

**Ma trận quyền:** thêm `review.comment` cho engineer và reviewer. Bảng trong test nghiệm thu Phase 4 được cập nhật tương ứng.

### Chốt ở Group 0 (2026-10-02)

Chi tiết contract (nguồn sự thật: `contracts/python/advertest_contracts/models.py`, mock trong `contracts/mocks/`):

- **`ProtocolBody`** có `schema_version = 2`. `RequiredAttack` gồm `attack_spec_name`, `spec_sha256`, `mode` và `grid` (`levels`, không trùng) hoặc `search` (`RequiredSearch`: `threshold_kind`, `threshold`, `class_filter`, `lo`, `hi`, `max_tol` < `hi − lo`, `min_bootstrap_samples` 0–1000, mặc định 200). `PassCriterion` thêm `kind` (`CriterionKind`), `attack_spec_name`, `level`.
- **Kiểm tra ngay trong contract (422 `validation_error`):**
  - `attack_spec_name` không trùng trong một protocol (mỗi attack một chế độ, như Phase 5 không cho hai attack cùng spec);
  - tiêu chí chỉ tham chiếu attack có trong `required_attacks`;
  - `max_drop_at_level` chỉ dùng với attack quét lưới, `level` phải là một level bắt buộc;
  - `min_breaking_point` chỉ dùng với attack tìm ngưỡng, cùng `threshold_kind`, `threshold`, `class_filter` với `search`, và `lo < level ≤ hi`.
  - Kiểm tra cần catalog (spec tồn tại, `spec_sha256`, patch không tìm ngưỡng, dải trong `primary_param`, `MAX_RUNS`) ở backend (422 `invalid_request`).
- **Danh sách rỗng:** `required_attacks` và `pass_criteria` được rỗng để `dev-open` hợp lệ. Migration ghi body của `dev-open` đúng như `contracts/mocks/protocol_body/dev_open.json` và cập nhật `body_sha256`. `ProtocolCreate` (`name`, `body`) và `ProtocolVersionCreate` (`body`) bắt buộc có ít nhất một attack và một tiêu chí.
- **Version protocol:** `POST /protocols/{id}/versions` chỉ tạo được từ version mới nhất của `name` (khác → `409`); version cũ chuyển `retired` trong cùng giao dịch, nên mỗi `name` có tối đa một bản `active`. Ghi `protocol.versioned`, và `protocol.retired` cho bản cũ.
- **`ProtocolView`** (`GET /protocols/{id}`, kết quả tạo/version/retire): `id`, `name`, `version`, `status`, `body`, `body_sha256` (= `sha256_of(body)`), `created_by` (null chỉ với `dev`), `created_at`. `GET /protocols?include_retired=true` thêm bản `retired` cho trang `/protocols`.
- **Endpoint (khung `501` ở Group 0):**

  | Endpoint | Permission | Trả về |
  |---|---|---|
  | `POST /experiments/{id}/submit` (`SubmitForReview`) | `experiment.submit_review` | `ExperimentDetail` |
  | `GET /experiments/{id}/comments` | `experiment.read` | `ReviewComment[]`, cũ nhất trước |
  | `POST /experiments/{id}/comments` (`ReviewCommentCreate`) | `review.comment` | `ReviewComment` (201) |
  | `GET /reviews?status=waiting\|mine\|decided&sort=submitted_at\|max_drop` | `review.decide` | `ReviewQueueItem[]` |
  | `POST /reviews/{experiment_id}/claim`, `/release` | `review.decide` | `ExperimentDetail` |
  | `POST /reviews/{experiment_id}/decision` (`ReviewDecisionInput`) | `review.decide` | `ExperimentDetail` |
  | `POST /reviews/{experiment_id}/cases/{case_id}/verdicts` (`CaseVerdictInput`) | `review.decide` | `CaseVerdictView` (201) |
  | `GET /failure-cases/{case_id}/verdicts` | `experiment.read` | `CaseVerdictView[]`, mới nhất trước |
  | `GET /reports` | `report.read` | `ReportView[]` |
  | `GET /reports/{id}` | `report.read` | `ReportDetail` (`report`, `snapshot` khi `ready`) |
  | `GET /reports/{id}/download?format=pdf\|json` | `report.export` | `ReportDownload` (`url`, `expires_at`, `sha256`, `filename`) |
  | `GET /reports/files/{token}` | `report.export` | Đúng file đã lưu |
  | `POST /reports/{id}/regenerate` | `report.export` | `ReportView` |
  | `GET /verify/{report_id}` | công khai | `VerifyInfo`; report không có hoặc chưa `ready` → `404` |

  Ghi verdict nằm dưới `/reviews` chứ không ở `POST /failure-cases/{id}/verdicts`: test kiến trúc Phase 3 cấm API người dùng có endpoint ghi dưới `/runs` và `/failure-cases`. Case không thuộc experiment → `404`.
- **Lỗi:** `ErrorCode` thêm `not_compliant` (422, `error.compliance` đủ mọi mục), `experiment_locked` (409), `checklist_incomplete` (409, `error.checklist`). `ErrorBody` thêm `compliance`, `checklist` (bỏ khỏi body khi null).
- **Enum mã:** `ComplianceCode`, `ChecklistCode` (`protocol_not_dev`, `required_cases_reviewed`), `SubmitCheckCode`, `CommentTargetType`, `CriterionKind`, `ReviewQueueFilter`, `ReportNoteCode`. `ComplianceItem` thêm `attack_spec_name` (null với mục không theo attack).
- **`ExperimentDetail`:**
  - `compliance[]`;
  - `submit_check[]` và `runs_requiring_explanation[]`: chỉ khi `completed`, cho hộp gửi duyệt; backend Phase 8 luôn điền `submit_check` khi `completed`;
  - `review` (`ReviewView`): có khi và chỉ khi đã gửi duyệt. Gồm `submitted_at`, `submission_note`, `run_explanations`, `assignee`, `claimed_at`, quyết định, `criteria_results`, `checklist`, `required_cases` (kèm `current_verdict`, `display_mode`), `comments_count`;
  - `report`: chỉ khi `approved`.
  - Người nhận review khác người tạo (kiểm cả trong contract).
- **`ReviewDecisionInput`:** `approve` thiếu `model_verdict` hoặc `mitigation` → 422 ngay ở contract. Thiếu `inconclusive_justification` khi có tiêu chí `inconclusive` → 422 ở backend.
- **`ReportSnapshot`:**
  - các khóa `summary`, `notes`, `configuration`, `results`, `runs`, `reviewed_cases`, `history`, `reproducibility`, `resources`, tương ứng 9 mục;
  - `notes` luôn có `test_environment_only` và `input_space`; có `git_dirty` khi và chỉ khi có run `git_dirty` (protocol phải cho phép);
  - `reviewed_cases` chỉ gồm case `anonymization.applied`;
  - `history.timeline` gồm `experiment.submitted`, `review.claimed`, `review.released`, `review.decided`;
  - file JSON là `canonical_json(snapshot)`.
- **`ReportView`:** `generated_at`, `json_sha256`, `pdf_sha256` có khi và chỉ khi `ready`; có `model_verdict`, `experiment_name`.

### Thay đổi DB

| Bảng | Thay đổi |
|---|---|
| `protocols` | `body` theo schema mới; migration cập nhật `dev-open` |
| `experiments` | Thêm `submission_note`, `submitted_at`, `review_assignee_id`, `claimed_at`, `decided_at` |
| `run_explanations` | Mới: `run_id`, `author_id`, `text`, `created_at` |
| `case_verdicts` | Thêm `kind` |
| `reviews` | Thêm `model_verdict`, `inconclusive_justification`, `criteria_results`, `checklist` |
| `review_comments` | Mới: `id`, `experiment_id`, `author_id`, `target_type`, `target_id`, `body`, `created_at` |
| `reports` | Thêm `status`, `snapshot_key`, `json_key`, `pdf_key`, `json_sha256`, `pdf_sha256`, `attempts`; bỏ cột `sha256` đơn và `uq_reports_sha256`; `exported_by` đổi thành `approved_by`; unique `experiment_id` |

Ràng buộc DB:
- `advertest_app` không có quyền `UPDATE`/`DELETE` trên `review_comments`, `run_explanations`.
- Trigger: không cho thêm `case_verdicts`, `review_comments`, `run_explanations` khi experiment ở trạng thái `approved`, `changes_requested` hoặc `rejected`.
- Trigger Phase 0 (người review ≠ người tạo) vẫn giữ; thêm tương tự cho `experiments.review_assignee_id`.
- `reports` (Phase 0: chỉ thêm) được cấp thêm `UPDATE`, không có `DELETE`. Trigger chỉ cho sửa `status`, `attempts`, các cột key và hash, và chỉ khi dòng hiện tại có `status ≠ ready`; dòng đã `ready` là bất biến. Sinh lại cập nhật đúng dòng đó nên `report_id` không đổi (kickoff 2026-10-02).

## Behaviour

### Protocol
| Endpoint | Permission | Hành vi |
|---|---|---|
| `GET /protocols`, `GET /protocols/{id}` | `protocol.read` | |
| `POST /protocols` | `protocol.manage` | Tạo protocol `active` version 1 |
| `POST /protocols/{id}/versions` | `protocol.manage` | Tạo version mới (bản ghi mới, cùng `name`); version cũ giữ nguyên |
| `POST /protocols/{id}/retire` | `protocol.manage` | `active` → `retired`; experiment đã tạo không bị ảnh hưởng |

- Nội dung một version không bao giờ thay đổi sau khi tạo.
- Kiểm tra khi tạo: attack spec tồn tại và `spec_sha256` khớp; `pass_criteria` chỉ tham chiếu attack có trong `required_attacks`, `min_breaking_point` chỉ dùng với attack ở chế độ tìm ngưỡng; `patch` không được ở chế độ tìm ngưỡng.
- Số level quét lưới bắt buộc cộng Σ `max_points` của các attack tìm ngưỡng bắt buộc (tính với `tol = max_tol`, `coarse_n` mặc định, có giai đoạn tập con) không vượt `MAX_RUNS = 50` (Phase 7), nếu không thì không experiment nào tuân thủ được → `422`.

### Tuân thủ protocol khi tạo experiment
Experiment gắn protocol `active` phải thỏa mọi điều sau, nếu không → `422` kèm `compliance[]`:
- mỗi attack bắt buộc có mặt với đúng `spec_sha256` và `mode`;
- quét lưới: chứa mọi level bắt buộc (có thể thêm level khác);
- tìm ngưỡng: cùng `threshold_kind`, `threshold`, `class_filter`; dải bao phủ `[lo, hi]` của protocol; `tol ≤ max_tol`; `bootstrap_samples ≥ min_bootstrap_samples` (không có khoảng tin cậy thì tiêu chí không bao giờ `inconclusive` do KTC);
- slice có ít nhất `min_slice_size` ảnh;
- model hỗ trợ gradient nếu có attack bắt buộc cần gradient.

Engineer có thể thêm attack ngoài protocol. `compliance[]` cũng được trả trong ước lượng để wizard hiển thị trực tiếp.

### Gửi duyệt (`POST /experiments/{id}/submit`, permission `experiment.submit_review`, chỉ chủ sở hữu)
Điều kiện, sai thì `409` (hoặc `422` với lỗi dữ liệu nhập):
- experiment `completed`;
- protocol không ở trạng thái `dev`;
- mọi run của attack bắt buộc có trạng thái cuối; run bắt buộc nào không `completed` (và không phải `skipped` do `cached`/`early_stop`) phải có lời giải trình trong `run_explanations`;
- nếu `forbid_dirty_runs`: không run nào có `git_dirty = true`;
- không case bắt buộc nào có `display_mode = hidden_unanonymized` (case chưa làm mờ, chỉ có ở dữ liệu trước Phase 6) (kickoff 2026-10-02).

Lời giải trình chỉ được gửi kèm `SubmitForReview`; không có endpoint thêm giải trình riêng (kickoff 2026-10-02).

Khi gửi: trạng thái `submitted_for_review`, `submitted_at`; experiment bị **khóa** (mọi endpoint thay đổi experiment trả `409`, trừ bình luận); ghi `audit_log`; email cho mọi reviewer `active` (trừ người tạo).

### Nhận review
- `POST /reviews/{experiment_id}/claim` (`review.decide`): chỉ khi `submitted_for_review`; người tạo experiment → `403`; chuyển `in_review`, gán người nhận.
- `POST /reviews/{experiment_id}/release`: chỉ người đang nhận; trở về `submitted_for_review`.
- Chỉ người đang nhận mới ghi verdict và ra quyết định.
- `GET /reviews?status=` trả hàng đợi, tự loại experiment do chính người gọi tạo.

### Case bắt buộc review
- Với mỗi attack bắt buộc: `cases_to_review_per_attack` failure case có `severity_score` cao nhất trên mọi run của attack đó (cùng điểm thì theo `image_id`).
- Reviewer có thể review thêm case khác.

### Verdict
- `POST /reviews/{experiment_id}/cases/{case_id}/verdicts` (`review.decide`, người đang nhận; chốt ở Group 0): tạo verdict version mới; version mới nhất là hiện hành; mọi version được giữ.
- `mitigation` bắt buộc khi `kind = safety_relevant`.

### Đánh giá tiêu chí (tự động, chỉ mang tính tham khảo)
| `kind` | `pass` | `fail` | `inconclusive` |
|---|---|---|---|
| `max_drop_at_level` | Đại lượng tại level ≤ ngưỡng | > ngưỡng | Không có run toàn slice (`scope = full`) `completed` ở level đó, hoặc run `partial` |
| `min_breaking_point` | `found`/`non_monotonic` với cận dưới của `bracket` ≥ level, hoặc `not_reached` | Điểm gãy (= cận trên của `bracket`) < level, hoặc `below_min` | `near_threshold`, `stopped_limit`, `failed`, level nằm trong `bracket` (a < level < b), hoặc khoảng tin cậy của điểm gãy chứa level |

Level bắt buộc bị `skipped` do `early_stop`: `max_drop_at_level` dùng đại lượng của run kích hoạt (`trigger_run_id`), giống xếp hạng Phase 6; `detail` ghi "suy từ dừng sớm tại level X" (kickoff 2026-10-02).

### Danh sách kiểm tra trước khi chấp nhận
`approve` kiểm tra theo thứ tự (kickoff 2026-10-02):
1. Người gọi không phải người đang nhận, hoặc là người tạo → `403`.
2. Thiếu trường nhập: `conclusion`, `mitigation`, `model_verdict`; hoặc có tiêu chí `inconclusive` mà thiếu `inconclusive_justification` → `422`.
3. `checklist` có mục chưa thỏa → `409` kèm `checklist`. `checklist` chỉ gồm điều kiện trạng thái phía server (cũng trả trong `ExperimentDetail.review`):
   - protocol không phải `dev`;
   - mọi case bắt buộc có verdict hiện hành.

Frontend tự kiểm các trường nhập của form trước khi bật nút "Chấp nhận".

`changes_requested` và `reject` chỉ bắt buộc `conclusion` (lý do).

### Quyết định (`POST /reviews/{experiment_id}/decision`)
- `approve` → `approved`; `changes_requested` → `changes_requested`; `reject` → `rejected`. Cả ba là trạng thái cuối; sau đó không thêm verdict, bình luận hay giải trình được nữa.
- Ghi `reviews` (kèm `criteria_results`, `checklist` tại thời điểm quyết định) và `audit_log`; email cho engineer.
- Sau `changes_requested`, engineer dùng "Nhân bản" để tạo experiment mới (`cloned_from` trỏ về experiment cũ).

### Bình luận
- `POST /experiments/{id}/comments` (`review.comment`): khi experiment `submitted_for_review` hoặc `in_review`; gắn với experiment, run hoặc failure case; chỉ thêm, không sửa, không xóa.

### Report
**Sinh report:** ngay sau `approve`, tác vụ nền trong API:
1. Dựng `ReportSnapshot` từ DB và MinIO, chuẩn hóa bằng `canonical_json`, tính `json_sha256`.
2. Render HTML (Jinja2) → PDF (WeasyPrint); biểu đồ vẽ bằng matplotlib thành PNG nhúng vào; ảnh case dùng thumbnail đã làm mờ.
3. Tính `pdf_sha256`; lưu snapshot, JSON, PDF vào bucket `reports`; `status = ready`.
4. Lỗi → thử lại tối đa 3 lần, rồi `status = failed`; experiment vẫn `approved`; reviewer có thể bấm sinh lại.
5. Khi API khởi động, report còn ở `generating` (tác vụ nền bị ngắt) được sinh tiếp.

**Nội dung `ReportSnapshot`:**
1. **Tóm tắt:** model verdict, kết luận, mitigation, người duyệt, thời điểm.
2. **Phạm vi và lưu ý bắt buộc:** chỉ là môi trường kiểm thử (`mission.md` nguyên tắc 8); eps và corruption tính trong không gian đầu vào của model (ảnh letterbox dạng float, không lượng tử hóa 8-bit); occlusion là phép thử chịu tải; patch ở vị trí cố định; phương pháp làm mờ ảnh.
3. **Cấu hình:** protocol (tên, version, hash), model (tên, hash weights), dataset version, slice (hash, số ảnh), class mapping (hash, class bị loại), attack spec (version, hash), compute target và môi trường.
4. **Kết quả:** metric sạch; bảng và đường cong quét lưới; xếp hạng AUC; kết quả tìm ngưỡng kèm khoảng tin cậy; kết quả từng tiêu chí.
5. **Toàn bộ run:** mọi run kể cả `failed`, `skipped`, `stopped_limit`, `cancelled`, kèm lý do và lời giải trình.
6. **Failure case đã review:** thumbnail đã làm mờ, verdict hiện hành, mitigation.
7. **Lịch sử:** mọi experiment khác cùng model version và cùng dataset version, tạo trước thời điểm duyệt, gắn protocol này (mọi version) **hoặc** protocol `dev` (gắn nhãn "dev"), kèm trạng thái và người tạo; timeline review (gửi, nhận, số bình luận, quyết định).
8. **Tái lập:** fingerprint, git commit, cảnh báo `git_dirty`, phiên bản thư viện, Docker image của từng run.
9. **Tài nguyên:** thời gian xử lý đã dùng so với giới hạn.

Mỗi trang PDF có chân trang: mã report, "BẢN CHÍNH THỨC", hướng dẫn xác minh tại `/verify/{report_id}`.

**Quyền với report:**
| Endpoint | Permission | Hành vi |
|---|---|---|
| `GET /reports`, `GET /reports/{id}` | `report.read` | Xem report trong ứng dụng; URL tải chỉ trả cho người có `report.export` |
| `GET /reports/{id}/download?format=pdf\|json` | `report.export` | URL tạm thời; ghi `audit_log` (`report.downloaded`) |
| `POST /reports/{id}/regenerate` | `report.export` | Chỉ khi `failed` |
| `GET /verify/{report_id}` | Công khai | `VerifyInfo`, không có tên người hay nội dung |

### Audit log
Ghi các action: `protocol.created`, `protocol.versioned`, `protocol.retired`, `experiment.submitted`, `review.claimed`, `review.released`, `case_verdict.recorded`, `review.comment_added`, `run_explanation.added`, `review.decided`, `report.generated`, `report.generation_failed`, `report.downloaded`.

### Frontend

**Engineer:**
- Wizard bước 1: danh sách protocol `active` (và `dev-open`). Chọn protocol → attack bắt buộc được thêm và **khóa** (có biểu tượng khóa và chú thích "Theo protocol"); ngưỡng tìm kiếm điền sẵn và khóa; slice nhỏ hơn `min_slice_size` bị ẩn. Bảng tuân thủ (✓/✗) hiển thị trực tiếp ở cột tóm tắt.
- Chi tiết experiment: nút "Gửi duyệt" khi đủ điều kiện; hộp gửi duyệt gồm ghi chú, ô giải trình cho từng run bắt buộc chưa hoàn thành, danh sách điều kiện. Sau khi gửi: dải "Đã khóa – đang chờ duyệt"; tab mới **Review** (trạng thái, người nhận, bình luận, quyết định). Khi `changes_requested`: nút "Nhân bản để sửa".

**Reviewer:**
- `/reviews`: hàng đợi (chờ nhận / tôi đang review / đã quyết định), sắp theo thời gian gửi hoặc mức sụt lớn nhất; bảng trên desktop, thẻ trên điện thoại.
- `/reviews/:id`: nút Nhận / Trả lại; bảng tuân thủ và kết quả tiêu chí; danh sách kiểm tra trước khi chấp nhận (✓/✗ kèm lý do); bảng run kèm giải trình; biểu đồ kết quả (dùng lại Phase 5–7); danh sách case bắt buộc nhóm theo attack kèm tiến độ ("3/5 đã review"); bình luận; khung quyết định (kết luận, mitigation, model verdict, giải trình tiêu chí chưa kết luận) với ba nút. Nút "Chấp nhận" bị khóa cho đến khi danh sách kiểm tra đủ, kèm lý do.
- `/reviews/:id/cases/:caseId`: `CaseViewer` + form verdict + lịch sử verdict. Phím tắt: `J`/`K` case sau/trước, `1`–`4` mức nghiêm trọng, `S`/`A`/`N` loại verdict, `Ctrl+Enter` lưu, `?` hiện bảng phím tắt. Điện thoại: vuốt chuyển case; form verdict trong bottom sheet với nút lớn.
- `/protocols`: danh sách; form tạo và tạo version mới (xây dựng danh sách attack bắt buộc, tiêu chí, số case, `forbid_dirty_runs`); nút ngừng dùng.
- `/reports`, `/reports/:id`: xem report dạng trang web; reviewer có nút tải PDF và JSON.
- Trang chủ: khối reviewer (số experiment chờ nhận, danh sách tôi đang review).

**Công khai:**
- `/verify/:id`: hiển thị mã report, ngày phát hành, hai hash. Người dùng chọn file PDF hoặc JSON; hash được tính **trong trình duyệt** (Web Crypto), file không được gửi lên server; hiển thị "Khớp" hoặc "Không khớp".

**Chung:** watermark "BẢN NHÁP – CHƯA DUYỆT" giữ nguyên với mọi trang ngoài report chính thức; report chính thức hiển thị "BẢN CHÍNH THỨC".

## Decisions

- **Chấp nhận review là chấp nhận bài test, không phải tuyên bố model đạt.** Kết luận về model nằm trong `model_verdict`. *Lý do:* reviewer có thể chấp nhận một bài test làm đúng quy trình cho thấy model **không đạt**; hai khái niệm phải tách riêng.
- **Đánh giá tiêu chí tự động chỉ mang tính tham khảo.** *Lý do:* `mission.md` nguyên tắc 7 (con người quyết định); hệ thống đưa số liệu và cảnh báo, reviewer ký kết luận.
- **Case bắt buộc review lấy top-N theo attack.** *Lý do:* review toàn bộ hàng trăm case là không khả thi; top-N theo mức nghiêm trọng bao phủ những case quan trọng nhất của mỗi attack.
- **Report chứa lịch sử các experiment liên quan.** *Lý do:* chống chạy lại nhiều lần rồi chỉ gửi duyệt lần đẹp nhất; reviewer và người đọc report thấy được mọi lần thử.
- **Cấm run có code chưa commit theo mặc định.** *Lý do:* code chưa commit không thể tái lập và có thể đã bị chỉnh để cho kết quả đẹp.
- **Report sinh một lần khi chấp nhận, nội dung cố định; tải xuống chỉ lấy file đã lưu.** *Lý do:* mọi bản tải cùng một hash, trang xác minh có ý nghĩa.
- **Xác minh tính hash trong trình duyệt.** *Lý do:* người xác minh không phải gửi report (có thể chứa thông tin nội bộ) lên server; trang công khai không lộ tên người hay nội dung.
- **Nhận review trước khi quyết định.** *Lý do:* tránh hai reviewer cùng lúc ghi verdict và ra quyết định mâu thuẫn; trách nhiệm rõ ràng.
- **Lịch sử report gồm cả experiment `dev-open`.** *Lý do:* nếu không, engineer có thể thử nhiều seed hoặc slice với `dev-open` rồi chỉ chạy protocol thật một lần (kickoff 2026-10-02).
- **Report là bản ghi sửa được tới khi `ready`, bất biến sau đó.** *Lý do:* `report_id` phải có trước khi render (chân trang, `/verify`) và giữ nguyên qua các lần thử lại (kickoff 2026-10-02).
- **Khóa bằng cả service và trigger DB.** *Lý do:* như các luật chống gian lận khác, đặt ở DB thì bug ở tầng ứng dụng cũng không phá được.

## Context

- `mission.md` nguyên tắc 1 (tách quyền), 2 (tiêu chí chốt trước), 3 (bất biến, truy vết), 7 (con người quyết định), 8 (chỉ là kiểm thử), 9 (riêng tư).
- `tech-stack.md` mục 4 (WeasyPrint, email), 4.1 (quyền), 4.4 (tái lập).
- Phase 0: trigger người review ≠ người tạo, quyền DB. Phase 3: protocol `dev`. Phase 4: phiên, ma trận quyền. Phase 5: wizard, `CaseViewer`, email outbox. Phase 6: xếp hạng AUC, làm mờ. Phase 7: kết quả tìm ngưỡng, khoảng tin cậy.
- Phase 7 (ảnh hưởng thiết kế, replan 2026-10-02):
  - `breaking_point` là cận trên `b` của `bracket`; giao điểm thật nằm trong (a, b], nên tiêu chí `min_breaking_point` so level với cả khoảng.
  - Run tập con (`scope = subset`) có trong mục "Toàn bộ run" kèm nhãn phạm vi, nhưng không dùng cho tiêu chí hay đường cong quét lưới; nhãn `not_reached` trên biểu đồ so sánh là "> {hi/max}%"; kết quả tìm ngưỡng trong report ghi cả `bracket`, `points_used`/`max_points` và số mẫu bootstrap.
  - Run động đếm vào `MAX_RUNS = 50` qua `max_points` (PGD mặc định trên slice 300 ảnh: 21 điểm).
- Phase 6 (ảnh hưởng thiết kế):
  - Case tạo trước Phase 6 không có `anonymization`, nên `display_mode = hidden_unanonymized` và `artifacts = null`. Report chỉ nhúng thumbnail của case có `anonymization.applied`; case bắt buộc review cần quy tắc riêng cho case bị ẩn.
  - Mục "phương pháp làm mờ" của report lấy từ `anonymization.method`/`version` (`rule_v1`: theo box, không dùng model phát hiện mặt).
  - Ảnh thứ ba của case theo `perturbation_kind` (nhiễu khuếch đại / vùng khác biệt / vị trí patch); "heatmap nhiễu" ở roadmap chính là ảnh này.

## Open Questions

- [x] `max_drop_at_level` với level bị `skipped` (`early_stop`): dùng đại lượng của run kích hoạt như xếp hạng Phase 6 (kickoff 2026-10-02, xem mục Đánh giá tiêu chí).

- [ ] `cases_to_review_per_attack` mặc định 5 có phù hợp không.
- [x] Có cần thêm matplotlib vào `tech-stack.md` hay vẽ biểu đồ report bằng SVG tự sinh: matplotlib, đã ghi vào `tech-stack.md` cùng Jinja2 ở Group 0 (2026-10-02).
