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

Cuối phase, mọi test nghiệm thu Phase 0–8, R1 và R2 vẫn pass, và golden R1 vẫn khớp.

## Out of Scope

- **Áp `design.md` cho toàn ứng dụng** (các mục 11b), gồm: token toàn cục mới, đổi font sang Be Vietnam Pro, nút chuyển sáng/tối, vùng A/B/C cho mọi trang, gom toàn bộ câu chữ vào `copy/vi.ts`, đổi font và màu của report PDF. Phần này chuyển sang **Phase R3b**, làm cùng landing (11a). R3 dùng token và component sẵn có; màn hình mới vẫn tuân theo ngữ nghĩa màu, màu trạng thái, lớp overlay và mục 7, 8 của `design.md`.
- Landing page (Phase 11a, chuyển sang R3b).
- Thuật toán attack mới, adapter mới, và upload `.pt` hay pickle qua web (`mission.md` nguyên tắc 10).
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

**`design.md`** (Group 0, người duyệt) bổ sung:
- màu trạng thái cho `AttackSpecStatus` và `ModelStatus`;
- nhãn mode Khám phá/Chính thức;
- thang màu của ma trận độ bền.

Chi tiết ở mục Behaviour "Màu và trạng thái mới". `status-config.ts` khai `Record<Enum, …>` cho các enum này, như quy ước `tech-stack.md` mục 5.1.

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
  3. **Ma trận độ bền:** hàng là attack, 4 cột là dải cường độ (`bands`, ghi "0–25% dải" …), mỗi ô ghi số phần trăm và tô theo thang màu (mục Màu và trạng thái mới). Ô `null` ghi "Chưa chạy". Cạnh ma trận có chú thích thang màu.
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
  - **reviewer:** review đang chờ; spec attack `pending_approval` (của người khác); protocol `draft` của mình.
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
  - Ảnh sạch và ảnh bị tấn công đặt cạnh nhau (điện thoại: xếp dọc), box vẽ trên canvas theo lớp overlay của `design.md` mục 3: `kept` cyan liền, `lost` magenta có ×, `new` magenta đứt.
  - **Thanh trượt level** có nhãn level, đổi ảnh tấn công và bảng ngay, không gọi lại API.
  - Bảng theo object: class, score sạch, score sau tấn công, trạng thái. Kèm số đếm `kept`/`lost`/`new` của level đang chọn.
- Nhãn **"Không phải kết quả kiểm thử"** luôn hiện ở đầu kết quả (`not_a_test_result`), màu `--threshold`, kèm câu giải thích: không tạo experiment, không vào report, ảnh tự xóa sau 24 giờ (ghi giờ xóa từ `expires_at`).
- Gặp 410: "Lượt thử đã hết hạn và bị xóa", kèm nút "Thử lại".

### Màu và trạng thái mới (bổ sung `design.md`)

| Trạng thái | Màu | Icon (lucide) | Nhãn |
|---|---|---|---|
| spec `draft` | `--ink-muted` | `file-pen` | Nháp |
| spec `checking`, model `checking` | `--detect` | `loader` | Đang kiểm tra |
| spec `check_failed`, model `check_failed` | `--fail` | `x-circle` | Kiểm tra không đạt |
| spec `pending_approval` | `--threshold` | `hourglass` | Chờ duyệt |
| spec `active` | `--approved` | `badge-check` | Đang dùng |
| spec `retired` | `--ink-muted` | `archive` | Đã thay thế |
| model `ready` | `--approved` | `check-circle` | Sẵn sàng |

- **Mode:** Khám phá dùng viền `--ink-muted` với icon `flask-conical`; Chính thức dùng viền `--detect` với icon `shield-check`. Mode không dùng `--approved`, vì màu này chỉ dành cho "đã chấp nhận".
- **Thang màu ma trận độ bền** (theo `max_relative_drop`):

  | Mức sụt | Màu ô |
  |---|---|
  | < 0.1 | `--surface` |
  | 0.1–0.3 | `--fail` 20% |
  | 0.3–0.5 | `--fail` 50% |
  | ≥ 0.5 | `--fail` 85% |

  Ô ≥ `WEAKNESS_DROP` có thêm viền 2 px `--fail`. Ô `null` dùng nền gạch chéo xám. Số luôn hiện trong ô, để không phụ thuộc vào màu.

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

- **Tách phần áp `design.md` toàn ứng dụng (11b) và landing (11a) sang Phase R3b; R3 bỏ phụ thuộc 11a.** *Lý do:* 11a chưa làm, phạm vi R3 quá lớn; thứ tự cắt giảm vốn xếp phần này sau M1–M8. Người dùng chốt 2026-10-10.
- **M1–M8 suy từ các mục UX của R4b**, như bảng ở Scope. Người dùng chốt 2026-10-10.
- **Làm mờ thử nhanh dùng ngưỡng 0.05 và hợp vùng trên mọi ảnh của lượt.** *Lý do:* nguyên tắc 9; phương án làm mờ toàn ảnh làm ảnh khó đọc. Người dùng chốt 2026-10-10.
- **R3 xử lý cả 4 tồn đọng R2:** recheck model, insight trong report PDF, dọn object mồ côi, `validate` kiểm `art_class`. Người dùng chốt 2026-10-10.
- **Câu kết luận của từng biểu đồ sinh ở frontend; câu kết luận chung lấy từ backend** (`conclusion.text`). *Lý do:* câu chung đã có ở R2 và report dùng lại; câu của từng biểu đồ chỉ để hiển thị.
- **Tab Chi phí và Tái lập gộp vào Tổng quan**, để trang chỉ còn 5 tab như roadmap.
- **Chuỗi giao diện mới** (thuật ngữ, ý nghĩa quyết định, thử nhanh) nằm ở `frontend/src/copy/`. Chuỗi cũ để R3b gom.
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
