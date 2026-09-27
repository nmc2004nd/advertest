# Plan: Phase 2 — Attack white-box đầu tiên

> Phân chia thư mục để các agent làm song song:
> `attacks/` (agent `attack`), `ml_core/metrics/` (agent `ml-metric`), `ml_core/runner/` và `ml_core/cli/` (agent `ml-core`).
>
> Thứ tự: Group 0 → (Group 1, Group 2 song song) → Group 3 → Group 4.

## Group 0 — Cập nhật contract và spec `[người duyệt]`

1. Thêm tham số `mask` vào interface `Perturbation`; cập nhật `tech-stack.md` mục 3.1.
2. Thêm `git_dirty` vào `Manifest.fingerprint_inputs`.
3. Thêm schema `FailureCaseRecord` và mock tương ứng.
4. Rà `contracts/seeds/attack_specs.json` cho `fgsm`, `pgd_linf`, `pgd_l2` theo bảng trong `requirements.md` (Phase 0 đã seed đúng bảng này, dự kiến không phải sửa); nếu sửa thì tăng `version` và tính lại `spec_sha256`.
5. Chạy `make contracts`, commit; ghi thay đổi vào `CHANGELOG.md`.

## Group 1 — Attack `[agent: attack]`

6. `attacks/registry.py`: đọc catalog, tra spec theo `name` hoặc `spec_sha256`.
7. `attacks/art_adapter.py`: lớp `ArtPerturbation` cài đặt `Perturbation`; dựng attack ART từ `art_class` và `fixed_params`; đổi đơn vị `level` → `eps`; tính `eps_step` theo `eps_step_ratio`; `targeted = False`; tắt thanh tiến độ của ART.
8. Truyền `mask` và nhãn ground truth vào `generate`; `level = 0` trả ngay bản sao của ảnh gốc.
9. Đặt seed toàn cục (numpy, torch) theo `seed` trước mỗi lần gọi `generate`.
10. Factory `build_perturbation(spec, estimator)`; kiểm tra `requires_gradients` so với năng lực estimator và ném lỗi `IncompatibleAttack` có thông điệp rõ ràng.
11. Unit test trong `attacks/tests/` dùng estimator giả (model nhỏ tuyến tính) để test chuẩn nhiễu, mask, `level = 0`.

## Group 2 — Metric sau tấn công `[agent: ml-metric]`

12. Hàm ghép prediction với ground truth một-một (score giảm dần, IoU ≥ 0.5, cùng class, score ≥ `operating_conf`).
13. Tính tập C trên ảnh sạch, số object mất, `attack_success_rate`.
14. Tính `new_false_positives` theo ảnh (loại prediction trong ignore region).
15. Tính `absolute_drop`, `relative_drop` (xử lý trường hợp mAP sạch bằng 0).
16. Tính `severity_score` và chọn top failure case theo quy tắc xác định.
17. Unit test với dữ liệu tổng hợp: ASR = 0 khi không mất gì, ASR = 1 khi mất hết, `|C| = 0` trả `null`.

## Group 3 — Runner, manifest, CLI `[agent: ml-core]`

18. `ml_core/runner/config.py`: schema `LocalRunConfig`, đọc YAML, tính `experiment_id`.
19. `ml_core/runner/env.py`: lấy `git_commit`, `git_dirty`, phiên bản thư viện, thông tin GPU/CUDA/driver, `docker_image_digest`.
20. `ml_core/runner/fingerprint.py`: dựng `fingerprint_inputs` cho từng run, gọi `compute_fingerprint` từ contract.
21. `ml_core/runner/run.py`: với mỗi (attack, level): kiểm tra cache theo fingerprint → kiểm tra tương thích → chạy attack theo batch (tạo mask từ thông tin letterbox) → predict trên ảnh sau tấn công → tính metric → chọn failure case → lưu artifact → ghi manifest và `RunResult`.
22. Bắt ngoại lệ theo từng run: ghi `status = failed` kèm thông điệp, tiếp tục run kế tiếp.
23. Cờ `--force`: chạy lại vào `runs/<fingerprint>/reruns/<run_id>/`, không ghi đè.
24. Xuất ảnh PNG: ảnh sạch, ảnh sau tấn công, ảnh nhiễu khuếch đại.
25. Lệnh `advertest run --config` (in tiến độ, bảng tóm tắt) và `advertest run show <fingerprint>`.
26. Viết file cấu hình mẫu `configs/examples/pgd_sweep.yaml` (PGD L∞ với eps 2, 4, 8, 16 và FGSM với eps 4, 8).

## Group 4 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

27. Viết test nghiệm thu `tests/acceptance/phase_02/` theo `validation.md`.
28. Chạy trên fixture, ghi golden value vào `tests/fixtures/golden/phase_02.json`.
29. Chạy `pgd_sweep.yaml` trên slice KITTI 300 ảnh bằng GPU local; ghi bảng kết quả và thời gian vào `CHANGELOG.md`.
30. Chạy lại cùng cấu hình với `--force`, so sánh với lần đầu.
31. Mở vài failure case, kiểm tra bằng mắt ảnh nhiễu và box.
32. Trả lời các câu hỏi mở; cập nhật `requirements.md` và seed catalog nếu cần.
33. Cập nhật `roadmap.md`, `CHANGELOG.md`; merge.
