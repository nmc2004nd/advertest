# Plan: Phase 0 — Contract và khung dự án

> Mỗi group ghi agent sở hữu. `người duyệt` nghĩa là Huy tự làm hoặc tự duyệt từng dòng. Group 2 phải merge trước khi bắt đầu Group 3, 4, 5, 6. Các group 3, 4, 5, 6 có thể chạy song song.

## Group 1 — Repo và công cụ `[người duyệt]`

1. Tạo cấu trúc thư mục theo `tech-stack.md` mục 8: `specs/`, `contracts/`, `ml_core/`, `attacks/`, `backend/`, `frontend/`, `tests/acceptance/`, `tests/fixtures/`, `docker/`, `scripts/`.
2. Khởi tạo Python workspace bằng `uv` (một `pyproject.toml` gốc, các package `advertest_contracts`, `ml_core`, `attacks`, `backend`). Pin phiên bản torch, adversarial-robustness-toolbox, ultralytics, torchmetrics, numpy, fastapi, pydantic, sqlalchemy, alembic.
3. Cấu hình ruff và mypy (strict cho `contracts/` và `backend/`).
4. Khởi tạo `frontend/` bằng Vite + React + TypeScript strict, pnpm; cài Tailwind, shadcn/ui, TanStack Query, React Router.
5. Tạo `Makefile` với các lệnh: `up`, `down`, `migrate`, `contracts`, `fixtures`, `lint`, `typecheck`, `test`, `test-acceptance`, `check`.
6. Ghi các phiên bản đã pin vào `specs/tech-stack.md`.

## Group 2 — Contract `[người duyệt]`

7. Viết enum trong `contracts/python/advertest_contracts/enums.py` đúng bảng trong `requirements.md`.
8. Viết các model Pydantic: `AttackSpec`, `AttackConfig`, `ExperimentConfig`, `RunResult`, `Manifest`, `SearchResult`, `ProtocolBody`.
9. Viết hàm tiện ích dùng chung: `canonical_json()` theo RFC 8785 (JCS) và `sha256_of()`, `compute_fingerprint(fingerprint_inputs)`.
10. Viết interface `Perturbation` (Protocol) trong `contracts/python/advertest_contracts/perturbation.py` đúng `tech-stack.md` mục 3.1.
11. Script `scripts/gen_contracts.py`: xuất JSON Schema vào `contracts/schemas/`, sinh TypeScript type vào `frontend/src/contracts/`.
12. Viết mock trong `contracts/mocks/`: ít nhất một mẫu cho mỗi schema, và cho `RunResult` có đủ một mẫu mỗi `RunStatus`, cho `SearchResult` có đủ một mẫu mỗi `SearchStatus`.
13. Viết seed catalog ban đầu trong `contracts/seeds/attack_specs.json`: `fgsm`, `pgd_linf`, `pgd_l2` (giá trị theo Phase 2). `adv_patch`, corruption và occlusion được thêm ở Phase 6 cùng `access = not_applicable`.

## Group 3 — Database `[agent: backend]`

14. Cấu hình SQLAlchemy 2 và Alembic trong `backend/`.
15. Viết migration đầu tiên tạo toàn bộ bảng trong `requirements.md`, dùng enum Postgres tương ứng với enum contract.
16. Tạo hai DB role `advertest_owner` và `advertest_app`; cấp và thu hồi quyền đúng mục "Ràng buộc bắt buộc ở cấp DB".
17. Viết trigger chặn `reviews.reviewer_id` trùng `experiments.created_by`.
18. Tạo unique constraint `(experiment_id, fingerprint)` trên `runs`.
19. Script seed: nạp `attack_specs` từ `contracts/seeds/`, tạo một compute target `local-dev` (`billing_mode = none`), một tài khoản admin từ biến môi trường.

## Group 4 — Backend API khung `[agent: backend]`

20. Tạo app FastAPI với router cho từng nhóm endpoint trong `requirements.md`, dùng model từ `advertest_contracts`.
21. Mọi endpoint (trừ `/health`) trả `501` với body lỗi thống nhất `{"error": {"code": "not_implemented", "message": ...}}`.
22. Viết `/health`: phiên bản, git commit, trạng thái Postgres và MinIO.
23. Khai báo security scheme trong OpenAPI: cookie cho người dùng, bearer token cho `/internal/worker`.
24. Xuất `contracts/openapi.json` bằng `make contracts`.

## Group 5 — Frontend khung `[agent: frontend]`

25. Sinh type từ `contracts/openapi.json` vào `frontend/src/contracts/` (qua `make contracts`).
26. Tạo lớp gọi API dùng TanStack Query, có chế độ mock đọc từ `contracts/mocks/` khi `VITE_USE_MOCKS=true`.
27. Tạo component `StatusBadge` dùng chung cho `RunStatus`, `ExperimentStatus`, `SearchStatus`: màu + icon + chữ.
28. Tạo một trang khung `/dev/contracts` hiển thị danh sách mock `RunResult` bằng `StatusBadge`, để chứng minh type và mock hoạt động. Trang này bị loại khỏi bản build production.
29. Cấu hình Vitest và một test cho `StatusBadge` (mọi giá trị enum đều có nhãn, không có giá trị nào rơi vào nhánh mặc định).

## Group 6 — Fixture `[agent: ml-core]`

30. Script `scripts/fetch_fixtures.py`: tải 5 ảnh KITTI kèm label gốc (vào `tests/fixtures/kitti/image_2/`, `label_2/`) và weights YOLOv8n từ nơi lưu do người duyệt chọn, kiểm tra sha256 theo `tests/fixtures/checksums.json`, lưu vào `tests/fixtures/` (đã có trong `.gitignore`).
31. Viết annotation ground truth cho 5 ảnh theo định dạng manifest nội bộ (`tests/fixtures/manifest.json`).
32. Viết smoke test: chạy YOLOv8n trên 5 ảnh bằng CPU, trả về box hợp lệ theo quy ước `tech-stack.md` mục 2.1.

## Group 7 — Docker Compose `[agent: backend]`

33. `docker/compose.yaml` gồm `postgres`, `minio`, `api`, `frontend`; volume cho dữ liệu; healthcheck cho từng service.
34. Service khởi tạo MinIO tạo sẵn các bucket: `artifacts`, `reports`, `datasets`, `models`.
35. `api` chạy migration bằng role `advertest_owner`, sau đó chạy ứng dụng bằng role `advertest_app`.
36. File `.env.example` liệt kê mọi biến môi trường cần thiết.

## Group 8 — CI `[người duyệt]`

37. GitHub Actions: job `python` (ruff, mypy, pytest), job `frontend` (eslint, `tsc --noEmit`, vitest), job `contracts` (sinh lại và `git diff --exit-code`, validate mock), job `acceptance` (Postgres service container, chạy `tests/acceptance/phase_00/`).
38. Cache fixture và dependency.

## Group 9 — Hướng dẫn agent `[người duyệt]`

39. Viết `CLAUDE.md` ở gốc: thứ tự đọc spec, thư mục được sửa theo từng agent, file cấm sửa, lệnh `make check` bắt buộc trước khi báo xong, quy tắc dừng và hỏi khi mơ hồ.
40. Tạo `CHANGELOG.md` với mục Phase 0.

## Group 10 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

41. Viết test nghiệm thu trong `tests/acceptance/phase_00/` theo `validation.md`.
42. Chạy `make check` và toàn bộ manual check.
43. Rà lại contract từng dòng một lần cuối, đối chiếu với `requirements.md`.
44. Cập nhật `roadmap.md`, `CHANGELOG.md`; merge.
