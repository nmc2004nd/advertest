# Validation: Phase 3 — Worker và máy local

> Test trong `tests/acceptance/phase_03/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. CI chạy Postgres và MinIO như service container; worker chạy trên CPU với fixture.

## Automated Tests

### Chung
- [ ] `make check` pass, bao gồm toàn bộ test nghiệm thu Phase 0–3.
- [ ] `make contracts` không tạo thay đổi; mock của mọi schema mới validate được.
- [ ] CLI `advertest run` (Phase 2) vẫn cho kết quả nằm trong sai số so với golden Phase 2 sau khi chuyển sang `RunExecutor`.

### Ranh giới kiến trúc — `test_architecture.py`
- [ ] Package `advertest_worker`, `ml_core`, `attacks` không import `backend.app`, SQLAlchemy hay client MinIO có thông tin đăng nhập (kiểm tra bằng phân tích import).
- [ ] Biến môi trường của service `worker` trong compose không chứa thông tin đăng nhập Postgres hoặc MinIO.
- [ ] Không có endpoint công khai nào (ngoài `/internal/worker`) ghi vào `runs` hoặc `failure_cases` (kiểm tra OpenAPI và router).

### Xác thực worker — `test_worker_auth.py`
- [ ] Gọi endpoint `/internal/worker` không có token hoặc token sai → `401`.
- [ ] Token sau khi xoay: token cũ → `401`, token mới hoạt động.
- [ ] Token của target A lấy bundle, báo tiến độ hoặc hoàn thành run của experiment thuộc target B → `403`.
- [ ] DB chỉ lưu sha256 của token, không lưu token gốc.

### Lease — `test_leasing.py`
- [ ] Hai experiment `queued` cho cùng target: `lease` trả experiment tạo trước; experiment chuyển sang `running`.
- [ ] Gọi `lease` lần hai khi experiment đang được giữ → không trả lại experiment đó.
- [ ] Không có heartbeat quá 60 giây → experiment được lease lại cho worker khác.
- [ ] Sau khi lease lại, request của worker cũ (heartbeat, progress, complete với `lease_id` cũ) → `409`; tiến độ và kết quả không đổi.
- [ ] Experiment thuộc target khác không bao giờ được lease.

### Artifact — `test_artifacts.py`
- [ ] Presigned PUT cho khóa ngoài `runs/<run_id>/` bị từ chối khi xin URL.
- [ ] Presigned URL hết hạn không dùng được.
- [ ] Không xin được presigned URL cho run không ở trạng thái `running` (đã `completed`, `failed`, ...).
- [ ] Sau khi run hoàn tất: mọi khóa được tham chiếu trong `RunResult` và `FailureCaseRecord` tồn tại trong MinIO.
- [ ] Không còn đối tượng nào trong `runs/<run_id>/candidates/` sau khi hoàn tất.
- [ ] Thumbnail có chiều rộng 320 px, định dạng WebP.
- [ ] `complete` với `failure_case_ids` không khớp `failure_cases`, hoặc khóa artifact không tồn tại hay nằm ngoài `runs/<run_id>/` → bị từ chối; hợp lệ thì bảng `failure_cases` có đúng các record.
- [ ] Hai run cùng fingerprint ở hai experiment (run đầu `stopped_limit`, run sau chạy đủ) đều ghi được failure case, không xung đột `id`.

### Chạy và kết quả — `test_execution.py`
- [ ] Gửi experiment fixture (FGSM eps 4, PGD eps 4) → worker chạy xong; experiment `completed`, các run `completed`; metric nằm trong ±0.01 so với golden Phase 2.
- [ ] Gửi lại experiment cùng cấu hình → các run `skipped` với `status_reason.code = cached`, có `cached_from_run_id`, metric bằng metric của run gốc; attack không được gọi (spy).
- [ ] Model không hỗ trợ gradient → run `skipped` (`incompatible`).
- [ ] Ép một run ném ngoại lệ → run đó `failed` có thông điệp; run còn lại `completed`.
- [ ] `RunCompletion` nhận từ worker cho run chưa `running` → bị từ chối.
- [ ] Manifest do worker trong Docker tạo có `docker_image_digest` khác `"none"` và `git_dirty = false`.
- [ ] Checkpoint không chứa dữ liệu ảnh; chạy tiếp từ checkpoint cho mAP và ASR trùng lần chạy liền mạch.

### Chạy tiếp sau gián đoạn — `test_resume.py`
- [ ] Dừng worker sau batch k (mô phỏng chết đột ngột, không gọi `complete`); worker mới lease lại sau khi lease hết hạn và tiếp tục từ batch k+1.
- [ ] Mỗi ảnh chỉ được xử lý đúng một lần trên tổng hai worker (đếm bằng spy).
- [ ] Metric cuối nằm trong sai số (`map50` ±0.005, ASR ±0.01) so với lần chạy không bị gián đoạn.
- [ ] Danh sách failure case cuối (so theo `image_id` và `severity_score`) trùng với lần chạy không bị gián đoạn.
- [ ] Gián đoạn hai lần liên tiếp vẫn cho cùng kết quả.

### Giới hạn và hủy — `test_limits.py`
- [ ] Giới hạn thời gian rất nhỏ → run hiện tại `stopped_limit` (`time`), `metrics.partial = true`, `images_done < images_total`; run chưa chạy `stopped_limit` với `images_done = 0`; experiment `completed`.
- [ ] Thời gian worker bị dừng (giữa hai lần lease) không được cộng vào thời gian đã dùng.
- [ ] `experiment cancel` khi đang chạy → worker dừng sau batch hiện tại; run hiện tại và run chưa chạy `cancelled`; experiment `cancelled`.

### Calibration và ước lượng — `test_calibration.py`
- [ ] `advertest-worker calibrate` trên CPU tạo `CostProfile` hợp lệ cho target, model và attack; `batch_size ≤ min(n, 32)` với n = min(20, số ảnh của slice) (fixture 5 ảnh: n = 5).
- [ ] Job không có cost profile → calibration tự chạy trước, sau đó job chạy bằng batch size trong profile.
- [ ] Hàm ước lượng trả đúng giá trị trên số liệu dựng sẵn; thiếu profile trả "chưa có ước lượng".

### Kiểm toán — `test_audit.py`
- [ ] Tạo target, xoay token, gửi và hủy experiment đều có dòng `audit_log` với đúng actor, action, entity.
- [ ] `--as` với người dùng không phải admin `active` → lệnh bị từ chối.

## Manual Checks

- [ ] Tạo compute target `local-dev` cho laptop; khởi động worker bằng cách mặc định (chạy trực tiếp: `uv run advertest-worker run`).
- [ ] Chạy worker bằng profile `gpu` của compose trên máy có GPU (được phép để tồn đọng khi chưa có máy GPU).
- [ ] `import-local` dữ liệu Phase 1–2; kiểm tra trong MinIO console chỉ có ảnh thuộc slice.
- [ ] Gửi `pgd_sweep.yaml` trên slice KITTI 300 ảnh; theo dõi bằng `experiment show --watch`: tiến độ tăng đều, trạng thái đúng.
- [ ] Trong lúc PGD đang chạy, `kill -9` worker; khởi động lại; experiment chạy tiếp từ batch kế tiếp sau khoảng một phút; kết quả cuối khớp lần chạy trước trong sai số.
- [ ] Gửi lại cùng cấu hình: toàn bộ run được bỏ qua do cache gần như ngay lập tức.
- [ ] Gửi experiment với giới hạn thời gian 60 giây: dừng đúng, có kết quả một phần.
- [ ] Mở vài failure case trong MinIO: có ảnh sạch, ảnh sau tấn công, ảnh nhiễu, thumbnail.
- [ ] Ghi `sec_per_image` và batch size từ calibration của laptop vào `CHANGELOG.md`.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện, đặc biệt là kịch bản `kill -9` trên máy thật.
- [ ] Người duyệt đã chấp nhận thay đổi contract.
- [ ] Câu hỏi mở đã có câu trả lời; `tech-stack.md` đã cập nhật nếu cần.
- [ ] Tài liệu chạy worker trên máy local đã có.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 3 được đánh dấu hoàn thành.
