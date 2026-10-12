# Requirements: Phase R3 — UX ứng dụng

## Scope

Phase R3 **sửa và bổ sung** giao diện đã có từ Phase 5–8 (không viết lại) để giải quyết nhận xét M1–M8 của mentor, và đưa các API của Phase R2 lên giao diện. Kèm theo đó là các tồn đọng backend, worker và attack mà R2 để lại cho R3.

**M1–M8.** Repo không lưu nguyên văn nhận xét của mentor. Danh sách dưới đây được suy ra từ các mục UX của Phase R4b trong `roadmap.md` (commit `7a32111`), và là danh sách dùng để nghiệm thu (người dùng chốt 2026-10-10):

| Mã | Nhận xét (suy ra) | Mục Behaviour |
|---|---|---|
| M1 | Trang experiment phải là trung tâm; người dùng không biết đang ở bước nào của quy trình | Trang experiment |
| M2 | Wizard quá nhiều bước và quá nhiều ô gõ tay; tên attack, level, dataset khó hiểu | Wizard 3 bước |
| M3 | Trang kết quả không nói ngay model yếu ở đâu | Kết quả và insight |
| M4 | Biểu đồ không có lời giải thích; thuật ngữ khó hiểu | Kết quả và insight, Thuật ngữ |
| M5 | Không rõ mỗi quyết định (gửi duyệt, approve, yêu cầu sửa, từ chối, xuất report) có hệ quả gì | Ý nghĩa quyết định |
| M6 | Trang chủ không cho biết việc tiếp theo của mỗi vai trò | Trang chủ |
| M7 | Muốn thêm attack hoặc model phải sửa code | Admin catalog và model |
| M8 | Thiếu cách minh họa nhanh một attack trên một ảnh | Thử nhanh |

Phase này gồm 4 mảng:

1. **Giao diện M1–M8** trên khung và token hiện có: trang experiment, wizard, trang kết quả, ý nghĩa quyết định, trang chủ, admin catalog và model, thử nhanh.
2. **Tồn đọng R2 ở backend, worker và attack:**
   - service `advertest-worker --tools` trong Docker, kèm fixture trong image;
   - gộp phần dựng fixture selfcheck;
   - làm mờ rộng hơn cho thử nhanh;
   - kiểm lại model `check_failed`;
   - dọn object MinIO mồ côi;
   - `validate` kiểm `art_class`.
3. **Insight trong report PDF.**
4. **Bổ sung contract nhỏ** (Group 0): recheck model, `insight` trong snapshot report, `promoted_from` trong `ExperimentDetail`.
5. **Bổ sung sau Group 0 (người dùng yêu cầu 2026-10-12):**
   - ảnh failure case và thử nhanh cắt bỏ viền letterbox khi hiển thị (`content_box`, đề xuất contract 001);
   - chuyển `.pt`/`.pth` upload qua web sang `.safetensors` trong sandbox chuyển đổi (service `converter`, đề xuất contract 003; `mission.md` nguyên tắc 10 sửa theo);
   - xóa model chưa dùng, lưu trữ / khôi phục model đã dùng, tạo class mapping qua web (bước mapping trong form đăng ký model và mục Class mapping ở trang chi tiết model; đề xuất contract 002). Phần giao diện map class cho model kéo từ Phase 10 lên; giao diện map class cho dataset riêng vẫn ở Phase 10.

Cuối phase, mọi test nghiệm thu Phase 0–8, R1 và R2 vẫn pass, và golden R1 vẫn khớp.

## Out of Scope

- Các mục còn lại của 11b chuyển sang **Phase R3b**, làm cùng landing (11a): gom toàn bộ câu chữ cũ vào `copy/vi.ts`, chuyển E2E sang tìm theo role/nhãn, đăng nhập/xác minh, font report PDF. Từ 2026-10-10, `design.md` đã mô tả đúng app hiện có, nên R3 không đổi token, font hay họa tiết (mục Behaviour "Phong cách giao diện").
- Landing page (Phase 11a, chuyển sang R3b).
- Thuật toán attack mới, adapter mới, và mở `.pt` hay pickle upload qua web ở bất cứ đâu ngoài sandbox chuyển đổi (`mission.md` nguyên tắc 10, sửa 2026-10-12).
- Tạo protocol tự động từ template. Template chỉ điền sẵn form cho reviewer (R2).
- So sánh nhiều experiment (Phase 11c). Dataset riêng và map class (Phase 10).
- Bản tiếng Anh.

## Data / Fields

Đổi contract (Group 0, người duyệt). Trường mới đều tùy chọn và bị bỏ khỏi JSON khi là `None`, để hash của dữ liệu cũ (report đã xuất, config) không đổi.

```python
# Kiểm lại model (tồn đọng R2 "Chốt ở Group 4")
# POST /models/{model_id}/check     x-permission: model.manage
#   chỉ từ status = check_failed; trả 202 ModelSummary (status = checking); khác → 409 conflict

class ExperimentDetail:                      # thêm
    promoted_from: UUID | None               # exclude_if None; để trang experiment liên kết nguồn

class ReportInsight:                         # mới; lấy từ ExperimentInsight tại lúc xuất report
    weaknesses: list[Weakness]               # tối đa MAX_WEAKNESSES
    matrix: list[RobustnessRow]
    bands: list[tuple[float, float]]
    conclusion: Conclusion

class ReportSnapshot:                        # thêm, schema_version vẫn 1
    insight: ReportInsight | None = None     # exclude_if None; report xuất trước R3 không có
```

Không thêm enum mới. Giao diện dùng các enum đã có từ R2: `AttackSpecStatus`, `ModelStatus`, `ToolJobStatus`, `ExperimentMode`, `SpecCheckName`, `ConclusionCode`, `QuickTryObjectStatus`.

**`design.md`** (đã viết lại theo app hiện có, 2026-10-10) có sẵn:
- tông trạng thái cho `AttackSpecStatus` và `ModelStatus`;
- nhãn mode Khám phá/Chính thức;
- thang màu ma trận độ bền;
- lớp overlay của thử nhanh.

Xem mục 3 của `design.md`. `status-config.ts` khai `Record<Enum, …>` cho các enum này, như quy ước `tech-stack.md` mục 5.1.

### Chốt ở Group 0 (2026-10-10)

Nguồn sự thật: `contracts/python/advertest_contracts/models.py`, mock trong `contracts/mocks/`.

- **Contract.**
  - `ReportInsight` gồm `weaknesses`, `matrix`, `bands`, `conclusion`; bỏ `experiment_id`, `mode`, `partial` vì report chỉ xuất từ experiment Chính thức đã duyệt.
  - `ReportSnapshot.insight` và `ExperimentDetail.promoted_from` dùng `exclude_if None`.
  - `POST /models/{model_id}/check` trả 202 `ModelSummary`; endpoint khung trả 501 cho tới Group 1.
  - Audit action mới `model.rechecked` (chuỗi tự do, không phải enum).
- **Mock mới:**
  - `model_summary/check_failed`;
  - `attack_spec_admin_view/snow_light_{checking,check_failed,rejected_draft}`;
  - `report_insight/weak`, `report_snapshot/approved_grid_insight`;
  - `experiment_detail/promoted_official`.

  Experiment Khám phá có insight dùng mock sẵn có `experiment_detail/completed` + `experiment_insight/weak`.
- **E2E cần worker công cụ.** `scripts/e2e.sh` chạy thêm `advertest-worker --tools` cho máy `local-dev`.
- **E2E cũ đi qua wizard 6 bước.** Có 6 file: `phase_05/{experiment-flow,queue-home,wizard-rules}`, `phase_06/wizard-catalog`, `phase_07/search`, `phase_08/review-flow`.
  - Khi Group 5 xong, người duyệt chuyển các file này sang wizard 3 bước và giữ nguyên mọi assertion. `phase_05/experiment-flow` còn mở tab "Chi phí": chuyển sang section Chi phí trong Tổng quan.
  - Trong lúc chờ, các file này fail trên nhánh `phaser3-frontend` sau Group 5. Đây không phải lỗi của agent.

#### Interface cho test nghiệm thu (`tests/acceptance/phase_r3/`, `frontend/e2e/phase_r3/`)

Test gọi trực tiếp các tên dưới đây. Đổi tên hoặc chữ ký phải qua người duyệt.

- **Group 1:**
  - `backend.app.services.quick_tries.purge_orphans(session, buckets, now) -> int`. Tuổi object tính theo `LastModified` của MinIO so với `now`.
  - `backend.app.reports.render.html(snapshot, read_artifact)` có section tiêu đề "Điểm yếu chính", đặt giữa "Tóm tắt" và "Cấu hình", kèm câu "Điểm yếu là gợi ý để review, không thay cho tiêu chí đạt của protocol".
- **Group 2:** `attacks.selfcheck.fixture_inputs(*, with_estimator: bool, fixtures_dir: Path | None = None) -> SelfcheckInputs`.
- **Group 3:**
  - `advertest_worker.quick_try.QUICK_TRY_BLUR_MIN_SCORE = 0.05`.
  - `run_quick_try` giữ chữ ký R2.
  - `advertest_worker.spec_check` không tự dựng fixture (không dùng `SliceLoader`).
- **Giao diện (E2E):** nhãn, role và `data-testid` dưới đây là interface. Phần còn lại agent frontend tự quyết theo `design.md`.

  | Màn hình | Interface |
  |---|---|
  | Trang experiment | `role=tab` đúng 5 tên; `data-testid="experiment-mode"` ("Khám phá"/"Chính thức"); `data-testid="lifecycle"` chứa `lifecycle-step` có `data-step` ∈ `create, run, analyze, submit, review, report` và `data-state` ∈ `done, current, todo, failed`; heading "Chi phí", "Tái lập" trong Tổng quan; `data-testid="empty-state"`; link "Nâng từ <tên nguồn>" |
  | Ý nghĩa quyết định | `data-testid="decision-meaning"` trong hộp gửi duyệt, cột quyết định review, trang report |
  | Trang chủ | `data-testid="todo-list"` chứa `todo-item` có `data-kind` (engineer: `submit_ready`, `changes_requested`, `promote_ready`; reviewer: `review_pending`, `spec_pending`; admin: `user_pending`, `spec_check_failed`, `model_check_failed`) và số lượng; trống: chữ "Không có việc cần làm", link "Tạo experiment Khám phá" (engineer) |
  | Wizard | `data-testid="wizard-step"` đúng 3 phần tử ("Mục đích", "Model và dữ liệu", "Attack và xác nhận"), bước hiện tại `aria-current="step"`; `radiogroup` "Mode", "Preset" (radio theo `title` của preset); ô chọn nhãn "Protocol", "Model", "Dataset và slice", "Máy chạy" (`<select>` hoặc combobox có `role=option`); nút "Tiếp…", "Tạo experiment"; `data-testid="attack-row"` có `data-attack` = tên spec, chip level có `data-level`, chip bắt buộc có `aria-disabled="true"` và chữ "Protocol yêu cầu"; nút "Bỏ attack…" không có ở attack bắt buộc; ô số chỉ nằm trong `<details>` "Tùy chỉnh nâng cao" |
  | Kết quả | `data-testid="insight-conclusion"`, `weakness` (bấm được, `data-level`; mở tab Failure case với query `attack=<tên>&level=<level>`), `robustness-matrix` chứa `matrix-cell` (4 ô mỗi hàng), `matrix-legend`; nút "Cách đọc"; nút "Nâng lên chính thức" → hộp thoại có ô chọn "Protocol" và nút "Tiếp tục" |
  | Thuật ngữ | phần tử có thuộc tính `data-term`, focus được; tooltip `role="tooltip"` có `id` trùng `aria-describedby`; Esc đóng |
  | Admin catalog | `/admin/attacks`: nút "Tạo attack spec"; ô chọn "Sao chép từ" (điền sẵn từ spec có sẵn); ô "Tên spec", "Tên hiển thị", "Mô tả"; nút "Tạo spec" → trang chi tiết có `data-testid="spec-status"` và `check-item` (7 mục) |
  | Duyệt spec | `/attack-specs/pending`: `data-testid="pending-spec"` mỗi spec; nút "Kích hoạt" (vô hiệu với spec của chính mình, kèm chữ "Bạn đã tạo spec này"), "Từ chối" → hộp thoại có ô "Lý do" và nút "Từ chối" vô hiệu khi trống; hộp thoại kích hoạt có nút "Kích hoạt" |
  | Model | `/admin/models` nút "Đăng ký model"; ô chọn "Framework"; `data-testid="onnx-layouts"` ghi "(1, 4+C, N)" và "boxes/scores/labels"; ô file "File weights"; lỗi đuôi file hiện `role="alert"` có ".onnx" và nút "Đăng ký" vô hiệu; `/admin/models/:id` có `data-testid="model-status"`, `model-check`, nút "Kiểm tra lại" |
  | Thử nhanh | `/quick-try`: ô chọn "Model", "Attack"; ô file "Ảnh"; nút "Chạy thử nhanh"; `data-testid="quick-try-result"`, `not-a-test-result` (có giờ xóa dạng `HH:MM`), `attacked-image` (`src` đổi theo level), `object-table`; `role="slider"` tên "Level" |

### Chốt ở Group 8 (2026-10-11)

Ghi lại quyết định đã chốt trong lúc làm Group 4–7 và review cả phase (`.claude/handoff/phaser3-review.md`). Các mục ở đây ưu tiên hơn mục Behaviour khi hai bên khác nhau.

- **Trang experiment và trang chủ (G4).**
  - Thanh vòng đời: bước Chạy `failed` khi experiment đã kết thúc (`completed`/`cancelled`) mà `run_counts.failed > 0`; Phân tích vẫn `current`. Review: `changes_requested` hoặc `rejected` → `failed`. Report: đã duyệt mà chưa có report hoặc `generating` → `current`; report `failed` → `failed`.
  - Danh sách việc cần làm thay banner "Việc nên làm tiếp" trên `/home`.
  - **Bỏ việc `protocol_draft`** khỏi R3: `ProtocolStatus` không có `draft` nên việc này không có nguồn. Reviewer chỉ có `review_pending`, `spec_pending`. Code frontend gỡ loại việc này ở lần sửa kế tiếp của `features/home/` (R3b); trong lúc chờ, số đếm luôn 0 nên việc không hiện.
- **Wizard 3 bước (G5).**
  - Khám phá thêm attack: gọi lại `POST /experiments/draft` với `attack_spec_ids`. Attack đã có giữ level đã sửa. Bỏ attack chỉ bỏ ở client.
  - Chip level gồm: level của bản nháp, khóa của `level_labels`, mọi giá trị rời rạc và bộ gợi ý (lũy thừa của 2 trong dải; spec cần train: 0.1 và 0.25), tối đa 12.
  - Giới hạn thời gian là thanh trượt bước 5 phút, giá trị gợi ý là `default_time_limit_s` của máy.
  - Slice huấn luyện chọn ở bước 2 khi protocol bắt buộc spec cần train; ở Khám phá thì chọn ngay tại chỗ khi thêm spec cần train.
  - "Nâng lên chính thức" hiện với experiment Khám phá `completed` hoặc `cancelled`, người dùng có `experiment.create`, nằm dưới insight. Lỗi 409 hiện trong hộp thoại.
  - **Bỏ preset "Toàn bộ catalog"** của wizard cũ. Bản nháp Khám phá mặc định đã gồm cả catalog `active` trừ spec cần train.
  - Không còn hộp xác nhận "Chạy experiment": nút "Tạo experiment" ở bước 3 tạo luôn. Nháp lưu dưới khóa `advertest.wizard.v3`; nháp `v1`/`v2` bị bỏ qua.
- **Admin catalog và duyệt spec (G6).**
  - Trường không có trên form (`access`, `art_class`, `cost_model`, `requires_training`/`training`) lấy từ spec "Sao chép từ" cùng adapter. Corruption/occlusion không có spec nguồn thì dùng: không áp dụng, `art_class` null, chỉ CPU. Adapter kiểu attack bắt buộc chọn spec nguồn cùng adapter.
  - Version tự tính ở client (lớn nhất + 1). "Tạo version mới" khóa tên.
  - Chi tiết spec ở `/admin/attacks/:id`, đọc từ `GET /admin/attack-specs` (API không có endpoint chi tiết).
  - Khác biệt khi duyệt spec so với version `active` cùng tên lấy từ `GET /attack-specs`.
  - Mục điều hướng mới: "Spec chờ duyệt" (`attack_catalog.approve`) và "Model" (nhóm Quản trị, `model.manage`).
  - **Lý do từ chối spec đọc qua `GET /audit-log`** (cần `audit.read`). Chạy được vì chỉ admin có `attack_catalog.manage` và admin có `audit.read`; đổi ma trận quyền mà tách hai quyền này thì phải sửa chỗ này. Đề xuất contract thêm `reject_reason` vào `AttackSpecAdminView` làm ở R3b.
- **Thử nhanh (G7).**
  - Gặp 429: link tới lượt đang chạy lấy id lượt vừa tạo, lưu ở `localStorage` (`advertest-quick-try:<user_id>`). Không có id thì chỉ hiện câu thông báo.
  - Tông `QuickTryObjectStatus`: `kept` info, icon scan-eye, "Giữ được"; `lost` danger, circle-x, "Bị mất"; `new` warning, circle-alert, "Phát hiện sai mới".
  - Lượt đang xem nằm trên URL `/quick-try?id=<id>`. Mục điều hướng "Thử nhanh" (`quick_try.use`).
  - Box `kept` trên ảnh tấn công vẽ theo bbox của ảnh sạch, vì contract chỉ có một bbox cho mỗi object. Người xem có thể hiểu nhầm vị trí box; muốn sửa thì cần đổi contract.
- **Attack (G2).**
  - CLI selfcheck dùng `--fixtures-dir` thay cho `--kitti-root`/`--weights`. Estimator chỉ dựng khi spec `requires_gradients`.
  - `validate` chỉ kiểm `art_class` với adapter ART; corruption và occlusion không bị kiểm.
- **E2E cũ (task 23a).** 6 file của Phase 5–8 chuyển sang wizard 3 bước qua `wizardToAttacks`, `keepAttacks`, `setLevels` trong `frontend/e2e/phase_r3/helpers.ts`. Assertion chỉ đổi khi hành vi cũ đã bị spec R3 bỏ:
  - "nhập level ngoài dải" → level chỉ chọn bằng chip trong dải; attack không còn level thì nút "Tạo experiment" bị vô hiệu;
  - preset "Toàn bộ catalog" → bản nháp Khám phá gồm mọi spec `active` không cần train (đếm qua `GET /attack-specs` vì E2E khác kích hoạt thêm spec), thêm `adv_patch` bằng chip sau khi chọn slice huấn luyện;
  - ước lượng tối đa trên thẻ máy chạy và hộp xác nhận → ở tóm tắt cấu hình (thanh dưới trên điện thoại);
  - nháp `v2` của Phase 6 → cùng nội dung lưu dưới khóa `v3`;
  - "Bước 4/6", heading "Xác nhận", tab "Chi phí" → "Bước 3 trên 3", heading "Attack và xác nhận", section "Chi phí" trong Tổng quan.

## Behaviour

### Trang experiment (M1)

- Giữ 5 tab: **Tổng quan**, **Kết quả**, **Failure case**, **Review**, **Report**.
  - Tab Chi phí và Tái lập hiện có chuyển thành hai section thu gọn được, nằm cuối tab Tổng quan, không mất thông tin.
  - Tab Review và Report luôn hiện. Khi chưa có dữ liệu, tab hiện trạng thái trống nói điều gì còn thiếu, kèm nút hành động tiếp theo (`design.md` mục 6). Ví dụ: "Chưa gửi duyệt. Gửi duyệt khi mọi run bắt buộc đã xong."
  - Tham số `?tab=` cũ (`cost`, `repro`) chuyển về Tổng quan, cuộn tới section tương ứng.
- **Thanh vòng đời** ở đầu trang gồm 6 bước: Tạo → Chạy → Phân tích → Gửi duyệt → Review → Report. Trạng thái của mỗi bước suy từ `ExperimentDetail`:
  - Tạo: luôn xong.
  - Chạy: đang làm khi `queued`/`running`; xong khi `completed`/`cancelled`; `failed` hiện màu và icon lỗi.
  - Phân tích: đang làm khi experiment đã kết thúc mà chưa gửi duyệt.
  - Gửi duyệt và Review: theo `review`.
  - Report: theo `report`.

  Experiment Khám phá chỉ có 3 bước Tạo → Chạy → Phân tích, và thêm nút "Nâng lên chính thức" (nguyên tắc 11). Mỗi bước hiện màu + icon + chữ (nguyên tắc 6). Thanh là hàm thuần có unit test theo bảng trạng thái.
- Đầu trang có nhãn mode (Khám phá/Chính thức). Khi có `promoted_from`, trang hiện link "Nâng từ <tên experiment nguồn>".

### Wizard 3 bước (M2)

Wizard 6 bước hiện có gộp thành 3 bước. Logic kiểm tra, ước lượng và tạo experiment giữ nguyên.

1. **Mục đích:**
   - Chọn mode Khám phá hoặc Chính thức. Khám phá dùng protocol `dev`; Chính thức chọn từ danh sách protocol `active`.
   - Chọn preset (Nhanh/Tiêu chuẩn/Chuyên sâu). Mỗi preset là thẻ có `title` và `description` lấy từ `GET /experiment-presets`.
2. **Model và dữ liệu:**
   - Chọn model, dataset/slice và máy chạy bằng danh sách chọn có tên dễ đọc. Chỉ model `ready` được chọn.
   - Class mapping tự chọn khi chỉ có một.
   - Giới hạn chọn bằng thanh trượt có giá trị gợi ý.
3. **Attack và xác nhận:**
   - Wizard gọi `POST /experiments/draft` rồi hiện danh sách attack. Mỗi attack có `display_name`, mô tả, mức sát thực tế, và level dạng chip mang nhãn (`level_labels`). Spec chưa có metadata thì dùng tên kỹ thuật.
   - Khám phá: thêm hoặc bớt attack bằng chip.
   - Chính thức: attack và level bắt buộc của protocol bị khóa, có chú thích "Protocol yêu cầu".
   - Hiện `notes` (ví dụ `slice_too_small`) và ước lượng (`POST /experiments/estimate`, nguyên tắc 5), rồi nút "Tạo experiment".

Quy tắc chung:
- Không còn ô gõ số tự do cho level, ngưỡng hay giới hạn. Ngoại lệ: tham số tìm ngưỡng nâng cao nằm trong phần "Tùy chỉnh nâng cao" thu gọn.
- Luồng "Nhân bản để sửa" (Phase 8) và "Nâng lên chính thức" mở wizard ở bước 3, điền sẵn từ `ExperimentClone`. Bản nháp nâng lên mang `promoted_from`.
- Experiment tạo qua wizard mới có config giống hệt (`config_sha256` bằng nhau) experiment tạo bằng `POST /experiments/draft` với cùng lựa chọn rồi `POST /experiments`.

### Kết quả và insight (M3, M4)

- Tab Kết quả mở đầu bằng `GET /experiments/{id}/insight`:
  1. **Câu kết luận** (`conclusion.text`), kèm nhãn "Kết quả một phần" khi `partial`.
  2. **Danh sách điểm yếu** (tối đa 5). Mỗi dòng gồm attack (`display_name`), level kèm nhãn, class (nếu có), và mức sụt hoặc điểm gãy. Bấm vào dòng thì mở tab Failure case, đã lọc theo attack và level đó.
  3. **Ma trận độ bền:** hàng là attack, 4 cột là dải cường độ (`bands`, ghi "0–25% dải" …), mỗi ô ghi số phần trăm và tô theo thang màu (`design.md` mục 3). Ô `null` ghi "Chưa chạy". Cạnh ma trận có chú thích thang màu.
- Ngay dưới đó là nút "Nâng lên chính thức", chỉ hiện với experiment Khám phá đã kết thúc:
  - Nút mở hộp chọn protocol `active`, rồi gọi `POST /experiments/{id}/promote` và mở wizard bước 3.
  - Lỗi 409 hiện câu giải thích theo `design.md` mục 7.
- Biểu đồ hiện có (đường mức sụt, điểm gãy, xếp hạng attack) và ma trận đều có:
  - **câu kết luận** một dòng phía trên. Câu sinh có quy tắc ở frontend từ cùng dữ liệu của biểu đồ (hàm thuần, có unit test); không dùng câu chung chung;
  - nút **"Cách đọc"** mở đoạn giải thích 2–4 câu: trục, màu, đường ngưỡng.
- `no_data`: tab hiện trạng thái trống ("Chưa có run nào có kết quả"), không hiện ma trận rỗng.

### Thuật ngữ (M4)

- Bảng thuật ngữ `frontend/src/copy/glossary.ts` có ít nhất các mục: mAP, AP50, mức sụt tương đối, điểm gãy, level/cường độ, attack white-box, corruption, occlusion, patch, slice, protocol, fingerprint, Khám phá, Chính thức.
- Mỗi mục có định nghĩa tối đa 2 câu.
- Component `Term` hiện thuật ngữ có gạch chân chấm; hover, focus hoặc chạm thì mở tooltip. Tooltip dùng được bằng bàn phím và có `aria-describedby`.
- Lần xuất hiện đầu tiên của mỗi thuật ngữ trong tab Kết quả, wizard và thử nhanh dùng `Term`.

### Ý nghĩa quyết định (M5)

- Bảng `frontend/src/copy/decisions.ts` mô tả 5 quyết định: Gửi duyệt, Approve, Yêu cầu sửa, Từ chối, Xuất report. Mỗi quyết định có 3 dòng: điều gì xảy ra ngay, ai làm bước tiếp theo, và có đảo ngược được không. Nội dung khớp hành vi Phase 8, ví dụ: "Gửi duyệt: experiment bị khóa, không chạy thêm run được."
- Bảng này hiện ở 3 nơi:
  - hộp xác nhận gửi duyệt: dòng của Gửi duyệt;
  - cột quyết định của màn hình review: cả 3 quyết định review, dòng đang chọn được nhấn;
  - trang report: một đoạn "Report này có nghĩa là gì", gồm verdict và nguyên tắc 8.

### Trang chủ "việc cần làm" (M6)

- `/home` mở đầu bằng danh sách **việc cần làm** theo vai trò, mỗi việc là một link tới đúng nơi xử lý:
  - **engineer:** experiment của mình đã xong mà chưa gửi duyệt; experiment bị yêu cầu sửa; experiment Khám phá đã xong có thể nâng lên chính thức.
  - **reviewer:** review đang chờ; spec attack `pending_approval` (của người khác). (Protocol `draft` bỏ khỏi R3, xem Chốt ở Group 8.)
  - **admin:** tài khoản chờ duyệt; spec `check_failed`; model `check_failed`.
- Mỗi việc có số lượng. Khi không có việc nào, trang hiện "Không có việc cần làm" và một hành động gợi ý (engineer: "Tạo experiment Khám phá").
- Danh sách lấy từ endpoint hiện có. Hàm gom việc là hàm thuần, có unit test theo từng vai trò. Người có nhiều vai trò thấy gộp, không trùng.

### Admin catalog và model (M7)

- **Danh sách spec của admin** (`/admin/attacks`, mở rộng trang hiện có):
  - Cột trạng thái (`AttackSpecStatus`), tên dễ đọc, version, adapter.
  - Lọc theo trạng thái.
- **Tạo spec:**
  - Chọn adapter từ `GET /attack-adapters`.
  - Form tham số (`fixed_params`) sinh từ `params_schema`: enum thành danh sách chọn, số có `minimum`/`maximum` thành ô số có giới hạn, boolean thành công tắc. Schema có kiểu ngoài các kiểu này thì form báo "Adapter này chưa hỗ trợ tạo qua giao diện".
  - Nhập dải level (`primary_param`) và metadata: tên, mô tả, mức sát thực tế, nhãn level.
  - Muốn "Tạo version mới" từ spec có sẵn thì form điền sẵn mọi trường.
  - Lỗi 422 và 409 hiện đúng trường gây lỗi.
- **Chi tiết spec:**
  - Kết quả tự kiểm tra: 7 mục theo thứ tự `SpecCheckName`, mỗi mục đạt/không đạt kèm `details`, cộng `error` nếu có.
  - Đang `checking` thì trang tự cập nhật (polling 2 giây theo `tech-stack.md` mục 5).
  - Nút "Kiểm tra lại" khi `check_failed`. Sửa metadata bằng hộp thoại.
  - Với `draft` bị từ chối, trang hiện lý do và giải thích rằng muốn tiếp tục thì tạo version mới (Chốt ở Group 4 của R2).
- **Reviewer duyệt spec:**
  - Trang `/attack-specs/pending` (`attack_catalog.approve`) liệt kê spec chờ duyệt, kèm kết quả tự kiểm tra và khác biệt so với version `active` trước đó (nếu có).
  - "Kích hoạt" có hộp xác nhận nêu hệ quả: version cũ chuyển `retired`.
  - "Từ chối" bắt buộc nhập lý do.
  - Spec do chính mình tạo thì nút bị vô hiệu kèm lý do (nguyên tắc 1). Backend vẫn là lớp chặn.
- **Đăng ký model** (`/admin/models`, `model.manage`):
  - Danh sách model, cột trạng thái (`ModelStatus`).
  - Form đăng ký: tên, framework (`torchvision`/`onnx`), kiến trúc (torchvision: danh sách chọn 3 kiến trúc cho phép), danh sách class, `input_size`.
  - File được upload thẳng lên presigned URL, có thanh tiến độ. Chặn ngay ở client file không phải `.onnx`/`.safetensors`, hoặc lớn hơn 500 MB.
  - Form ONNX nêu rõ hai layout đầu ra được hỗ trợ: kiểu YOLO `(1, 4+C, N)` và `boxes/scores/labels` đã qua NMS. Model không theo hai layout này sẽ `check_failed`.
  - Chi tiết model hiện `ModelCheckResult`. Nút "Kiểm tra lại" khi `check_failed` gọi `POST /models/{id}/check`.

### Thử nhanh (M8)

- Trang `/quick-try` (`quick_try.use`):
  - Chọn model `ready`, attack `active` (attack cần gradient bị ẩn khi model không có gradient; patch luôn ẩn) và preset.
  - Chọn ảnh JPEG/PNG bằng kéo-thả hoặc chọn file. Client chặn file > 10 MB.
- Sau khi gửi, trang hiện trạng thái `queued`/`running`, polling 2 giây. Gặp 429 thì hiện "Bạn đang có một lượt thử chưa xong", kèm link tới lượt đó.
- **Kết quả:**
  - Ảnh sạch và ảnh bị tấn công đặt cạnh nhau (điện thoại: xếp dọc), box vẽ trên canvas theo lớp overlay của `design.md` mục 3: ảnh sạch dùng màu "dự đoán ảnh sạch"; trên ảnh tấn công, `kept` cam liền, `lost` đỏ dày 3 px có ×, `new` cam nét đứt 3-3.
  - **Thanh trượt level** có nhãn level, đổi ảnh tấn công và bảng ngay, không gọi lại API.
  - Bảng theo object: class, score sạch, score sau tấn công, trạng thái. Kèm số đếm `kept`/`lost`/`new` của level đang chọn.
- Nhãn **"Không phải kết quả kiểm thử"** luôn hiện ở đầu kết quả (`not_a_test_result`), màu `--threshold`, kèm câu giải thích: không tạo experiment, không vào report, ảnh tự xóa sau 24 giờ (ghi giờ xóa từ `expires_at`).
- Gặp 410: "Lượt thử đã hết hạn và bị xóa", kèm nút "Thử lại".

### Phong cách giao diện

- Màn hình mới và trang được sửa theo `design.md` (đã mô tả đúng app hiện có):
  - khung và component sẵn có: `AppShell`, `PageHero`/`PageHeader`, `.panel`, `.seg`, `components/ui`, `StatusBadge`, `EmptyState`, `ConfirmDialog`;
  - token và lớp trong `frontend/src/index.css`.

  Mục tiêu: người dùng không phân biệt được trang nào làm ở R3.
- Không thêm token, màu hex, font hay họa tiết mới (`design.md` mục 8). Ngoại lệ duy nhất: các màu overlay đã khai trong `design.md` mục 3.
- Trạng thái mới (spec, model, mode) dùng tông và icon ở `design.md` mục 3, khai trong `status-config.ts` bằng `Record<Enum, …>` theo `tech-stack.md` mục 5.1.
- Trình vẽ box (`components/case-viewer/`) bổ sung các phần `design.md` mục 3 ghi là "Phase R3 bổ sung":
  - ground truth nét đứt 8-4;
  - nhãn × cho object bị mất;
  - lớp "phát hiện sai mới" (cam, nét đứt 3-3).

  Thử nhanh và trình xem case dùng chung trình vẽ này.

### Docker: worker công cụ (tồn đọng R2)

- `docker/compose.yaml` thêm service `worker-tools`: cùng image với worker, lệnh `advertest-worker --tools`, token worker riêng lấy từ `ENV_FILE` (thêm vào `.env.example`).
- Image worker chứa fixture mà `spec_check` và `model_check` cần: 4 ảnh KITTI fixture, `yolov8n.pt` và nhãn. Fixture chép lúc build từ `tests/fixtures/` đã kiểm sha256. Thiếu fixture thì build fail.
- `make up` xong thì luồng admin tạo spec → kiểm tra → reviewer duyệt chạy hết trong Docker.

### Gộp dựng fixture selfcheck (tồn đọng R2)

- `attacks/selfcheck.py` có hàm công khai `fixture_inputs(*, with_estimator: bool, fixtures_dir: Path | None = None) -> SelfcheckInputs`. `backend/worker/advertest_worker/spec_check.py` gọi lại hàm này, bỏ code dựng fixture riêng.
- CLI selfcheck và worker cho cùng `SpecCheckResult.items` trên cùng spec, cùng seed.

### Làm mờ rộng hơn cho thử nhanh (tồn đọng R2, nguyên tắc 9)

- Vùng làm mờ của **mọi ảnh** trong một lượt (ảnh sạch và mọi level) là hợp của vùng `rule_v1` tính từ:
  - mọi detection có score ≥ `QUICK_TRY_BLUR_MIN_SCORE = 0.05` (hằng số trong `backend/worker/`),
  - trên ảnh sạch và trên **mọi** level.

  Không còn lọc theo `operating_conf`. Lớp class được làm mờ giữ theo `rule_v1` (người, xe).
- Bảng object và nhãn cho attack vẫn dùng `operating_conf` như R2. Chỉ vùng làm mờ thay đổi.
- Một người hay xe mà model chỉ thấy ở một level vẫn bị làm mờ ở mọi ảnh của lượt đó.

### Kiểm lại model (tồn đọng R2)

- `POST /models/{id}/check`:
  - Chỉ nhận model `check_failed`; chuyển model về `checking`, xếp job `model_check` mới và ghi audit `model.rechecked`.
  - Model ở trạng thái khác trả 409.
  - Weights đã xóa khỏi storage thì trả 409 kèm `detail` nói rõ.

### Dọn object MinIO mồ côi (tồn đọng R2)

- Vòng dọn thử nhanh hiện có (10 phút, `purge_expired`) xóa thêm object dưới `quick-tries/<id>/` khi:
  - không có dòng `quick_tries` với `id` đó, hoặc dòng đã có `deleted_at`;
  - **và** object cũ hơn 30 phút (dài hơn thời hạn presigned PUT 15 phút).
- Hàm `purge_orphans(session, buckets, now) -> int` trả số object đã xóa. Lệnh `advertest-admin purge-quick-tries` gọi cả hai hàm.

### `validate` kiểm `art_class` (tồn đọng R2)

- `PerturbationRegistry.validate(spec)` báo `InvalidSpec` khi adapter `art.evasion` (hoặc adapter ART khác) nhận `art_class` không thuộc danh sách lớp ART mà builder hỗ trợ. Vì vậy `POST /admin/attack-specs` trả 422 ngay, không để lỗi lộ ra ở mục 1 của selfcheck.
- Spec seed vẫn validate được; `spec_sha256` không đổi.

### Insight trong report PDF

- Khi xuất report, backend tính `ExperimentInsight` của experiment và ghi vào `snapshot.insight`; snapshot vẫn bất biến sau khi xuất.
- Report PDF thêm section **"Điểm yếu chính"** ngay sau phần tóm tắt, gồm câu kết luận, danh sách điểm yếu và ma trận độ bền (bảng có số, tô màu theo thang ở trên).
- Section ghi rõ: "Điểm yếu là gợi ý để review, không thay cho tiêu chí đạt của protocol" (nguyên tắc 2, 7).
- Report đã xuất trước R3 không có `insight`. Trang xác minh và `json_sha256` của chúng không đổi; template PDF bỏ qua section khi `insight` là `None`.

## Decisions

- **Tách landing (11a) và phần còn lại của 11b sang Phase R3b; R3 bỏ phụ thuộc 11a.** *Lý do:* 11a chưa làm, phạm vi R3 quá lớn. Người dùng chốt 2026-10-10.
- **M1–M8 suy từ các mục UX của R4b**, như bảng ở Scope. Người dùng chốt 2026-10-10.
- **Làm mờ thử nhanh dùng ngưỡng 0.05 và hợp vùng trên mọi ảnh của lượt.** *Lý do:* nguyên tắc 9; phương án làm mờ toàn ảnh làm ảnh khó đọc. Người dùng chốt 2026-10-10.
- **R3 xử lý cả 4 tồn đọng R2:** recheck model, insight trong report PDF, dọn object mồ côi, `validate` kiểm `art_class`. Người dùng chốt 2026-10-10.
- **Câu kết luận của từng biểu đồ sinh ở frontend; câu kết luận chung lấy từ backend** (`conclusion.text`). *Lý do:* câu chung đã có ở R2 và report dùng lại; câu của từng biểu đồ chỉ để hiển thị.
- **Tab Chi phí và Tái lập gộp vào Tổng quan**, để trang chỉ còn 5 tab như roadmap.
- **`design.md` viết lại theo app hiện có** (màu, font Inter, hero/gradient, tông trạng thái, overlay `BOX_COLORS`); R3 theo đúng file này. *Lý do:* giữ app nhất quán; không có đợt đổi giao diện toàn cục. Người dùng chốt 2026-10-10.
- **Chuỗi giao diện mới** (thuật ngữ, ý nghĩa quyết định, thử nhanh) nằm ở `frontend/src/copy/`. Chuỗi cũ để R3b gom.
- **Ảnh case hiển thị theo `content_box`** (vùng ảnh thật trong letterbox), case cũ (`null`) giữ khung vuông; lưới failure case 3 cột. Người dùng duyệt đề xuất contract 001 ngày 2026-10-12.
- **Model chưa có experiment hay lượt thử nhanh thì xóa hẳn; đã dùng thì chỉ lưu trữ** (`archived_at`, ẩn khỏi wizard và thử nhanh, khôi phục được). *Lý do:* `mission.md` nguyên tắc 3. Người dùng chốt 2026-10-12 (đề xuất contract 002).
- **`.pt` từ web chỉ được mở trong sandbox chuyển đổi** (container `network_mode: none`, rootfs chỉ đọc, không capability, không bí mật; tiến trình con có timeout và rlimit; torchvision nạp bằng `weights_only=True`). Worker công cụ chỉ chuyển byte qua volume spool và đọc metadata từ header safetensors. Kết quả đăng ký như safetensors thường, vẫn qua `model_check`. Người dùng chọn hướng này và duyệt sửa `mission.md` nguyên tắc 10 ngày 2026-10-12 (đề xuất contract 003).
- **Ai thấy model nào:** admin và reviewer thấy mọi model; engineer thấy model mình đăng ký và model của người có vai trò admin (catalog dùng chung). Backend chặn: `GET /models` chỉ trả model thấy được, `GET /models/{id}` của engineer khác → 404, ước lượng/tạo experiment và thử nhanh với model đó → 422. Experiment của người khác vẫn hiện tên model. Người dùng chốt 2026-10-12.
- **Chỉ người đăng ký model hoặc admin thấy nút xóa, lưu trữ, kiểm lại, thêm mapping** (`ModelSummary.owner_id`, `owner_name`); người khác thấy ai đã đăng ký. Người dùng chốt 2026-10-12.
- **Class mapping tạo trong form đăng ký model, gợi ý theo preset `kitti-coco` hoặc tên trùng, sửa được, bỏ qua được** (thêm sau ở trang chi tiết model). Người dùng chốt 2026-10-12.
- **Tên nhánh `phaser3-<agent>`; test ở `tests/acceptance/phase_r3/` và `frontend/e2e/phase_r3/`; merge vào `dev`.** *Lý do:* như R1, R2.

## Context

- `mission.md` nguyên tắc 1, 2, 5, 6, 7, 8, 9, 10, 11; `design.md` mục 3, 6, 7, 8; `tech-stack.md` mục 5.1.
- API R2: `specs/2026-10-09-phase-r2-backend/requirements.md`, mục Data / Fields, "Chốt ở Group 0" (bảng quyền) và Behaviour.
- Giao diện hiện có:
  - wizard 6 bước: `frontend/src/features/wizard/state.ts` `STEPS`;
  - tab experiment: `frontend/src/features/experiments/ExperimentDetailPage.tsx` `TABS`;
  - thanh quy trình nhóm: `frontend/src/features/flow/`;
  - trang chủ: `frontend/src/pages/HomePage.tsx`;
  - admin attack: `frontend/src/pages/admin/AttacksPage.tsx`;
  - trình vẽ box: `frontend/src/components/case-viewer/`.
- Làm mờ: `ml_core/privacy/regions.py` (`rule_v1`, `MIN_SCORE = 0.25` cho failure case); thử nhanh: `backend/worker/advertest_worker/quick_try.py` `blurred_png`.
- Prototype UI của một thành viên trên `other/main` (`747e72b`, chưa merge, contract khác R2) chỉ để tham khảo ý tưởng. Không merge, không chép.

## Open Questions

- [ ] (Từ R2) Hai layout đầu ra ONNX có đủ cho model người dùng dự kiến đăng ký không? R3 ghi rõ giới hạn trên form; ghi nhận model nào không vừa khi demo.
