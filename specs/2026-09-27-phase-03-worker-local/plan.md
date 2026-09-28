# Plan: Phase 3 — Worker và máy local

> Phân chia thư mục:
> `ml_core/runner/`, `ml_core/store/` (agent `ml-core`); `backend/app/` (agent `backend`); `backend/worker/` — package `advertest_worker` (agent `worker`); `backend/admin_cli/` (agent `backend`).
>
> Thứ tự: Group 0 → (Group 1, Group 2 song song) → Group 3 → Group 4 → Group 5 → Group 6.
> Group 3 có thể bắt đầu với executor giả ngay khi Group 0 xong, sau đó chuyển sang executor thật khi Group 1 merge.

## Group 0 — Contract `[người duyệt]`

1. Thêm các schema `WorkerJobBundle`, `RunStartRequest`, `RunStartResponse`, `ProgressReport`, `WorkerDirective`, `CostProfile`.
2. Thêm `RunResult.cached_from_run_id`, `RunResult.metrics.partial`, `FailureCaseRecord.artifacts.clean_thumb`, `.adversarial_thumb`, enum `ProtocolStatus`; schema `RunCompletion`; `compute_failure_case_id(fingerprint, run_id, image_id)`, cập nhật mock và test nghiệm thu Phase 2 liên quan tới `id`.
3. Cập nhật OpenAPI nhóm `/internal/worker` theo bảng endpoint trong `requirements.md`.
4. Thêm mock cho các schema mới; `make contracts`; ghi `CHANGELOG.md`.
4b. Chuyển `httpx==0.28.1` sang dependency chính; thêm package `advertest_worker` (`backend/worker/`) và entry point `advertest-worker` vào `pyproject.toml`; cập nhật `tech-stack.md` mục 11.

## Group 1 — Executor và lưu trữ `[agent: ml-core]`

5. Tách `ml_core/runner/run.py` (Phase 2) thành `RunExecutor` (`init`, `process_batch`, `finalize`) với trạng thái tuần tự hóa được (`to_checkpoint()`, `from_checkpoint()`), giữ các hành vi Phase 2 ghi trong `requirements.md`; checkpoint không chứa ảnh.
6. Theo dõi top-K ứng viên failure case theo batch với quy tắc xác định của Phase 2.
7. Tạo thumbnail WebP rộng 320 px.
8. Cài đặt `MinioStore` và `PresignedStore` (chỉ ghi qua URL do API cấp) theo interface `ArtifactStore`.
9. Chuyển CLI `advertest run` sang dùng `RunExecutor`; test nghiệm thu Phase 2 phải vẫn pass.

## Group 2 — Backend: dữ liệu và dịch vụ `[agent: backend]`

10. Migration: thêm trạng thái `dev` cho protocol, seed protocol `dev-open`; bổ sung cột cần thiết cho lease, checkpoint, thời gian xử lý cộng dồn, `cached_from_run_id`; sửa bảng `failure_cases` khớp `FailureCaseRecord` (detections, artifacts gồm thumbnail, số object mất và FP mới).
11. Service `compute_targets`: tạo, xoay token (lưu sha256), xác thực token.
12. Service `registry`: đăng ký model, dataset version, slice, mapping từ `LocalStore`; upload lên MinIO (chỉ ảnh thuộc slice).
13. Service `experiments`: tạo experiment từ cấu hình local + target + giới hạn, lập danh sách run, gắn protocol `dev-open`; hủy experiment.
14. Service `leasing`: chọn experiment theo thứ tự đến trước cho đúng target, đặt và gia hạn lease, lease lại khi hết hạn.
15. Service `runs`: bắt đầu run (kiểm tra cache theo fingerprint toàn hệ thống), nhận tiến độ, cộng dồn thời gian, tính `WorkerDirective`, nhận kết quả, cập nhật trạng thái experiment.
16. Hàm ước lượng thời gian từ cost profile.
17. Ghi `audit_log` cho: tạo target, xoay token, gửi experiment, hủy experiment.

## Group 3 — Backend: API nội bộ `[agent: backend]`

18. Dependency xác thực bearer token → compute target; kiểm tra quyền sở hữu experiment/run theo target (`403` nếu sai).
19. Cài đặt 8 endpoint `/internal/worker` theo `requirements.md`.
20. Presigned URL: GET cho tài nguyên trong bundle, PUT giới hạn trong `runs/<run_id>/`, hết hạn 15 phút; dùng endpoint MinIO công khai cấu hình được (`MINIO_PUBLIC_ENDPOINT`).
21. Kiểm tra `RunCompletion` nhận từ worker theo contract và theo trạng thái hiện tại của run (không cho hoàn thành run chưa `running`); `failure_case_ids` khớp record; khóa artifact nằm trong `runs/<run_id>/` và tồn tại.

## Group 4 — Worker `[agent: worker]`

22. Package `advertest_worker`: cấu hình qua biến môi trường (`API_URL`, `WORKER_TOKEN`, `CACHE_DIR`).
23. Client API nội bộ có retry với backoff khi mất kết nối.
24. Vòng lặp chính: lease → bundle → tải tài nguyên vào cache local theo sha256 → calibration nếu thiếu cost profile → chạy từng run.
25. Với mỗi run: tính fingerprint và manifest → `start` → xử lý batch bằng `RunExecutor` → upload checkpoint và ứng viên → `progress` → làm theo `WorkerDirective`.
26. Luồng heartbeat riêng mỗi 15 giây.
27. Chạy tiếp từ checkpoint khi bundle có checkpoint.
28. Hoàn tất run: chọn case, chép sang `cases/`, tạo thumbnail, xóa ứng viên thừa, gửi `complete` với `RunCompletion`.
29. Lệnh `advertest-worker run` và `advertest-worker calibrate` (entry point riêng, không thêm vào `ml_core.cli`); calibration theo quy tắc trần trong `requirements.md`.
30. Xử lý hết VRAM trong khi chạy: giảm batch size một bậc, ghi cảnh báo, gửi cost profile cập nhật.

## Group 5 — CLI quản trị và hạ tầng `[agent: backend]`

31. `advertest-admin`: `compute-target create|rotate-token|list`, `import-local`, `submit`, `experiment list|show|cancel`; `show --watch` làm mới mỗi 2 giây.
32. Thêm service `worker` vào `docker/compose.yaml` với profile GPU (nvidia runtime) và profile CPU (cho CI); image đặt `GIT_COMMIT` và `DOCKER_IMAGE_DIGEST` (build arg) để fingerprint đúng.
33. Cập nhật `.env.example`.
34. Viết hướng dẫn chạy worker trên máy local (mặc định chạy trực tiếp; cách dùng profile `cpu`/`gpu`) vào tài liệu vận hành.

## Group 6 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

35. Viết test nghiệm thu `tests/acceptance/phase_03/` theo `validation.md` (Postgres và MinIO chạy như service container trong CI, worker chạy trên CPU với fixture).
36. Chạy toàn bộ luồng trên laptop với slice KITTI; thực hiện manual check gián đoạn worker.
37. Trả lời câu hỏi mở; cập nhật spec nếu cần.
38. Cập nhật `roadmap.md`, `CHANGELOG.md`; merge.
