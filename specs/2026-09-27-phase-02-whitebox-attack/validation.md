# Validation: Phase 2 — Attack white-box đầu tiên

> Test trong `tests/acceptance/phase_02/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Toàn bộ test tự động chạy trên CPU bằng fixture.

## Automated Tests

### Chung
- [ ] `make check` pass (bao gồm test nghiệm thu Phase 0, 1, 2).
- [ ] `make contracts` không tạo thay đổi; mock `FailureCaseRecord` validate được.
- [ ] `spec_sha256` của `fgsm`, `pgd_linf`, `pgd_l2` khớp với giá trị tính lại; tham số cố định đúng bảng trong `requirements.md`.

### Tính đúng của attack — `test_attack_correctness.py`
- [ ] `level = 0` với cả 3 attack: ảnh sau tấn công trùng hệt ảnh gốc, metric sau tấn công bằng metric sạch.
- [ ] FGSM và PGD L∞ với eps = 8/255: `max |δ|` trên vùng ảnh thật ≤ 8/255 + 1e-6.
- [ ] PGD L2 với eps = 2: chuẩn L2 của δ trên mỗi ảnh ≤ 2 + 1e-4.
- [ ] Với cả 3 attack: δ ở vùng pad bằng **đúng 0** (so sánh chính xác, không dùng sai số).
- [ ] Ảnh sau tấn công nằm trong [0, 1].
- [ ] PGD L∞ eps = 8/255 làm loss của từng ảnh fixture tăng so với ảnh sạch.
- [ ] PGD L∞ eps = 16/255 trên fixture: `map50_tấn_công < map50_sạch − 0.1`.
- [ ] Weights và running stats BatchNorm không đổi sau một run PGD.

### Metric — `test_attack_metrics.py`
- [ ] Ghép prediction một-một: hai prediction cùng trùng một ground truth chỉ một cái được ghép.
- [ ] Prediction có score < 0.25 không được tính vào tập C.
- [ ] Trường hợp dựng sẵn: 4 object trong C, 1 object mất sau tấn công → `attack_success_rate = 0.25`.
- [ ] `|C| = 0` → `attack_success_rate = null`; `map50_sạch = 0` → `relative_drop = null`.
- [ ] Prediction mới nằm trong ignore region không được tính vào `new_false_positives`.
- [ ] `new_false_positives` trừ số FP trên ảnh sạch, tối thiểu 0; prediction không thuộc class đích không phải FP.
- [ ] `absolute_drop` và `relative_drop` đúng công thức trên số liệu dựng sẵn.

### Failure case — `test_failure_cases.py`
- [ ] Số case mỗi run ≤ `failure_cases_per_run`, chỉ gồm ảnh có `severity_score > 0`.
- [ ] Thứ tự case xác định: chạy hai lần cho cùng danh sách `image_id` cùng thứ tự.
- [ ] Mỗi case có đủ 3 file PNG và `FailureCaseRecord` validate được theo contract.
- [ ] Ảnh nhiễu khuếch đại có giá trị 0.5 (128) ở vùng pad; ảnh sau tấn công trùng ảnh sạch ở vùng pad.
- [ ] `FailureCaseRecord.id` là uuid5 xác định từ `fingerprint` và `image_id`.

### Fingerprint, manifest, cache — `test_reproducibility.py`
- [ ] Mọi run có `manifest.json` validate được theo contract; `fingerprint` bằng hash tính lại từ `fingerprint_inputs`.
- [ ] Đổi `level`, `seed`, spec hoặc mapping → fingerprint khác.
- [ ] Đổi `batch_size` hoặc `device` → fingerprint **không đổi**.
- [ ] Working tree có thay đổi chưa commit → `git_dirty = true`.
- [ ] Chỉ `.ai-log/` thay đổi → `git_dirty = false`.
- [ ] Chạy lần hai cùng cấu hình: run có `status = skipped`, `status_reason.code = cached`, attack không được gọi (kiểm tra bằng spy).
- [ ] Run `cached` không tạo hay sửa file nào trong `runs/<fingerprint>/`.
- [ ] Chạy với `--force`: kết quả mới nằm trong `reruns/`, file `result.json` gốc không bị thay đổi (so sánh hash trước và sau).
- [ ] Kết quả với `--force` nằm trong sai số so với lần đầu: `map50` ±0.005, `attack_success_rate` ±0.01.
- [ ] Batch size 1 và batch size 5 cho kết quả trong cùng sai số trên.
- [ ] Kết quả `fgsm` eps 4 và `pgd_linf` eps 4 trên fixture nằm trong ±0.01 so với `tests/fixtures/golden/phase_02.json`.
- [ ] Đổi `inference_params` → fingerprint khác.
- [ ] Nhãn đưa vào attack là ground truth của loader (`boxes`, `labels`), không phải prediction.
- [ ] mAP sạch lấy từ cache prediction của Phase 1 (không chạy lại predict ảnh sạch), bằng kết quả `advertest eval`.
- [ ] `experiment_id = content_id(sha256_of(cấu hình))`; `environment.compute_target_id = null`, `gpu_model = null` trên CPU; `docker_image_digest = "none"`; `gpu_seconds > 0`, `cost = null` với run `completed`.
- [ ] `advertest run show <fingerprint>` in `RunResult` và đường dẫn artifact (kể cả `reruns/`); fingerprint không có thì mã thoát 1.
- [ ] Bảng tóm tắt của `advertest run` có đủ cột: attack, level, mAP sạch, mAP tấn công, relative drop, ASR, trạng thái.

### Trạng thái — `test_statuses.py`
- [ ] Model card giả có `supports_gradients = false` → run `skipped`, `status_reason.code = incompatible`, attack không được gọi; kết quả ghi ở `runs/<fingerprint>/attempts/<run_id>/`.
- [ ] Ép một run ném ngoại lệ → run đó `failed` có thông điệp lỗi, ghi ở `attempts/<run_id>/` (không ở `runs/<fingerprint>/result.json`); các run còn lại trong cùng cấu hình vẫn `completed`.
- [ ] Mọi `RunResult` xuất ra validate được theo contract (bao gồm quy tắc bắt buộc `status_reason` với trạng thái bất thường).

## Manual Checks

> Máy phát triển không có GPU: các mục ghi "GPU" chạy trên CPU và ghi số liệu CPU; phần GPU chuyển thành tồn đọng, không chặn việc đóng phase (như Phase 1).

- [ ] Chạy `configs/examples/pgd_sweep.yaml` trên slice KITTI 300 ảnh bằng GPU local; bảng tóm tắt hiển thị đủ cột và trạng thái.
- [ ] mAP giảm dần theo eps với PGD L∞; ghi bảng kết quả vào `CHANGELOG.md`.
- [ ] PGD làm mAP giảm nhiều hơn FGSM ở cùng eps (kỳ vọng thông thường); nếu không, ghi nhận và điều tra trước khi merge.
- [ ] Ghi thời gian mỗi ảnh của FGSM và PGD trên GPU local, và batch size lớn nhất chạy ổn định khi tính gradient.
- [ ] Chạy lại với `--force`: kết quả trên GPU nằm trong sai số đã định nghĩa.
- [ ] Mở ít nhất 5 failure case: ảnh nhiễu khuếch đại chỉ có nhiễu trong vùng ảnh thật, không có ở dải pad trên/dưới; box trong `FailureCaseRecord` khớp với ảnh.
- [ ] Hiệu chỉnh dải `eps` của `pgd_l2` nếu cần (cập nhật seed và `version`).

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; kết quả KITTI đã ghi lại.
- [ ] Người duyệt đã chấp nhận thay đổi contract (`mask`, `git_dirty`, `FailureCaseRecord`) và `tech-stack.md` đã cập nhật.
- [ ] Các câu hỏi mở đã có câu trả lời hoặc đã chuyển vào backlog.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 2 được đánh dấu hoàn thành.
