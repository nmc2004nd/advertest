# Plan: Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

> Phân chia thư mục:
> `attacks/corruptions/`, `attacks/occlusion/` (agent `attack-transform`); `attacks/patch/` (agent `attack-patch`);
> `ml_core/runner/`, `ml_core/metrics/ranking.py` (agent `ml-core`); `ml_core/privacy/` (agent `ml-privacy`);
> `backend/app/`, `backend/migrations/` (agent `backend`); `backend/worker/` (agent `worker`); `frontend/` (agent `frontend`).
> Agent `ml-privacy` được sửa thêm `ml_core/runner/candidates.py` ở task 23, và tối thiểu `ml_core/runner/executor.py` (`_offer`, `_record`; chốt ở Group 4).
>
> Thứ tự: Group 0 → (Group 1, 2, 4 song song) → Group 3 → (Group 5, 6 song song; frontend bắt đầu với mock ngay sau Group 0) → Group 7.

## Group 0 — Constitution, contract, seed `[người duyệt]`

1. Cập nhật `roadmap.md`: chuyển làm mờ từ Phase 10 sang Phase 6, đổi tên Phase 6.
2. Cập nhật contract theo bảng trong `requirements.md`; thêm schema `PatchArtifact`.
2a. OpenAPI: endpoint đọc catalog đầy đủ (`attack_catalog.manage`); endpoint nội bộ cho worker tra và đăng ký patch, và báo run `skipped` (`early_stop`).
3. Thêm 7 spec mới vào `contracts/seeds/attack_specs.json`; tính `spec_sha256`.
4. Viết mock: experiment toàn catalog có run `early_stop`, `attack_ranking` đủ trường hợp (kể cả `auc_drop = null`), tiến độ patch ở giai đoạn `training`, case có `anonymization.applied`.
5. `make contracts`; ghi `CHANGELOG.md`.
5a. Migration `0006`: thêm `not_applicable` vào enum `attack_access` (seed mới phải nạp được vào DB).

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
14. Hàm đo `sec_per_image_iteration` cho calibration.

## Group 3 — Runner, dừng sớm, xếp hạng `[agent: ml-core]`

15. `ml_core/runner/grid.py`: hàm thuần sắp thứ tự level thô trước, mịn sau, và hàm điều kiện dừng sớm (từ metric các run đã xong).
15a. `RunExecutor.process_batch` truyền `image_id` trong mỗi phần tử của `targets`.
16. `[agent: worker]` `_run_bundle` gọi hàm dừng sớm trước mỗi run và báo `skipped` (`early_stop`) qua API nội bộ cho level lớn hơn chưa chạy; chạy tiếp sau gián đoạn thì tính lại từ bundle.
17. Tích hợp patch vào `RunExecutor` (ml-core) và worker (`[agent: worker]`): tra `PatchArtifact` theo khóa → train nếu chưa có (báo tiến độ `phase = training`, lưu checkpoint patch qua presigned URL) → đánh giá. Train dùng `spec.training.batch_size`, không dùng batch size của cost profile (đề xuất contract 001).
18. Thêm `patch_key` vào `fingerprint_inputs`.
19. Tạo ảnh nhiễu / vùng khác biệt chung cho mọi loại biến đổi (|δ| chuẩn hóa).
20. `ml_core/metrics/ranking.py`: tính `auc_drop`, `max_relative_drop`, xử lý `early_stop` và thiếu dữ liệu.
20a. CLI `advertest slice create --exclude-slice <id>`: slice huấn luyện không giao với slice đánh giá.

## Group 4 — Làm mờ ảnh `[agent: ml-privacy]`

21. `ml_core/privacy/regions.py`: tính vùng làm mờ `rule_v1` từ ground truth, prediction sạch, prediction sau biến đổi, ignore region.
22. `ml_core/privacy/blur.py`: Gaussian + pixelate theo kích thước vùng.
23. Tích hợp vào bước tạo ảnh hiển thị (ảnh sạch, ảnh sau biến đổi, ảnh thứ ba) và thumbnail của failure case; ghi `anonymization` vào `FailureCaseRecord`; bảo đảm không ảnh hiển thị chưa làm mờ nào được upload.

## Group 5 — Backend `[agent: backend]`

24. Kiểm tra khi tạo experiment: `training_slice_id` bắt buộc với patch, cùng dataset version, **không giao** với slice đánh giá, tối đa 50 ảnh.
24a. Gán `ordinal` của run theo thứ tự thô → mịn (hàm của task 15).
24b. `GET /slices?disjoint_from=<slice_id>`: chỉ slice không giao với slice đó.
25. Ước lượng: `training_seconds` = `max_iter` × số ảnh slice huấn luyện × `sec_per_image_iteration` khi patch chưa có; cộng vào `total_seconds` và `exceeds_limit`.
26. Lưu và tra `PatchArtifact`; endpoint nội bộ cho worker tra và đăng ký patch; presigned URL cho khóa patch.
26a. Endpoint nội bộ báo run chưa start là `skipped` (`early_stop`).
27. `attack_ranking` trong `ExperimentDetail` bằng hàm của `ml_core/metrics/ranking.py`.
28. Cập nhật quy tắc `display_mode` theo `anonymization.applied`; `FailureCaseView` bỏ khóa MinIO khi ảnh bị ẩn.
28a. Câu tóm tắt và email có nhãn riêng cho `early_stop`.
29. Endpoint đọc catalog đầy đủ cho `/admin/attacks` (`attack_catalog.manage`).

## Group 6 — Frontend `[agent: frontend]`

30. Wizard bước 4: ba nhóm, chip severity, chọn slice huấn luyện cho patch (lọc slice giao nhau), preset "Toàn bộ catalog" (`adv_patch` 2 level: 0.1, 0.25), công tắc dừng sớm; nháp đổi khóa sang `advertest.wizard.v2`.
31. Hiển thị `training_seconds` trong ước lượng.
32. Tab Kết quả: bảng xếp hạng (có `coverage`), biểu đồ cột `auc_drop`, tùy chọn trục hoành chuẩn hóa; nhãn lý do `early_stop` trong bảng run.
33. Tiến độ hai giai đoạn cho run patch.
34. `CaseViewer`: nhãn ảnh thứ ba theo loại, dải "Đã làm mờ".
35. Trang `/admin/attacks`; thêm mục vào `NAV_ITEMS` (`frontend/src/nav/config.ts`, permission `attack_catalog.manage`, `implemented: true`). Admin khi đó có 5 mục, nên trên điện thoại hiện 3 mục + "Thêm". Dùng lại mẫu bảng/thẻ, `TruncatedId`, "Tải thêm" của Phase 4.

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

36. Viết test nghiệm thu `tests/acceptance/phase_06/` và kịch bản Playwright `frontend/e2e/phase_06/` theo `validation.md`.
36a. `scripts/e2e.sh` nạp seed `adv_patch` với `max_iter = 4` thay cho 200 (giữ `batch_size` của spec, đề xuất contract 001); fixture chỉ có 5 ảnh nên kịch bản patch cần slice đánh giá và slice huấn luyện tách từ 5 ảnh đó (ví dụ 3 và 2 ảnh, qua `--exclude-slice`).
37. Chạy experiment toàn catalog trên KITTI bằng laptop; hiệu chỉnh tham số patch.
38. Kiểm tra bằng mắt kết quả làm mờ; trả lời câu hỏi mở.
39. Cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
