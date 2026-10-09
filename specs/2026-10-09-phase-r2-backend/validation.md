# Validation: Phase R2 — Backend: insight, mở rộng qua cấu hình, thử nhanh

> Test trong `tests/acceptance/phase_r2/` do người duyệt viết hoặc duyệt; agent chỉ đọc. Test được thêm theo group (`plan.md` bước 3); ở mỗi thời điểm, mọi test đã có đều phải pass.

## Automated Tests

### Chung
- [ ] `make check` pass, gồm test nghiệm thu Phase 0–8 và R1.
- [ ] `make test-db` pass; golden R1 (CLI và worker) vẫn khớp.
- [ ] `spec_sha256` của 10 spec trong seed không đổi; `contracts-check` sạch.

### Group 1 — Insight và luồng (`test_insight.py`, `test_promote.py`, `test_templates.py`; `db`)
- [ ] Experiment fixture (run dựng sẵn qua API worker): `weaknesses` đúng thứ tự và tối đa 5; ma trận đủ 4 dải, ô trống là `null`; `partial` đúng khi có run `stopped_limit`.
- [ ] Bảng đầu vào → `Conclusion.code` (`no_data`, `robust`, `weak`, `weak_class`); cùng đầu vào cho cùng `text`.
- [ ] `mode`: experiment gắn protocol `dev` là `exploration`, protocol khác là `official`; lọc `?mode=` đúng.
- [ ] `promote`: trả bản nháp đủ attack bắt buộc với level bắt buộc ∪ level nguồn; không tạo experiment; nguồn `official` hoặc chưa kết thúc → 409; protocol đích không `active` → 409; tạo từ bản nháp có `promoted_from` và audit log.
- [ ] Template `draft` là `ProtocolCreate` hợp lệ, dùng spec `active`; tiêu chí gợi ý đúng ngưỡng theo `strictness`; không đổi khi DB có thêm kết quả experiment.
- [ ] `POST /experiments/draft` với từng preset: level đúng công thức, hợp level bắt buộc; `deep` thêm tìm ngưỡng (trừ patch); kết quả qua được `POST /experiments/estimate`.

### Group 2 — Adapter attack (`test_adapter_field.py`, `test_selfcheck.py`)
- [ ] Spec có `adapter` khác `effective_adapter` thì registry chọn theo `adapter`; spec seed (không có `adapter`) giữ builder cũ.
- [ ] `fixed_params` sai `params_schema` → lỗi kiểm tra.
- [ ] Spec seed pass cả 7 mục tự kiểm tra; với mỗi mục có một builder giả vi phạm và chỉ mục đó fail.

### Group 3 — Adapter model (`test_model_adapters.py`)
- [ ] Fixture ONNX: inference ra box `xyxy` trong không gian letterbox; `capabilities.gradients = false`; attack white-box → `skipped` (`incompatible`), corruption → `completed`.
- [ ] Fixture safetensors torchvision: inference và estimator ART chạy được FGSM một ảnh.
- [ ] `ModelProvider` LRU: model thứ 3 đẩy model ít dùng nhất ra khỏi cache.
- [ ] File pickle đổi đuôi `.safetensors` → nạp thất bại, không chạy code.

### Group 4 — Catalog, model, thử nhanh (`test_catalog_lifecycle.py`, `test_model_upload.py`, `test_quick_try_api.py`; `db`)
- [ ] Vòng đời `draft → checking → pending_approval → active`; version cũ chuyển `retired` cùng giao dịch; `check_failed` chạy lại được.
- [ ] Người tạo tự approve → 403; engineer approve → 403; reviewer khác người tạo → 200.
- [ ] Adapter không có trong registry hoặc `fixed_params` sai → 422; trùng `spec_sha256` → 409; version nhảy cóc → 422.
- [ ] Sửa metadata không đổi `spec_sha256`/version, có audit log.
- [ ] Experiment hoặc protocol dùng spec không `active` → 422; experiment cũ chốt spec `retired` vẫn đọc và chạy lại được.
- [ ] Upload `.pt`, `.pkl`, zip, hoặc file không phải safetensors/onnx → 422; model `checking`/`check_failed` không dùng được trong experiment.
- [ ] Thử nhanh: lượt thứ hai khi lượt đầu chưa xong → 429; spec patch → 422; `not_a_test_result = true`; không tạo experiment, run, failure case; sau `expires_at` (giả lập đồng hồ) dọn dẹp xóa object MinIO và `GET` → 410.
- [ ] Endpoint mới có `x-permission` đúng ma trận quyền (test ma trận Phase 4 mở rộng).

### Group 5 — Worker công cụ (`test_tool_worker.py`; `db`)
- [ ] `spec_check`, `model_check`, `quick_try` chạy hết vòng qua worker thật trên fixture; kết quả ghi qua endpoint worker.
- [ ] Thứ tự lease: `quick_try` trước job kiểm tra đã xếp trước đó.
- [ ] Mất lease → xếp lại, quá 2 lần → `failed`.
- [ ] Ảnh kết quả thử nhanh đi qua làm mờ (fixture có mặt người: vùng mặt khác ảnh gốc).
- [ ] `ModelProvider.get` lỗi trong kiểm gradient → run cần gradient `failed` (`error`), run corruption cùng experiment `completed`.

## Manual Checks

- [ ] Demo qua API:
  - experiment fixture có danh sách điểm yếu và ma trận;
  - nâng một experiment Khám phá thành experiment Chính thức mới;
  - admin tạo biến thể corruption (ví dụ `snow_light`: adapter `corruption.imagecorruptions`, `corruption = snow`, severity 1–3, nhãn level riêng), reviewer duyệt, spec có trong `GET /attack-specs`;
  - đăng ký một model ONNX và chạy corruption trên nó.
- [ ] Thử nhanh 5 level FGSM và fog trên CPU laptop: ghi thời gian vào `CHANGELOG.md` (mục tiêu < 10 giây khi model đã cache).
- [ ] Đọc 3 câu kết luận sinh từ experiment thật trên KITTI: câu đúng số liệu và đọc hiểu được.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass.
- [ ] Manual Checks đã làm; số liệu ghi vào `CHANGELOG.md`.
- [ ] Open Question số luồng torch đã có quyết định trong spec hoặc chuyển backlog.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase R2 được đánh dấu hoàn thành.
