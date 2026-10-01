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
- Tập con = `subset_size` ảnh đầu tiên của slice sau khi sắp theo `hash(seed, image_id)`. Xác định, không phụ thuộc thứ tự lưu trữ.
- Nếu slice có không quá `subset_size` ảnh: tập con là toàn slice và bỏ qua giai đoạn xác nhận.

### Thuật toán
Ký hiệu `d(x, S)` là mức sụt ở level `x` trên tập ảnh `S`.

1. **Quét thô (trên tập con):** `coarse_n` level cách đều từ `lo` đến `hi` (với tham số rời rạc: `coarse_n` giá trị cách đều theo chỉ số, luôn gồm giá trị nhỏ nhất và lớn nhất).
   - `d(lo) ≥ ngưỡng` → chuyển sang xác nhận `lo` trên toàn slice; nếu vẫn gãy → `below_min`.
   - `d(hi) < ngưỡng` → chuyển sang xác nhận `hi` trên toàn slice; nếu vẫn không gãy → `not_reached`.
   - Ngược lại: khoảng `[a, b]` = hai level liền kề đầu tiên mà `d(a) < ngưỡng ≤ d(b)`.
   - Nếu các mức sụt thô không tăng dần (một điểm thấp hơn điểm trước quá 0.02) → ghi nhận cờ không đơn điệu.
2. **Chia đôi (trên tập con):** lặp `m = (a + b) / 2`, cập nhật `a` hoặc `b`, cho đến khi `b − a ≤ tol`. Với tham số rời rạc: chia đôi theo chỉ số, dừng khi `a` và `b` liền kề.
3. **Xác nhận (trên toàn slice):** đánh giá `a` và `b`.
   - `d(a) < ngưỡng ≤ d(b)` → xong.
   - `d(b) < ngưỡng` → dịch lên: `a = b`, `b` = level thô kế tiếp phía trên (hoặc `hi`); đánh giá `b` trên toàn slice; nếu `b = hi` mà vẫn không gãy → `not_reached`; ngược lại chia đôi trên toàn slice đến khi `b − a ≤ tol`.
   - `d(a) ≥ ngưỡng` → dịch xuống, đối xứng; nếu `a = lo` mà vẫn gãy → `below_min`.
4. **Kết quả:** `breaking_point = b`, `bracket = [a, b]`. Trạng thái `found`, hoặc `non_monotonic` nếu có cờ không đơn điệu (vẫn báo điểm gãy đầu tiên tìm được).

- **Điểm tổng hợp:** level là giá trị "không biến đổi" của spec (eps = 0, tỉ lệ che = 0) có mức sụt bằng 0 theo định nghĩa, không chạy, ghi vào quỹ đạo với `synthetic = true`.
- **Dùng lại kết quả:** mỗi điểm là một run có fingerprint riêng (gồm `eval_image_ids_sha256`). Điểm trên toàn slice trùng với run quét lưới đã có được bỏ qua do cache như mọi run khác.
- **Giới hạn trên số điểm:** với `W = (hi − lo) / (coarse_n − 1)` và `s = ⌈log₂(W / tol)⌉`:
  - điểm trên tập con tối đa: `coarse_n + s`;
  - điểm trên toàn slice tối đa: `3 + s`;
  - `max_points` = tổng hai giá trị trên. Với tham số rời rạc, `s` tính theo số chỉ số trong khoảng thô.
- Worker không bao giờ tạo quá `max_points` run cho một lần tìm kiếm (API từ chối nếu vượt).

### Khoảng tin cậy bootstrap
- Chỉ tính trên các điểm đánh giá trên toàn slice, bằng prediction theo ảnh đã lưu (`predictions_key`) và prediction sạch trong cache. Không tốn thêm GPU.
- Mỗi mẫu bootstrap: lấy lại có hoàn lại các ảnh của slice, tính lại đại lượng so với ngưỡng ở mọi điểm toàn slice, tìm level đầu tiên vượt ngưỡng bằng nội suy tuyến tính giữa hai điểm liền kề.
- `drop_ci` của mỗi điểm và `confidence_interval` của điểm gãy là phân vị 2.5% và 97.5%.
- `near_threshold = true` khi khoảng tin cậy của `d(b)` có cận dưới nhỏ hơn ngưỡng, hoặc khoảng tin cậy của `d(a)` có cận trên từ ngưỡng trở lên.
- Seed của bootstrap lấy từ `seed` của attack để kết quả tái lập được.

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

### API và kiểm tra khi tạo experiment
- `mode = search` được chấp nhận cho mọi spec không cần huấn luyện; với `adv_patch` → `422 not_supported_yet`.
- `lo < hi`, cả hai nằm trong dải của spec; `tol > 0` và `tol < hi − lo`; `coarse_n` trong 3–8; `subset_size` từ 2 đến số ảnh của slice (wizard cảnh báo khi dưới 20); ngưỡng đúng miền của `threshold_kind`; `class_filter` là class đích của mapping.
- Trần `MAX_RUNS = 50`: số run quét lưới cộng tổng `max_points` của mọi attack tìm ngưỡng không vượt 50; vượt → `422` ở `attacks`.
- Endpoint tạo run động kiểm tra: run thuộc attack ở chế độ tìm kiếm của experiment, level trong `[lo, hi]`, tổng số run chưa vượt `max_points`. Mọi vi phạm trả `422`, không trả `409` (worker coi `409` là mất lease).
- **Ước lượng:** `max_seconds = (max_subset_points × subset_size + max_full_points × số ảnh slice) × sec_per_image × 1.2`. Hiển thị như "tối đa", vì thực tế thường ít hơn.
  `total_seconds` và `exceeds_limit` giữ nghĩa của Phase 5–6 (chỉ run quét lưới). `max_total_seconds` = `total_seconds` + Σ `max_seconds`; `max_exceeds_limit` = `max_total_seconds` > giới hạn thời gian: chỉ cảnh báo, không chặn tạo experiment (worker vẫn dừng ở trần, `stopped_limit`).

### Frontend
- **Wizard bước 4:** mỗi attack có công tắc "Quét lưới / Tự tìm ngưỡng". Chế độ tìm ngưỡng gồm:
  - loại ngưỡng (ba lựa chọn, có giải thích một dòng), giá trị ngưỡng (thanh trượt và ô nhập, hiển thị %), class áp dụng (tùy chọn);
  - dải tìm kiếm (mặc định bằng dải của spec, nên PGD bắt đầu từ eps 0) và độ chính xác (mặc định `tol = (hi − lo) / 256`: PGD L∞ 0.125/255, PGD L2 0.0625; tham số rời rạc không dùng `tol`);
  - phần "Nâng cao" thu gọn: số điểm quét thô, kích thước tập con, số mẫu bootstrap.
  - `adv_patch`: công tắc bị khóa, kèm giải thích lý do.
- **Bước 5 và 6:** chi phí của attack tìm ngưỡng hiển thị dạng "tối đa ~X phút (tối đa N điểm)".
- **Tab Kết quả**, mục "Điểm gãy":
  - mỗi attack một thẻ tóm tắt: trạng thái (`StatusBadge`), câu kết luận (ví dụ "Gãy tại eps ≈ 6.5/255, KTC 95%: 5.8–7.1"; "Không gãy trong dải 0–32/255"; "Gãy ngay ở mức nhỏ nhất"), cảnh báo "Sát ngưỡng" khi `near_threshold`, cảnh báo "Không đơn điệu, cần xem kỹ" khi `non_monotonic`;
  - biểu đồ quỹ đạo: mức sụt theo level; điểm trên tập con rỗng ruột, trên toàn slice đặc; số thứ tự theo `search_order`; đường ngang ngưỡng; vùng tô khoảng `bracket`; dải khoảng tin cậy của điểm gãy; kèm bảng số liệu;
  - biểu đồ so sánh điểm gãy giữa các attack, chuẩn hóa về % dải của spec (càng nhỏ càng dễ gãy); `not_reached` hiển thị "> 100%", `below_min` hiển thị "≤ mức nhỏ nhất".
- **Tiến độ khi đang chạy:** "Điểm 5 / tối đa 13 · khoảng hiện tại [4, 8] · giai đoạn: chia đôi trên tập con".
- **Điện thoại:** chỉ hiển thị thẻ tóm tắt; chạm vào thẻ để mở biểu đồ quỹ đạo toàn màn hình.
- Xếp hạng AUC của Phase 6 chỉ gồm attack quét lưới; attack tìm ngưỡng nằm ở biểu đồ so sánh điểm gãy.
- Nháp wizard đã lưu trước Phase 7 vẫn mở được: attack không có `mode`/`search` là quét lưới, không mất dữ liệu nháp (giữ khóa `v2` hay đổi `v3` do agent frontend chọn, miễn đúng hành vi này).

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
