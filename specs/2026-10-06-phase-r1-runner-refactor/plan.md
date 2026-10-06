# Plan: Phase R1 — Refactor lớp chạy giữ hành vi

> Phân chia thư mục:
> `attacks/` (agent `attack`); `ml_core/models/` (agent `ml-model`); `ml_core/runner/`, `backend/worker/` (agent `worker`, như Phase 7); `tests/acceptance/phase_r1/`, `tests/fixtures/golden/` (người duyệt).
>
> Thứ tự: Group 0 ✅ → Group 1 → Group 2 → (Group 3, 4 song song) → Group 5 → Group 6 → Group 7.
> Mọi group của agent: golden R1 (CLI; worker qua `make test-db`) và test nghiệm thu Phase 0–8 phải pass ở **mỗi commit**, không chỉ cuối group.

## Group 0 — Golden `[người duyệt]` ✅

1. ✅ Golden CLI và worker trên code trước refactor (`6861ca8`); ghim provenance, torch 1 luồng.

## Group 1 — Seam `[agent: worker]`

2. `JobRunner` nhận `perturbation_factory` và `provenance` tùy chọn; `Runner` và `run_config` nhận `provenance`. Mặc định giữ hành vi.
3. Định nghĩa `Provenance` (Protocol cùng cài đặt mặc định đọc env và git như `ml_core/runner/env.py`) ở `ml_core/runner/`.
4. Không đổi gì khác; giữ nguyên các tên module cũ.

## Group 2 — Chuyển test nghiệm thu sang seam `[người duyệt]`

5. Thay 7 chỗ patch tên nội bộ bằng seam, giữ nguyên assertion: `phase_06/test_grid_order_early_stop.py:56`, `phase_07/conftest.py:213`, `phase_07/test_search_e2e_backend.py:255`, `phase_08/conftest.py:325, 335, 336`, `phase_02/test_reproducibility.py:313` (`predict_slice`: thay qua `ModelProvider` giả hoặc giữ đến Group 4 rồi chuyển).
6. Thêm fixture checkpoint do code trước R1 ghi (một run PGD dừng ở batch 0) vào `tests/fixtures/golden/`.
7. Viết test nghiệm thu kiến trúc và registry theo `validation.md` (fail trước refactor là đúng).

## Group 3 — Registry perturbation `[agent: attack]`

8. `attacks/builders.py`: `PerturbationBuilder`, `BuildContext`, `PerturbationRegistry`, `effective_adapter`, `DEFAULT_REGISTRY` với 4 builder (`art.evasion`, `corruption.imagecorruptions`, `occlusion.bbox`, `patch.robust_dpatch`), gồm `linf_eps` và `image_kind`.
9. `attacks/factory.py::build_perturbation` thành lớp chuyển tiếp gọi `DEFAULT_REGISTRY` (giữ chữ ký cho tới Group 5); bỏ `AnyPerturbation`.
10. Unit test: builder giả đăng ký và dựng được; tên adapter trùng thì lỗi; thiếu estimator với builder cần gradient thì `IncompatibleAttack`.

## Group 4 — Model adapter `[agent: ml-model]`

11. `ml_core/models/adapter.py`: `Capabilities`, `ModelAdapter`, `UltralyticsAdapter` (bọc `UltralyticsDetector` và `build_estimator`), `ModelProvider`.
12. Unit test: cache trả cùng instance theo khóa; model không hỗ trợ gradient → `estimator()` báo `NoGradients`.

## Group 5 — Lõi dùng chung `[agent: worker]`

13. `FingerprintService` (thay `job._inputs` và `run._fingerprint_inputs`), `ManifestBuilder` (thay `_Finisher._manifest` và `run._write_manifest`).
14. `ErrorPolicy` theo bảng trong `requirements.md`; `job._run_one` và `run._run_one` dùng chung.
15. Hai runner và `calibrate.py` dựng perturbation qua registry (patch qua `BuildContext.patch`), nạp model qua `ModelProvider`; bỏ `isinstance` trong `executor.linf_eps` và rẽ nhánh `kind` trong `images.perturbation_kind`.
16. Gom đường dẫn artifact; xóa lớp chuyển tiếp `attacks/factory.py` khi không còn chỗ gọi.

## Group 6 — Điều phối mỏng `[agent: worker]`

17. Tách `_Finisher`, `_JobSearchHooks`, dừng sớm và patch khỏi `JobRunner` thành module riêng trong `backend/worker/advertest_worker/` hoặc `ml_core/runner/` (dùng chung với CLI khi có thể: thứ tự run và dừng sớm theo `ml_core/runner/grid.py`).
18. `JobRunner` chỉ còn lease, heartbeat, directive, API; đạt các điều kiện kiến trúc trong `validation.md`.

## Group 7 — Kiểm tra cuối `[người duyệt]`

19. Chạy `make check`, `make test-db`; review từng nhánh bằng `phase-review`.
20. Cập nhật `CHANGELOG.md`, `roadmap.md` (đánh dấu R1); replan R2 (trường `adapter` trên registry vừa có).
