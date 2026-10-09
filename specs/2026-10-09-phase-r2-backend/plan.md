# Plan: Phase R2 — Backend: insight, mở rộng qua cấu hình, thử nhanh

> Phân chia thư mục:
> `contracts/`, `tests/acceptance/phase_r2/` (người duyệt); `attacks/` (agent `attack`); `ml_core/models/` (agent `ml-model`); `ml_core/runner/`, `backend/worker/` (agent `worker`); `backend/app/`, `backend/migrations/`, `backend/admin_cli/` (agent `backend`); `pyproject.toml`/`uv.lock` chỉ để thêm `onnxruntime`, `safetensors` đã duyệt (agent `ml-model`).
>
> Thứ tự: Group 0 → (Group 1 ∥ Group 2 ∥ Group 3) → Group 4 → Group 5 → Group 6.
> Group 1 (insight) không phụ thuộc các group khác nên làm được ngay sau Group 0.
> Group rủi ro, cần review riêng ngay sau khi làm: Group 0 (contract), Group 4 (migration, quyền), Group 5 (worker).

## Group 0 — Contract và test nghiệm thu `[người duyệt]`

1. Đổi contract theo `requirements.md` mục Data / Fields; `make contracts`; seed `protocol_templates.json` và `experiment_presets.json`.
2. Duyệt và pin `onnxruntime`, `safetensors` trong `tech-stack.md` mục 11.
3. Viết test nghiệm thu theo group (test của group chưa làm chỉ commit trên `phaser2-reviewer`, như R1).
4. Thêm model fixture ONNX nhỏ và một safetensors torchvision vào fixture (sha256 trong `tests/fixtures/checksums.json`).

## Group 1 — Insight, template, preset, Khám phá/Chính thức `[agent: backend]`

5. `backend/app/insight/`: tính điểm yếu, ma trận và câu kết luận từ run và search result; `GET /experiments/{id}/insight`.
6. `mode` trong `ExperimentSummary`/`ExperimentDetail`; lọc `?mode=` ở `GET /experiments`.
7. `GET /protocol-templates`, `GET /protocol-templates/{key}/draft` (gợi ý tiêu chí), `GET /experiment-presets`, `POST /experiments/draft`.
8. `POST /experiments/{id}/promote`; `promoted_from` khi tạo (cột mới, audit log).
9. Unit test luật điểm yếu, dải, câu kết luận (bảng đầu vào → đầu ra).

## Group 2 — Adapter attack và tự kiểm tra spec `[agent: attack]`

10. Registry đọc `spec.adapter` trước `effective_adapter`; mỗi builder khai báo `params_schema` (JSON Schema của `fixed_params`); hàm liệt kê adapter cho `GET /attack-adapters`.
11. `attacks/selfcheck.py`: 7 mục kiểm tra, trả `SpecCheckResult`; chạy được cả từ CLI (`python -m attacks.selfcheck <spec.json>`).
12. Unit test: spec seed pass toàn bộ; builder giả vi phạm từng mục thì fail đúng mục.

## Group 3 — Adapter model `[agent: ml-model]`

13. Thêm dependency `onnxruntime`, `safetensors` (đã duyệt ở Group 0).
14. `TorchvisionDetectionAdapter` (danh sách kiến trúc cho phép, safetensors, estimator ART); `OnnxAdapter` (hai layout đầu ra, không gradient).
15. `ModelProvider`: đăng ký adapter theo `framework`; cache LRU giới hạn; hàm `check_model(card, weights_path) → ModelCheckResult` (nạp, sha, inference fixture, số class, gradient).
16. Unit test trên fixture ONNX và safetensors.

## Group 4 — Catalog, model qua web, thử nhanh (API) `[agent: backend]`

17. Migration `0011_phase_r2` (status spec, metadata, model status, `tool_jobs`, `quick_tries`, `promoted_from`; backfill; GRANT).
18. Vòng đời spec: tạo, xếp `spec_check`, approve/reject (người duyệt khác người tạo), metadata + audit log, `GET /attack-specs` chỉ trả `active`; experiment/protocol chỉ nhận spec `active`.
19. Upload và đăng ký model: presigned PUT, kiểm định dạng, `model_check`, chỉ model `ready` dùng được.
20. Thử nhanh: `POST/GET /quick-tries`, giới hạn 1 lượt, 410 sau khi hết hạn, job dọn dẹp định kỳ.
21. Endpoint worker cho job công cụ: `tool-lease`, `tool-jobs/{id}`, `result`, heartbeat; thứ tự lease.

## Group 5 — Worker công cụ và tồn đọng R1 `[agent: worker]`

22. `advertest-worker --tools`: lease và chạy `spec_check` (gọi `attacks.selfcheck`), `model_check` (gọi `check_model`), `quick_try` (mọi level, làm mờ, ghép object theo IoU, upload ảnh).
23. Lỗi `ModelProvider.get` trong kiểm gradient chỉ làm run cần gradient `failed` (tồn đọng R1 Group 5).
24. Đo thời gian thử nhanh (5 level FGSM và fog, CPU, model đã cache); ghi vào handoff.

## Group 6 — Kiểm tra cuối `[người duyệt]`

25. `make check`, `make test-db`; `phase-review` cả phase.
26. Demo qua API (kịch bản trong `validation.md`); quyết Open Question số luồng torch; `phase-close`.
