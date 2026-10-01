# Requirements: Phase 7 — Tự tìm ngưỡng

## Scope

Tìm **điểm gãy** của model với từng attack: mức cường độ nhỏ nhất làm model suy giảm vượt ngưỡng do người dùng đặt. Kết quả của phase gồm:

1. **Thuật toán tìm kiếm**: quét thô trên tập con → chia đôi → xác nhận trên toàn slice.
2. **Giới hạn trên số điểm đánh giá** tính trước, để hiển thị chi phí tối đa.
3. **Khoảng tin cậy bootstrap** cho mức sụt và cho điểm gãy.
4. **Ba loại ngưỡng**: sụt tương đối, sụt tuyệt đối, tỷ lệ tấn công thành công, mỗi loại có thể áp dụng cho một class cụ thể.
5. **Trạng thái kết quả tìm kiếm** rõ ràng, kể cả khi dừng giữa chừng.
6. **Wizard** có chế độ "Tự tìm ngưỡng" cho từng attack; **trang kết quả** hiển thị điểm gãy, quỹ đạo tìm kiếm và so sánh giữa các attack.

Cuối phase: chọn ngưỡng sụt 20% cho PGD, hệ thống trả về điểm gãy kèm khoảng tin cậy, và điểm này khớp với đường cong quét lưới của cùng attack.

## Out of Scope

- Tìm ngưỡng cho attack cần huấn luyện (`adv_patch`). Mỗi điểm đánh giá sẽ phải train một patch mới, chi phí quá lớn cho MVP. Wizard hiển thị chế độ này ở trạng thái không khả dụng kèm giải thích.
- Tìm kiếm nhiều tham số cùng lúc.
- Ngưỡng lấy từ protocol (Phase 8). Trong phase này người dùng tự đặt ngưỡng; Phase 8 sẽ điền sẵn và khóa theo protocol.
- Dừng sớm (chỉ áp dụng cho quét lưới).

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

| Thay đổi | Nội dung |
|---|---|
| `SearchStatus` | Thêm `failed` |
| `AttackConfig.search` | Đầy đủ các trường: `threshold_kind`, `threshold`, `class_filter` (tùy chọn, **một** class đích: `str | None`, thay cho `list[str]` hiện có), `lo`, `hi`, `tol`, `coarse_n` (3–8, mặc định 4), `subset_size` (≥ 2, mặc định 100), `bootstrap_samples` (0–1000, mặc định 200; 0 là tắt) |
| `RunResult` | Thêm `scope` (`full` / `subset`), `search_order` (null với quét lưới), `predictions_key` (khóa lưu prediction theo ảnh) |
| `Manifest.fingerprint_inputs` | Thêm `eval_image_ids_sha256` (tập ảnh thực sự được đánh giá) |
| `SearchResult` | Thêm `metric_kind`, `max_points`, `points_used`, `message` (khi `failed`); mỗi phần tử `trajectory` thêm `drop_ci` (null nếu chưa tính) và `synthetic` (điểm không cần chạy, xem Behaviour); validator: `breaking_point` có khi và chỉ khi `status` là `found` hoặc `non_monotonic` |
| `EstimateResponse` | Thêm `searches[]`: `attack_spec_id`, `max_points`, `max_subset_points`, `max_full_points`, `max_seconds` (null khi thiếu profile); thêm `max_total_seconds` (null khi có run hoặc search thiếu ước lượng) và `max_exceeds_limit`; `runs` được phép rỗng khi `searches` không rỗng |
| `ExperimentDetail` | Thêm `search_results[]` (cập nhật cả khi đang chạy) |
| API nội bộ | `POST /internal/worker/experiments/{id}/runs`: worker tạo run động cho điểm tìm kiếm kế tiếp |

**Chi tiết chốt ở Group 0** (người duyệt, 2026-10-01; code trong `contracts/python/advertest_contracts/models.py`):

- **Hash cũ không đổi:** trường mới của model đã có (`RunResult`/`RunView` `scope`, `search_order`, `predictions_key`; `FingerprintInputs.eval_image_ids_sha256`; `ClassRunMetrics.attack_success_rate`; `BundleRun.scope`, `search_order`) bị bỏ khỏi JSON khi mang giá trị mặc định (`exclude_if`), như `patch_key` của Phase 6. Config, fingerprint và manifest cũ giữ nguyên hash.
- **Enum mới:** `EvalScope` (`full`, `subset`) cho `scope`; `SearchStage` (`coarse`, `bisect_subset`, `confirm`, `bisect_full`, `done`) cho giai đoạn tìm kiếm.
- **`SearchResult` tạm thời và cuối:** thêm `stage`; `status` null khi và chỉ khi `stage` khác `done` (bản tạm thời gửi sau mỗi điểm, `SearchStatus` không có giá trị "đang chạy"). Dòng tiến độ của giao diện đọc `points_used`, `max_points`, `bracket`, `stage`. `breaking_point = bracket[1]`. `class_filter` lặp lại trong kết quả. `metric_kind` suy từ `threshold_kind` và `class_filter`: `map50`, `class_ap50`, `asr`, `class_asr`. `points_used` = số điểm không `synthetic` của `trajectory` và ≤ `max_points`; `order` liên tục từ 0; mỗi run tối đa một điểm. Điểm `synthetic` có `run_id = null`, `drop = 0`; `drop_ci` chỉ ở điểm `full`. `near_threshold = false` khi chưa tính bootstrap.
- **`SearchConfig`:** `threshold` trong (0, 1] ở contract (cận `absolute_drop` ≤ mAP sạch kiểm ở backend); `tol < hi − lo` ở contract; `tol` vẫn bắt buộc với tham số rời rạc (không dùng).
- **ASR theo class:** `ClassRunMetrics.attack_success_rate` (tùy chọn) để `threshold.py` tính đại lượng `class_asr` từ `RunResult` (plan task 10).
- **API nội bộ:** body `SearchRunCreate` (`lease_id`, `attack_spec_id`, `level`, `scope`, `search_order`) trả `BundleRun` (`201`); `POST .../search-result` đổi body thành `SearchResultReport` (`lease_id`, `result`) như mọi request khác của worker, trả `204`; bản sau thay bản trước của cùng attack.
- **Chạy tiếp sau gián đoạn:** `WorkerJobBundle.search_results` chứa `SearchResult` mới nhất của từng attack tìm ngưỡng; thuật toán là máy trạng thái thuần nên worker dựng lại trạng thái bằng cách nạp lại `trajectory` theo `order` (không cần lưu trạng thái riêng trong checkpoint). Run tìm ngưỡng trong bundle có `search_order`; `runs` được rỗng khi mọi attack ở chế độ tìm ngưỡng.
- **`ExperimentDetail`:** `attack_ranking` chỉ được chứa attack quét lưới (validator); `search_results` chỉ chứa attack tìm ngưỡng, mỗi attack tối đa một.
- **`bracket` của kết quả tạm thời** (review Group 0, chỉnh ở review Group 1): khoảng hẹp nhất suy ra được từ các điểm đã có của giai đoạn hiện tại (cận dưới là level lớn nhất chưa gãy nằm dưới cận trên, cận trên là level nhỏ nhất đã gãy), kể cả trong giai đoạn quét thô; chưa có điểm gãy thì cận trên là `hi`, chưa có điểm chưa gãy thì cận dưới là `lo`. Ở giai đoạn xác nhận và dịch khoảng (điểm toàn slice), cận nào các điểm toàn slice chưa suy ra được thì giữ cận lấy từ các điểm tập con, để khoảng không nhảy về `[lo, hi]`.
- **Tiến độ và hàng đợi khi có tìm ngưỡng** (review Group 0): `ExperimentSummary.progress.images_total` chỉ tính ảnh của các run đã tạo (tăng dần khi worker tạo run động); giao diện dùng dòng tiến độ tìm kiếm cho attack tìm ngưỡng. `queue.ahead_seconds` tính phần tìm ngưỡng của experiment đứng trước bằng `max_seconds` trừ thời gian xử lý đã dùng cho attack đó (không âm).
- **`PassCriterion.class_filter`** đổi thành `str | None` cùng kiểu với `SearchConfig.class_filter` (Phase 8 điền cấu hình tìm ngưỡng từ protocol).
- **`EstimateResponse`:** `max_total_seconds` null khi không có attack tìm ngưỡng; `max_exceeds_limit` chỉ `true` khi có attack tìm ngưỡng; `exceeds_limit` kéo theo `max_exceeds_limit`; attack của `searches` không có run quét lưới; `missing_profiles` gồm cả attack tìm ngưỡng có `max_seconds = null`.

## Behaviour

### Đại lượng dùng để so với ngưỡng

| `threshold_kind` | Không có `class_filter` | Có `class_filter` |
|---|---|---|
| `relative_drop` | `relative_drop` trên mAP@0.5 | Như vậy nhưng trên AP@0.5 của class đó |
| `absolute_drop` | `absolute_drop` trên mAP@0.5 | Trên AP@0.5 của class đó |
| `attack_success_rate` | ASR trên mọi object | ASR chỉ tính object của class đó |

- `relative_drop` và `attack_success_rate`: ngưỡng trong (0, 1]. `absolute_drop`: ngưỡng trong (0, mAP sạch].
- Mức sụt bằng hoặc vượt ngưỡng được coi là **gãy**.

### Tập con
- Tập con = `subset_size` ảnh đầu tiên của slice sau khi sắp theo `hash(seed, image_id)`. Xác định, không phụ thuộc thứ tự lưu trữ. Khóa sắp xếp (review Group 1): `sha256(canonical_json({"purpose": "search_subset", "seed": seed, "image_id": image_id}))`, `seed` là seed của attack; đổi khóa này làm đổi tập con và fingerprint của mọi run trên tập con.
- Nếu slice có không quá `subset_size` ảnh: tập con là toàn slice và bỏ qua giai đoạn xác nhận.

### Thuật toán
Ký hiệu `d(x, S)` là mức sụt ở level `x` trên tập ảnh `S`.

1. **Quét thô (trên tập con):** `coarse_n` level cách đều từ `lo` đến `hi` (với tham số rời rạc: `coarse_n` giá trị cách đều theo chỉ số, luôn gồm giá trị nhỏ nhất và lớn nhất; `lo`, `hi` phải là giá trị của spec). Luôn đánh giá đủ mọi level thô, theo thứ tự tăng dần (Group 1).
   - `d(lo) ≥ ngưỡng` → chuyển sang xác nhận `lo` trên toàn slice; nếu vẫn gãy → `below_min`; nếu không gãy → dịch lên từ `lo` như bước 3.
   - `d(hi) < ngưỡng` → chuyển sang xác nhận `hi` trên toàn slice; nếu vẫn không gãy → `not_reached`; nếu gãy → dịch xuống từ `hi` như bước 3.
   - Ngược lại: khoảng `[a, b]` = hai level liền kề đầu tiên mà `d(a) < ngưỡng ≤ d(b)`.
   - Nếu các mức sụt thô không tăng dần (một điểm thấp hơn điểm trước quá 0.02) → ghi nhận cờ không đơn điệu.
2. **Chia đôi (trên tập con):** lặp `m = (a + b) / 2`, cập nhật `a` hoặc `b`, cho đến khi `b − a ≤ tol`. Với tham số rời rạc: chia đôi theo chỉ số, dừng khi `a` và `b` liền kề.
3. **Xác nhận (trên toàn slice):** đánh giá `a` và `b`.
   - `d(a) < ngưỡng ≤ d(b)` → xong.
   - `d(b) < ngưỡng` → dịch lên: `a = b`, `b` = level thô kế tiếp phía trên; đánh giá `b` trên toàn slice; còn chưa gãy thì `a = b` và lặp với level thô kế tiếp (dịch từng ô thô, quyết định Group 1); `b = hi` mà vẫn không gãy → `not_reached`; gãy thì chia đôi trên toàn slice đến khi `b − a ≤ tol`.
   - `d(a) ≥ ngưỡng` → dịch xuống, đối xứng; `a = lo` mà vẫn gãy → `below_min`.
   - `d(a) ≥ ngưỡng` và `d(b) < ngưỡng` cùng lúc (mâu thuẫn) → dịch xuống (thận trọng: điểm gãy nhỏ hơn) và ghi nhận cờ không đơn điệu (quyết định Group 1).
4. **Kết quả:** `breaking_point = b`, `bracket = [a, b]`. Trạng thái `found`, hoặc `non_monotonic` nếu có cờ không đơn điệu (vẫn báo điểm gãy đầu tiên tìm được).

- **Điểm tổng hợp:** level là giá trị "không biến đổi" của spec (eps = 0, tỉ lệ che = 0) có mức sụt bằng 0 theo định nghĩa, không chạy, ghi vào quỹ đạo với `synthetic = true`.
- **Dùng lại kết quả:** mỗi điểm là một run có fingerprint riêng (gồm `eval_image_ids_sha256`). Điểm trên toàn slice trùng với run quét lưới đã có được bỏ qua do cache như mọi run khác.
- **Giới hạn trên số điểm:** với `W = (hi − lo) / (coarse_n − 1)` và `s = ⌈log₂(W / tol)⌉`:
  - điểm trên tập con tối đa: `coarse_n + s`;
  - điểm trên toàn slice tối đa: `coarse_n + 1 + s` (xác nhận 2 điểm, dịch tối đa `coarse_n − 1` ô thô, chia đôi `s` bước; review Group 1, thay cho `3 + s` vì dịch từng ô thô);
  - `max_points` = tổng hai giá trị trên. Với tham số rời rạc, `coarse_n` là số level thô thực có (không quá số giá trị trong `[lo, hi]`) và `s = ⌈log₂ g⌉` với `g` là khoảng cách chỉ số lớn nhất giữa hai level thô liền kề (`s = 0` khi `g ≤ 1`).
  - Slice không lớn hơn `subset_size`: không có tập con, toàn slice tối đa `coarse_n + s`.
  - Ví dụ PGD L∞ dải 0–32, `coarse_n = 5`, `tol = 0.125`: `W = 8`, `s = 6`, tập con 11, toàn slice 12, `max_points = 23`.
- Worker không bao giờ tạo quá `max_points` run cho một lần tìm kiếm (API từ chối nếu vượt).

### Khoảng tin cậy bootstrap
- Chỉ tính trên các điểm đánh giá trên toàn slice, bằng prediction theo ảnh đã lưu (`predictions_key`) và prediction sạch trong cache. Không tốn thêm GPU.
- Mỗi mẫu bootstrap: lấy lại có hoàn lại các ảnh của slice, tính lại đại lượng so với ngưỡng ở mọi điểm toàn slice, tìm level đầu tiên vượt ngưỡng bằng nội suy tuyến tính giữa hai điểm liền kề.
- `drop_ci` của mỗi điểm và `confidence_interval` của điểm gãy là phân vị 2.5% và 97.5%.
- `near_threshold = true` khi khoảng tin cậy của `d(b)` có cận dưới nhỏ hơn ngưỡng, hoặc khoảng tin cậy của `d(a)` có cận trên từ ngưỡng trở lên.
- Seed của bootstrap lấy từ `seed` của attack để kết quả tái lập được.
- **Chốt ở Group 2** (kế hoạch và review):
  - Mẫu không cắt ngưỡng được cắt về biên: luôn dưới ngưỡng → level toàn slice lớn nhất; gãy ngay ở điểm toàn slice thấp nhất → level thấp nhất. Không bỏ mẫu nào vì lý do này.
  - Mẫu có đại lượng không tính được (NaN, ví dụ mẫu không còn object đúng của class) bị bỏ khỏi `drop_ci` của điểm đó, và bỏ khỏi khoảng tin cậy của điểm gãy.
  - `confidence_interval` của điểm gãy chỉ có khi `found` hoặc `non_monotonic`; trạng thái khác là null (`drop_ci` của từng điểm vẫn có).
  - `near_threshold`: `found`/`non_monotonic` theo quy tắc trên; `not_reached` chỉ xét `d(hi)` (cận trên KTC ≥ ngưỡng); `below_min` chỉ xét `d(lo)` (cận dưới KTC < ngưỡng); trạng thái khác là `false`.
  - Bộ sinh số: `sha256(canonical_json({"purpose": "bootstrap", "seed": seed}))`; một mẫu dùng chung cho mọi điểm toàn slice.

### Trạng thái
| Tình huống | `SearchStatus` | `bracket` |
|---|---|---|
| Tìm được điểm gãy | `found` | `[a, b]` với `b − a ≤ tol` |
| Tìm được nhưng mức sụt thô không đơn điệu | `non_monotonic` | Như trên |
| Không gãy trong toàn dải | `not_reached` | `[hi, hi]` |
| Gãy ngay ở `lo` | `below_min` | `[lo, lo]` |
| Chạm giới hạn thời gian hoặc bị hủy giữa chừng | `stopped_limit` (hủy thì trạng thái experiment là `cancelled`) | Khoảng tốt nhất hiện có |
| mAP sạch bằng 0 với ngưỡng tương đối, không còn object để tính ASR, hoặc lỗi không phục hồi | `failed` | `message` giải thích |

### Worker
- Chạy các attack quét lưới trước, rồi lần lượt từng attack tìm ngưỡng.
- Với mỗi điểm: gọi `POST /internal/worker/experiments/{id}/runs` để tạo run (`attack_spec_id`, `level`, `scope`, `search_order`), sau đó chạy như mọi run.
- Sau mỗi điểm gửi `SearchResult` tạm thời để giao diện cập nhật quỹ đạo; khi xong gửi kết quả cuối kèm bootstrap.
- Trạng thái tìm kiếm (các điểm đã có, `a`, `b`, giai đoạn) dựng lại từ `SearchResult` tạm thời mới nhất (`bundle.search_results`, xem "Chi tiết chốt ở Group 0"); bị gián đoạn thì tiếp tục đúng giai đoạn, không đánh giá lại điểm đã có.
- **Chốt ở Group 3** (review):
  - Run đã tạo cho một điểm nhưng chưa báo kết quả (worker chết giữa chừng) được chạy tiếp theo đúng `search_order` của nó, không tạo run mới; run đã có metric thì dùng metric đó.
  - Run lỗi, bị bỏ qua (attack không dùng được với model) hoặc kết thúc không có metric làm cả lần tìm kết thúc `failed`, không thử lại; `message` gồm trạng thái và lý do của run.
  - API từ chối (lỗi khác mất lease, ví dụ `422` khi vượt `max_points`) khi tạo run, chạy run hoặc nhận `SearchResult` tạm thời → lần tìm kết thúc `failed`, `message` gồm mã lỗi; experiment chạy tiếp attack sau. API từ chối kết quả cuối thì worker chỉ ghi log. Mất lease (`409`) vẫn dừng experiment.
  - Attack tìm ngưỡng chưa có run nào thì calibration đo ở `search.hi` (level 0 của PGD cho bước nhảy 0).
  - Mọi run có metric (cả quét lưới) ghi `runs/<run_id>/predictions.json` và điền `predictions_key`; run `stopped_limit` có metric một phần cũng ghi.
  - Bootstrap dùng prediction trong bộ nhớ với run hoàn tất trong phiên; run đã kết thúc ở phiên trước hoặc trúng cache thì đọc `runs/<run_id>/predictions.json` qua `artifact-url` của chính run đó (đề xuất contract 001, đã duyệt). File không có (404), lỗi đọc (MinIO lỗi, API từ chối cấp URL bằng lỗi khác mất lease) hoặc file hỏng → điểm bị bỏ khỏi bootstrap kèm cảnh báo, không làm dừng job; mất lease (`409`) vẫn dừng experiment (task 18b, review).
  - Bản sao prediction do API tạo khi trúng cache giữ khóa của run gốc trong trường `key`; worker đọc file theo đúng run ghi trong khóa (khóa phải có dạng `runs/<uuid>/predictions.json`).

### API và kiểm tra khi tạo experiment
- `mode = search` được chấp nhận cho mọi spec không cần huấn luyện; với `adv_patch` → `422 not_supported_yet`.
- `lo < hi`, cả hai nằm trong dải của spec; `tol > 0` và `tol < hi − lo`; `coarse_n` trong 3–8; `subset_size` từ 2 đến số ảnh của slice (wizard cảnh báo khi dưới 20); ngưỡng đúng miền của `threshold_kind`; `class_filter` là class đích của mapping.
- Trần `MAX_RUNS = 50`: số run quét lưới cộng tổng `max_points` của mọi attack tìm ngưỡng không vượt 50; vượt → `422` ở `attacks`.
- **Đọc prediction của run đã kết thúc** (đề xuất contract 001): `artifact-url` cấp URL `GET` cho `runs/<run_id>/predictions.json` của run đã kết thúc thuộc experiment đang lease (lease đúng); mọi yêu cầu khác với run không `running` giữ `409` như Phase 3. Khi `start` trả `skip_cached` và run gốc có `predictions_key`, API sao chép đối tượng sang `runs/<run_id>/predictions.json` (copy phía server trong MinIO) và ghi `predictions_key` của run mới; run gốc không có file thì để null.
- Endpoint tạo run động kiểm tra: run thuộc attack ở chế độ tìm kiếm của experiment, level trong `[lo, hi]`, tổng số run chưa vượt `max_points`. Mọi vi phạm trả `422`, không trả `409` (worker coi `409` là mất lease).
- **Ước lượng:** `max_seconds = (max_subset_points × subset_size + max_full_points × số ảnh slice) × sec_per_image × 1.2`. Hiển thị như "tối đa", vì thực tế thường ít hơn.
  `total_seconds` và `exceeds_limit` giữ nghĩa của Phase 5–6 (chỉ run quét lưới). `max_total_seconds` = `total_seconds` + Σ `max_seconds`; `max_exceeds_limit` = `max_total_seconds` > giới hạn thời gian: chỉ cảnh báo, không chặn tạo experiment (worker vẫn dừng ở trần, `stopped_limit`).

- **Chốt ở Group 4** (kế hoạch và review):
  - Experiment có attack tìm ngưỡng chỉ `completed` khi mọi run đã kết thúc **và** mọi attack tìm ngưỡng có `SearchResult` cuối; trước đó experiment giữ `running` và lease (worker còn tạo run động).
  - Hủy, hoặc mọi run đã kết thúc khi hết thời gian, mà kết quả còn tạm thời: API chốt thành `stopped_limit` (giữ quỹ đạo, khoảng; không có `drop_ci`, không tạo metric mới), bỏ lease; kết quả cuối worker gửi sau đó nhận `409`, worker chỉ ghi log. Tạo run động khi đã hết thời gian → API chốt kết quả và kết thúc experiment, trả `409`.
  - `SearchResult` phải khớp cấu hình (`threshold_kind`, `threshold`, `class_filter`), `max_points` tính lại, và từng điểm khớp run (`search_order`, level, `scope`; run đã kết thúc); `drop` phải bằng đại lượng tính lại từ metric của run (sai số 1e-9), run không có metric dùng được thì `drop` null. Kết quả cuối không được thay (`422`).
  - Cận `absolute_drop` ≤ mAP sạch chỉ kiểm khi đã biết mAP sạch từ một run toàn slice đã `completed` cùng model, slice, mapping; chưa biết thì chỉ kiểm (0, 1].
  - Ước lượng: attack tìm ngưỡng không dùng được với model (cần gradient) có `max_seconds = 0`.
  - Trúng cache mà file prediction của run gốc không còn trong MinIO: không sao chép, `predictions_key` null (review #1).
  - Downgrade migration `0008` xóa dữ liệu `search_results` (có từ Phase 7) để downgrade xa hơn không vướng khóa ngoại.

### Frontend
- **Wizard bước 4:** mỗi attack có công tắc "Quét lưới / Tự tìm ngưỡng". Chế độ tìm ngưỡng gồm:
  - loại ngưỡng (ba lựa chọn, có giải thích một dòng), giá trị ngưỡng (thanh trượt và ô nhập, hiển thị %), class áp dụng (tùy chọn);
  - dải tìm kiếm (mặc định bằng dải của spec, nên PGD bắt đầu từ eps 0) và độ chính xác (mặc định `tol = (hi − lo) / 256`: PGD L∞ 0.125/255, PGD L2 0.0625; tham số rời rạc không dùng `tol`);
    - `tol` tự tính lại theo dải mỗi khi đổi `lo`/`hi`, cho tới khi người dùng tự sửa ô độ chính xác; sau đó giữ giá trị của người dùng (nhân bản: `tol` khác mặc định theo dải coi là đã sửa);
    - tham số rời rạc không có ô `tol`; body vẫn gửi `(hi − lo) / 256` vì contract bắt buộc, và schema `zod` vẫn kiểm `tol < hi − lo` như contract;
  - phần "Nâng cao" thu gọn: số điểm quét thô, kích thước tập con, số mẫu bootstrap.
  - Mặc định khi bật: `relative_drop` 20%, mọi class; `subset_size` = min(100, số ảnh slice), tối thiểu 2 (API từ chối tập con lớn hơn slice).
  - Chuyển về quét lưới vẫn giữ cấu hình tìm ngưỡng (bật lại không mất). Preset "Toàn bộ catalog" giữ chế độ và cấu hình tìm ngưỡng của attack đã chọn; attack mới thêm là quét lưới.
  - Công tắc "Dừng sớm" chỉ áp cho attack quét lưới.
  - Form tìm ngưỡng còn lỗi (ô trống hoặc sai luật) thì không sang bước sau và chưa gọi ước lượng.
  - `adv_patch`: công tắc bị khóa, kèm giải thích lý do.
- **Bước 5 và 6:** chi phí của attack tìm ngưỡng hiển thị dạng "tối đa ~X phút (tối đa N điểm)".
  - Có attack tìm ngưỡng thì ước lượng tổng (thẻ máy chạy, tóm tắt, thanh dưới) là "tối đa ~X (tối đa N điểm)" từ `max_total_seconds`; bước 6 liệt kê chi phí tối đa từng attack; `max_exceeds_limit` hiện cảnh báo.
  - Hộp xác nhận ghi "N run quét lưới · tìm ngưỡng tối đa M điểm".
- **Tab Kết quả**, mục "Điểm gãy":
  - mỗi attack một thẻ tóm tắt: trạng thái (`StatusBadge`), câu kết luận (ví dụ "Gãy tại eps ≈ 6.5/255, KTC 95%: 5.8–7.1"; "Không gãy trong dải 0–32/255"; "Gãy ngay ở mức nhỏ nhất"), cảnh báo "Sát ngưỡng" khi `near_threshold`, cảnh báo "Không đơn điệu, cần xem kỹ" khi `non_monotonic`;
  - biểu đồ quỹ đạo: mức sụt theo level; điểm trên tập con rỗng ruột, trên toàn slice đặc; số thứ tự theo `search_order`; đường ngang ngưỡng; vùng tô khoảng `bracket`; dải khoảng tin cậy của điểm gãy; kèm bảng số liệu;
  - biểu đồ so sánh điểm gãy giữa các attack, chuẩn hóa về % dải của spec (càng nhỏ càng dễ gãy); `not_reached` hiển thị "> 100%", `below_min` hiển thị "≤ mức nhỏ nhất".
- **Tiến độ khi đang chạy:** "Điểm 5 / tối đa 13 · khoảng hiện tại [4, 8] · giai đoạn: chia đôi trên tập con".
- **Điện thoại:** chỉ hiển thị thẻ tóm tắt; chạm vào thẻ để mở biểu đồ quỹ đạo toàn màn hình.
- Xếp hạng AUC của Phase 6 chỉ gồm attack quét lưới; attack tìm ngưỡng nằm ở biểu đồ so sánh điểm gãy.
- Nháp wizard đã lưu trước Phase 7 vẫn mở được: attack không có `mode`/`search` là quét lưới, không mất dữ liệu nháp (agent frontend chọn giữ khóa `v2`, điền mặc định khi đọc).

## Decisions

- **Tìm trên tập con, xác nhận trên toàn slice.** *Lý do:* phần lớn điểm đánh giá chạy trên 100 ảnh thay vì 300; kết luận cuối vẫn dựa trên toàn bộ dữ liệu.
- **Giới hạn trên số điểm được tính và kiểm soát ở API.** *Lý do:* `mission.md` nguyên tắc 5: chi phí tối đa phải biết trước và không thể bị vượt.
- **Worker tạo run động qua API.** *Lý do:* level kế tiếp chỉ biết sau khi có kết quả điểm trước; API vẫn là nơi kiểm soát giới hạn và ghi trạng thái.
- **Chưa hỗ trợ tìm ngưỡng cho patch.** *Lý do:* mỗi điểm cần một lần train patch; chi phí không tương xứng trong MVP.
- **Bootstrap trên prediction đã lưu.** *Lý do:* có khoảng tin cậy mà không tốn GPU; cho reviewer biết kết quả có chắc chắn hay chỉ sát ngưỡng.
- **Không đơn điệu vẫn trả điểm gãy nhưng gắn trạng thái riêng.** *Lý do:* thông tin vẫn hữu ích, nhưng reviewer phải được báo rằng giả định của thuật toán có thể không đúng.
- **`tol` mặc định bằng 1/256 dải; run động đếm vào `MAX_RUNS` qua `max_points`; chi phí tối đa là trường riêng, chỉ cảnh báo; vượt `max_points` trả `422`; `subset_size` ≥ 2; `class_filter` một class.** *Lý do:* chốt ở kickoff (2026-10-01). Trên KITTI, PGD L∞ eps 2/255 đã làm sụt 98% nên điểm gãy 20% có thể dưới 1/255 (thay mục "lưới mịn eps nhỏ" của Phase 2/6); trần run giữ chi phí biết trước (`mission.md` nguyên tắc 5); `409` làm worker dừng cả experiment; E2E trên fixture cần tập con 3 ảnh.
- **Fingerprint gồm tập ảnh được đánh giá.** *Lý do:* kết quả trên tập con và trên toàn slice ở cùng level là hai kết quả khác nhau; còn điểm toàn slice trùng với quét lưới thì được dùng lại.

## Context

- `mission.md` nguyên tắc 4 (tái lập), 5 (chi phí tối đa biết trước), 6 (trạng thái rõ).
- `tech-stack.md` mục 2.3 (metric, bootstrap), 3.3 (tự tìm ngưỡng).
- Phase 2: metric theo class, ASR. Phase 3: executor, checkpoint, API nội bộ. Phase 5: wizard, ước lượng, tab Kết quả. Phase 6: seed theo ảnh, xếp hạng AUC, điểm "không biến đổi" của spec.
- Phase 5: `mode = search` hiện trả `422 not_supported_yet` cho mọi spec (`experiment_config.py`); Phase 7 thu hẹp lại chỉ còn `adv_patch`. `EstimateResponse` đang có `total_seconds` (null khi thiếu profile) và `exceeds_limit` (cận dưới); Cách ghép `max_seconds` với hai trường này: xem "API và kiểm tra khi tạo experiment".
- Phase 6 (ảnh hưởng thiết kế, kiểm trong code):
  - Xếp hạng (`backend/app/services/experiment_views.py::_ranking`, `rank_attacks`) gom mọi run theo `attack_spec_id`, không lọc `mode`: phải loại attack `mode = search` (và run `scope = subset`) khỏi `attack_ranking`.
  - Trường mới của fingerprint theo mẫu `patch_key`: null và bỏ khỏi JSON khi null để hash cũ không đổi. `eval_image_ids_sha256` phải null với run toàn slice; nếu không, điểm toàn slice sẽ không trúng cache của run quét lưới (trái với "Dùng lại kết quả").
  - Worker client coi mọi `409` là mất lease và dừng cả experiment (`advertest_worker/client.py`). Endpoint tạo run động phải trả `422` khi vượt `max_points` hoặc sai level, không trả `409`.
  - Thứ tự thô → mịn (`ordinal`) và `grid.early_stop` chỉ áp cho attack quét lưới. Run động của tìm kiếm có `ordinal` sau mọi run quét lưới. Công tắc dừng sớm của wizard không áp cho attack tìm ngưỡng.
  - Trần `MAX_RUNS = 50` (`experiment_config.py`): preset toàn catalog đã dùng 43 run. Đã chốt: run động đếm vào trần qua `max_points`; toàn catalog cộng một lần tìm ngưỡng PGD (21 điểm với mặc định) sẽ bị từ chối.
  - `fog` mức 3 và 4 cùng cường độ nên tìm ngưỡng trên `fog` dễ ra `non_monotonic`. Corruption (severity 1–5) không có level "không biến đổi", nên không có điểm tổng hợp.
  - Nháp wizard khóa `advertest.wizard.v2`: thêm `search` thì điền mặc định cho nháp cũ (như Phase 6) hoặc đổi sang `v3`.

## Open Questions

- [ ] `subset_size` mặc định 100 có đủ ổn định trên KITTI không (so sánh điểm gãy tập con và toàn slice ở manual check).
- [ ] 200 mẫu bootstrap có đủ, và thời gian tính trên CPU của worker có chấp nhận được không.
