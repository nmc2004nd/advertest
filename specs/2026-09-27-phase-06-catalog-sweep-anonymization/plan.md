# Plan: Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

> Phân chia thư mục:
> `attacks/corruptions/`, `attacks/occlusion/` (agent `attack-transform`); `attacks/patch/` (agent `attack-patch`);
> `ml_core/runner/`, `ml_core/metrics/ranking.py` (agent `ml-core`); `ml_core/privacy/` (agent `ml-privacy`);
> `backend/` (agent `backend`); `frontend/` (agent `frontend`).
>
> Thứ tự: Group 0 → (Group 1, 2, 4 song song) → Group 3 → (Group 5, 6 song song; frontend bắt đầu với mock ngay sau Group 0) → Group 7.

## Group 0 — Constitution, contract, seed `[người duyệt]`

1. Cập nhật `roadmap.md`: chuyển làm mờ từ Phase 10 sang Phase 6, đổi tên Phase 6.
2. Cập nhật contract theo bảng trong `requirements.md`; thêm schema `PatchArtifact`.
3. Thêm 7 spec mới vào `contracts/seeds/attack_specs.json`; tính `spec_sha256`.
4. Viết mock: experiment toàn catalog có run `early_stop`, `attack_ranking` đủ trường hợp (kể cả `auc_drop = null`), tiến độ patch ở giai đoạn `training`, case có `anonymization.applied`.
5. `make contracts`; ghi `CHANGELOG.md`.

## Group 1 — Corruption và occlusion `[agent: attack-transform]`

6. Hàm seed theo ảnh `per_image_seed(seed, image_id)` (đặt trong `attacks/common/`).
7. Adapter corruption cài `Perturbation`: cắt vùng ảnh thật → uint8 → corruption → float → đặt lại; vùng pad không đổi.
8. Kiểm tra tương thích 5 corruption ở cả 5 severity với kích thước vùng ảnh KITTI; nếu lỗi thì thay bằng bản tương đương (albumentations hoặc bản vá) và báo người duyệt để cập nhật `tech-stack.md`.
9. Adapter occlusion: hình chữ nhật cùng tỉ lệ box, diện tích theo tỉ lệ, vị trí theo seed ảnh, nằm trong box.
10. Đăng ký các adapter mới vào `build_perturbation`.

## Group 2 — Patch attack `[agent: attack-patch]`

11. Tính khóa patch và kích thước patch từ `area_ratio` và kích thước vùng ảnh thật; tính vị trí cố định ở tâm vùng ảnh thật.
12. Huấn luyện bằng `RobustDPatch` trên batch từ slice huấn luyện; ghi lịch sử giá trị mục tiêu; hook lưu checkpoint mỗi 50 vòng lặp và hàm khôi phục.
13. Adapter đánh giá cài `Perturbation`: dán patch đã train vào vị trí cố định.
14. Hàm đo `sec_per_iteration` cho calibration.

## Group 3 — Runner, dừng sớm, xếp hạng `[agent: ml-core]`

15. Hàm sắp thứ tự level thô trước, mịn sau.
16. Logic dừng sớm trong executor: đánh dấu `skipped` (`early_stop`) cho level lớn hơn chưa chạy.
17. Tích hợp patch vào `RunExecutor` và worker: tra `PatchArtifact` theo khóa → train nếu chưa có (báo tiến độ `phase = training`, lưu checkpoint patch qua presigned URL) → đánh giá.
18. Thêm `patch_key` vào `fingerprint_inputs`.
19. Tạo ảnh nhiễu / vùng khác biệt chung cho mọi loại biến đổi (|δ| chuẩn hóa).
20. `ml_core/metrics/ranking.py`: tính `auc_drop`, `max_relative_drop`, xử lý `early_stop` và thiếu dữ liệu.

## Group 4 — Làm mờ ảnh `[agent: ml-privacy]`

21. `ml_core/privacy/regions.py`: tính vùng làm mờ `rule_v1` từ ground truth, prediction sạch, prediction sau biến đổi, ignore region.
22. `ml_core/privacy/blur.py`: Gaussian + pixelate theo kích thước vùng.
23. Tích hợp vào bước tạo ảnh hiển thị và thumbnail của failure case; ghi `anonymization` vào `FailureCaseRecord`; bảo đảm không ảnh hiển thị chưa làm mờ nào được upload.

## Group 5 — Backend `[agent: backend]`

24. Kiểm tra khi tạo experiment: `training_slice_id` bắt buộc với patch, cùng dataset version và **không giao** với slice đánh giá.
25. Ước lượng: thêm `training_seconds` khi patch chưa có; cost profile với `sec_per_iteration`.
26. Lưu và tra `PatchArtifact`; endpoint nội bộ cho worker tra và đăng ký patch; presigned URL cho khóa patch.
27. `attack_ranking` trong `ExperimentDetail` bằng hàm của `ml_core/metrics/ranking.py`.
28. Cập nhật quy tắc `display_mode` theo `anonymization.applied`.
29. Endpoint đọc catalog đầy đủ cho `/admin/attacks` (`attack_catalog.manage`).

## Group 6 — Frontend `[agent: frontend]`

30. Wizard bước 4: ba nhóm, chip severity, chọn slice huấn luyện cho patch (lọc slice giao nhau), preset "Toàn bộ catalog", công tắc dừng sớm.
31. Hiển thị `training_seconds` trong ước lượng.
32. Tab Kết quả: bảng xếp hạng, biểu đồ cột `auc_drop`, tùy chọn trục hoành chuẩn hóa; nhãn lý do `early_stop` trong bảng run.
33. Tiến độ hai giai đoạn cho run patch.
34. `CaseViewer`: nhãn ảnh thứ ba theo loại, dải "Đã làm mờ".
35. Trang `/admin/attacks`; thêm mục vào `NAV_ITEMS` (`frontend/src/nav/config.ts`, permission `attack_catalog.manage`, `implemented: true`). Admin khi đó có 5 mục, nên trên điện thoại hiện 3 mục + "Thêm". Dùng lại mẫu bảng/thẻ, `TruncatedId`, "Tải thêm" của Phase 4.

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

36. Viết test nghiệm thu `tests/acceptance/phase_06/` và kịch bản Playwright `frontend/e2e/phase_06/` theo `validation.md`.
37. Chạy experiment toàn catalog trên KITTI bằng laptop; hiệu chỉnh tham số patch.
38. Kiểm tra bằng mắt kết quả làm mờ; trả lời câu hỏi mở.
39. Cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
