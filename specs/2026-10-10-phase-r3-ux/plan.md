# Plan: Phase R3 — UX ứng dụng

> Thư mục được sửa theo agent:
> - người duyệt: `contracts/`, `specs/design.md`, `tests/acceptance/phase_r3/`, `frontend/e2e/phase_r3/`;
> - `backend`: `backend/app/`, `backend/admin_cli/`, `docker/`, và `.env.example` (chỉ biến token của worker công cụ);
> - `attack`: `attacks/`;
> - `worker`: `backend/worker/`;
> - `frontend`: `frontend/src/` (không gồm `src/contracts/`, là file sinh ra).
>
> Thứ tự: Group 0 → (Group 1 ∥ Group 2 ∥ Group 4) → Group 3 (sau Group 2) → (Group 5 ∥ Group 6 ∥ Group 7) (sau Group 4) → Group 8.
> Group 4–7 chạy được trên mock (`VITE_USE_MOCKS=true`) trước khi Group 1 merge.
> Group rủi ro, cần review riêng ngay sau khi làm: Group 0 (contract), Group 1 (snapshot report, quyền endpoint), Group 3 (hành vi worker, làm mờ).

## Group 0 — Contract, design và test nghiệm thu `[người duyệt]` ✅

1. ✅ Đổi contract theo `requirements.md` mục Data / Fields:
   - `POST /models/{model_id}/check`;
   - `ExperimentDetail.promoted_from`;
   - `ReportInsight` và `ReportSnapshot.insight`;
   - audit action `model.rechecked`.

   Sau đó chạy `make contracts`. Thêm mock: experiment Khám phá có insight, model `check_failed`, spec ở từng `AttackSpecStatus`, report có `insight`.
2. ✅ Viết lại `design.md` theo app hiện có (gồm tông trạng thái spec/model, mode, thang màu ma trận, overlay thử nhanh), sửa dòng font trong `tech-stack.md` (2026-10-10).
3. ✅ Cập nhật `roadmap.md`: R3 bỏ phụ thuộc 11a; thêm Phase R3b (11a + 11b); sửa mục 3 của thứ tự cắt giảm (áp khi soạn spec, 2026-10-10).
4. ✅ Viết test nghiệm thu backend (`tests/acceptance/phase_r3/`) và E2E (`frontend/e2e/phase_r3/`) theo `validation.md`. Test của group chưa làm chỉ commit trên `phaser3-reviewer`, như R2.

## Group 1 — Tồn đọng backend và insight trong report `[agent: backend]` ✅

5. `POST /models/{id}/check`: kiểm trạng thái, kiểm weights còn trong storage, xếp `model_check`, ghi audit `model.rechecked`.
6. `ExperimentDetail.promoted_from` lấy từ cột đã có (migration `0011`).
7. Report:
   - lúc xuất, ghi `snapshot.insight` (dùng `backend/app/insight/service.py`);
   - template PDF thêm section "Điểm yếu chính", bỏ qua section khi `insight` là `None`;
   - report cũ xác minh vẫn khớp.
8. `purge_orphans` trong `backend/app/services/quick_tries.py`; vòng dọn nền và lệnh `advertest-admin purge-quick-tries` gọi thêm hàm này.
9. Docker:
   - service `worker-tools` trong `docker/compose.yaml`;
   - Dockerfile worker chép fixture đã kiểm sha256;
   - biến token trong `.env.example`.

## Group 2 — Attack `[agent: attack]` ✅

10. `attacks/selfcheck.py`: hàm công khai `fixture_inputs(*, with_estimator, fixtures_dir=None)`; CLI selfcheck dùng hàm này.
11. `PerturbationRegistry.validate` kiểm `art_class` của adapter ART; unit test cho spec seed (pass) và `art_class` lạ (`InvalidSpec`).

## Group 3 — Worker `[agent: worker]` ✅

12. `spec_check.py` gọi `attacks.selfcheck.fixture_inputs`, bỏ code dựng fixture riêng; đường dẫn fixture lấy theo image (Group 1 task 9).
13. `quick_try.py`:
    - làm mờ theo hợp vùng `rule_v1` của detection score ≥ `QUICK_TRY_BLUR_MIN_SCORE` trên ảnh sạch và mọi level;
    - bảng object giữ `operating_conf`.
14. Chạy lại phép đo thời gian thử nhanh của R2, ghi vào handoff (làm mờ mới không được vượt mục tiêu < 10 giây).

## Group 4 — Nền giao diện, trang experiment, trang chủ `[agent: frontend]` ✅

15. `status-config.ts`: `ATTACK_SPEC_STATUS`, `MODEL_STATUS`, `TOOL_JOB_STATUS`, `EXPERIMENT_MODE` (`Record<Enum, …>`, test so với enum sinh từ contract).
    Trình vẽ box (`components/case-viewer/`): ground truth nét đứt 8-4, nhãn × cho object bị mất, lớp "phát hiện sai mới" (`design.md` mục 3).
16. `frontend/src/copy/glossary.ts`, component `Term` (tooltip dùng được bằng bàn phím); `frontend/src/copy/decisions.ts`.
17. Trang experiment:
    - 5 tab; Chi phí và Tái lập chuyển vào Tổng quan; `?tab=` cũ chuyển hướng;
    - thanh vòng đời (hàm thuần + test theo bảng trạng thái);
    - nhãn mode, link `promoted_from`;
    - trạng thái trống của tab Review và Report.
18. Bảng ý nghĩa quyết định ở hộp gửi duyệt, màn hình review và trang report.
19. Trang chủ "việc cần làm" theo vai trò (hàm gom việc thuần + test theo vai trò).

## Group 5 — Wizard 3 bước, kết quả và nâng lên chính thức `[agent: frontend]` ✅

20. Wizard 3 bước:
    - mode, preset, danh sách chọn và thanh trượt;
    - bước 3 dựng từ `POST /experiments/draft`, chip level có nhãn, khóa phần bắt buộc của protocol;
    - "Tùy chỉnh nâng cao" thu gọn.

    Giữ luồng nhân bản; unit test so config tạo qua wizard với config từ `draft`.
21. Tab Kết quả: câu kết luận, điểm yếu (link sang Failure case đã lọc), ma trận và chú thích thang màu, trạng thái `no_data`.
22. Câu kết luận và "Cách đọc" cho từng biểu đồ (hàm sinh câu thuần, có test).
23. Nút "Nâng lên chính thức": chọn protocol, gọi `promote`, mở wizard bước 3 với `promoted_from`.
23a. `[người duyệt]` Sau khi Group 5 xong: chuyển 6 file E2E cũ đi qua wizard (Phase 5–8) sang wizard 3 bước, giữ nguyên assertion (Chốt ở Group 0).

## Group 6 — Admin catalog, duyệt spec, đăng ký model `[agent: frontend]` ✅

24. `/admin/attacks`:
    - cột trạng thái, bộ lọc;
    - form tạo spec và tạo version mới (form sinh từ `params_schema`);
    - chi tiết spec với kết quả tự kiểm tra, polling, "Kiểm tra lại", sửa metadata.
25. `/attack-specs/pending` cho reviewer: kích hoạt (hộp xác nhận) và từ chối (bắt buộc nhập lý do); vô hiệu nút với spec của chính mình.
26. `/admin/models`:
    - danh sách, form đăng ký, upload presigned có tiến độ, chặn đuôi file và kích thước ở client;
    - ghi chú layout ONNX;
    - chi tiết `ModelCheckResult` và "Kiểm tra lại".
27. Mục điều hướng mới theo quyền (`nav/config.ts`).

## Group 7 — Thử nhanh `[agent: frontend]` ✅

28. `/quick-try`:
    - chọn model, attack (lọc theo gradient, ẩn patch), preset và ảnh; chặn > 10 MB ở client;
    - polling; xử lý 429 và 410.
29. Ảnh sạch và ảnh tấn công cạnh nhau, box theo lớp overlay (dùng lại `components/case-viewer`), thanh trượt level không gọi lại API, bảng object và số đếm.
30. Nhãn "Không phải kết quả kiểm thử" kèm giờ xóa.

## Group 8 — Kiểm tra cuối `[người duyệt]`

31. `make check`, `make test-db`, `make test-e2e`; `phase-review` cả phase.
32. Demo theo `validation.md` (Docker, `make up`); `phase-close`.
