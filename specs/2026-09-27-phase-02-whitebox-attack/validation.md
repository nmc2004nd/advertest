# Validation: Phase 2 — Attack white-box đầu tiên

> Test trong `tests/acceptance/phase_02/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Toàn bộ test tự động chạy trên CPU bằng fixture.

## Automated Tests

### Chung
- [x] `make check` pass (bao gồm test nghiệm thu Phase 0, 1, 2).
- [x] `make contracts` không tạo thay đổi; mock `FailureCaseRecord` validate được.
- [x] `spec_sha256` của `fgsm`, `pgd_linf`, `pgd_l2` khớp với giá trị tính lại; tham số cố định đúng bảng trong `requirements.md`.

### Tính đúng của attack — `test_attack_correctness.py`
- [x] `level = 0` với cả 3 attack: ảnh sau tấn công trùng hệt ảnh gốc, metric sau tấn công bằng metric sạch.
- [x] FGSM và PGD L∞ với eps = 8/255: `max |δ|` trên vùng ảnh thật ≤ 8/255 + 1e-6.
- [x] PGD L2 với eps = 2: chuẩn L2 của δ trên mỗi ảnh ≤ 2 + 1e-4.
- [x] Với cả 3 attack: δ ở vùng pad bằng **đúng 0** (so sánh chính xác, không dùng sai số).
- [x] Ảnh sau tấn công nằm trong [0, 1].
- [x] PGD L∞ eps = 8/255 làm loss của từng ảnh fixture tăng so với ảnh sạch.
- [x] PGD L∞ eps = 16/255 trên fixture: `map50_tấn_công < map50_sạch − 0.1`.
- [x] Weights và running stats BatchNorm không đổi sau một run PGD.

### Metric — `test_attack_metrics.py`
- [x] Ghép prediction một-một: hai prediction cùng trùng một ground truth chỉ một cái được ghép.
- [x] Prediction có score < 0.25 không được tính vào tập C.
- [x] Trường hợp dựng sẵn: 4 object trong C, 1 object mất sau tấn công → `attack_success_rate = 0.25`.
- [x] `|C| = 0` → `attack_success_rate = null`; `map50_sạch = 0` → `relative_drop = null`.
- [x] Prediction mới nằm trong ignore region không được tính vào `new_false_positives`.
- [x] `new_false_positives` trừ số FP trên ảnh sạch, tối thiểu 0; prediction không thuộc class đích không phải FP.
- [x] `absolute_drop` và `relative_drop` đúng công thức trên số liệu dựng sẵn.

### Failure case — `test_failure_cases.py`
- [x] Số case mỗi run ≤ `failure_cases_per_run`, chỉ gồm ảnh có `severity_score > 0`.
- [x] Thứ tự case xác định: chạy hai lần cho cùng danh sách `image_id` cùng thứ tự.
- [x] Mỗi case có đủ 3 file PNG và `FailureCaseRecord` validate được theo contract.
- [x] Ảnh nhiễu khuếch đại có giá trị 0.5 (128) ở vùng pad; ảnh sau tấn công trùng ảnh sạch ở vùng pad.
- [x] `FailureCaseRecord.id` là uuid5 xác định từ `fingerprint` và `image_id`.

### Fingerprint, manifest, cache — `test_reproducibility.py`
- [x] Mọi run có `manifest.json` validate được theo contract; `fingerprint` bằng hash tính lại từ `fingerprint_inputs`.
- [x] Đổi `level`, `seed`, spec hoặc mapping → fingerprint khác.
- [x] Đổi `batch_size` hoặc `device` → fingerprint **không đổi**.
- [x] Working tree có thay đổi chưa commit → `git_dirty = true`.
- [x] Chỉ `.ai-log/` thay đổi → `git_dirty = false`.
- [x] Chạy lần hai cùng cấu hình: run có `status = skipped`, `status_reason.code = cached`, attack không được gọi (kiểm tra bằng spy).
- [x] Run `cached` không tạo hay sửa file nào trong `runs/<fingerprint>/`.
- [x] Chạy với `--force`: kết quả mới nằm trong `reruns/`, file `result.json` gốc không bị thay đổi (so sánh hash trước và sau).
- [x] Kết quả với `--force` nằm trong sai số so với lần đầu: `map50` ±0.005, `attack_success_rate` ±0.01.
- [x] Batch size 1 và batch size 5 cho kết quả trong cùng sai số trên.
- [x] Kết quả `fgsm` eps 4 và `pgd_linf` eps 4 trên fixture nằm trong ±0.01 so với `tests/fixtures/golden/phase_02.json`.
- [x] Đổi `inference_params` → fingerprint khác.
- [x] Nhãn đưa vào attack là ground truth của loader (`boxes`, `labels`), không phải prediction.
- [x] mAP sạch lấy từ cache prediction của Phase 1 (không chạy lại predict ảnh sạch), bằng kết quả `advertest eval`.
- [x] `experiment_id = content_id(sha256_of(cấu hình))`; `environment.compute_target_id = null`, `gpu_model = null` trên CPU; `docker_image_digest = "none"`; `gpu_seconds > 0`, `cost = null` với run `completed`.
- [x] `advertest run show <fingerprint>` in `RunResult` và đường dẫn artifact (kể cả `reruns/`); fingerprint không có thì mã thoát 1.
- [x] Bảng tóm tắt của `advertest run` có đủ cột: attack, level, mAP sạch, mAP tấn công, relative drop, ASR, trạng thái.

### Trạng thái — `test_statuses.py`
- [x] Model card giả có `supports_gradients = false` → run `skipped`, `status_reason.code = incompatible`, attack không được gọi; kết quả ghi ở `runs/<fingerprint>/attempts/<run_id>/`.
- [x] Ép một run ném ngoại lệ → run đó `failed` có thông điệp lỗi, ghi ở `attempts/<run_id>/` (không ở `runs/<fingerprint>/result.json`); các run còn lại trong cùng cấu hình vẫn `completed`.
- [x] Mọi `RunResult` xuất ra validate được theo contract (bao gồm quy tắc bắt buộc `status_reason` với trạng thái bất thường).

## Manual Checks

> Máy phát triển không có GPU: các mục ghi "GPU" chạy trên CPU và ghi số liệu CPU; phần GPU chuyển thành tồn đọng, không chặn việc đóng phase (như Phase 1).

- [x] Chạy `configs/examples/pgd_sweep.yaml` trên slice KITTI 300 ảnh bằng GPU local; bảng tóm tắt hiển thị đủ cột và trạng thái. (CPU, 2026-09-28)
- [x] mAP giảm dần theo eps với PGD L∞; ghi bảng kết quả vào `CHANGELOG.md`.
- [x] PGD làm mAP giảm nhiều hơn FGSM ở cùng eps (kỳ vọng thông thường); nếu không, ghi nhận và điều tra trước khi merge.
- [ ] Ghi thời gian mỗi ảnh của FGSM và PGD trên GPU local, và batch size lớn nhất chạy ổn định khi tính gradient. (Đã đo trên CPU: FGSM 0.17 s/ảnh, PGD 1.3 s/ảnh, batch 8; phần GPU tồn đọng.)
- [ ] Chạy lại với `--force`: kết quả trên GPU nằm trong sai số đã định nghĩa. (Trên CPU: trùng tuyệt đối; phần GPU tồn đọng.)
- [x] Mở ít nhất 5 failure case: ảnh nhiễu khuếch đại chỉ có nhiễu trong vùng ảnh thật, không có ở dải pad trên/dưới; box trong `FailureCaseRecord` khớp với ảnh.
- [x] Hiệu chỉnh dải `eps` của `pgd_l2` nếu cần (cập nhật seed và `version`). (Giữ dải, xem Open Questions trong `requirements.md`.)

## Definition of Done

- [x] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; kết quả KITTI đã ghi lại.
- [x] Người duyệt đã chấp nhận thay đổi contract (`mask`, `git_dirty`, `FailureCaseRecord`) và `tech-stack.md` đã cập nhật.
- [x] Các câu hỏi mở đã có câu trả lời hoặc đã chuyển vào backlog.
- [x] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 2 được đánh dấu hoàn thành.
