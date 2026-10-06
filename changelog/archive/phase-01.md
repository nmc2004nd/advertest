## Phase 1 — Inference và metric

**Trạng thái:** ✅ hoàn thành 2026-09-28, **còn tồn đọng** (người dùng cho phép đóng phase và cập nhật sau). Group 0–6 đã merge; mục chi tiết từng group (`### Phase 1 — Group …`) nằm bên dưới, xen với mục Phase 0 theo thứ tự thời gian.

### Phase 1 — Tổng kết (phase-close) — 2026-09-28
- **Giao được:** CLI `advertest` chạy trọn `dataset import-kitti` → `model register` → `slice create` → `mapping create` → `eval` → `viz`; wrapper YOLOv8n cho ART (model luôn ở eval, bài kiểm tra gradient); converter KITTI, mapping `kitti-coco` có lọc Moderate, slice theo hash; mAP bằng torchmetrics/pycocotools theo `max_det`; cache prediction thô; kho `LocalStore` bất biến.
- **Contract:** `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping`; `IgnoreRegion.source` chấp nhận `difficulty:`. Người duyệt đã chấp nhận.
- **Số liệu cuối:** `make check` pass trên `main` (376 test Python, 94 test nghiệm thu gồm 42 của Phase 1, 36 test Vitest). Baseline KITTI (CPU): mAP@0.5 = 0.533, mAP@0.5:0.95 = 0.304; golden trên fixture 0.5186 / 0.3524.
- **`validation.md`:** 42/42 Automated Tests; 4/7 Manual Checks; Definition of Done 5/6.
- **CI:** xanh sau khi push `main` gồm phần đóng phase (người dùng xác nhận); đánh dấu Definition of Done "Automated Tests pass trên CI".
- **Tồn đọng (cập nhật khi có kết quả):**
  - 3 manual check cần GPU: `eval` trên GPU local (ghi `sec_per_image`, batch size), lần hai trên GPU (cache hit nhanh rõ rệt), theo dõi VRAM và batch size lớn nhất. Máy phát triển hiện không có GPU; baseline đang là số đo CPU.
- **Lưu ý:** các group của người duyệt (0, 6) và việc review, merge do agent làm thay theo ủy quyền của người dùng; review do chính agent đã viết code thực hiện nên không phải review độc lập.

### Replan sau Phase 1 — 2026-09-28
- Phase 2 `requirements.md`: nhãn cho attack lấy từ `SliceLoader` (chỉ số class trong model); mask dựng từ `LetterboxInfo`; mAP sau tấn công qua `CleanMetric` theo `max_det`, mAP sạch từ cache Phase 1; `config_sha256` dùng `LETTERBOX_CONFIG`; `git_commit` lấy như `advertest eval`; câu hỏi mở mới về `Truck`/`bus` trong preset `kitti-coco` (chốt trước golden Phase 2).
- Phase 2 `plan.md` task 19: chuyển `current_git_commit`, `describe_device` sang `ml_core/runner/env.py` để `eval` và `run` dùng chung.
- `roadmap.md` Phase 3: thêm mục "(Từ Phase 1)" (ảnh theo sha256 trên MinIO thay đường dẫn tuyệt đối, `DEFAULT_STORE_DIR`, `import-local` đọc bố cục `LocalStore`, chỉ admin đăng ký model).
- Rủi ro: PGD trên CPU ước khoảng 2 s/ảnh (khoảng 1 giờ cho sweep 6 mức eps trên 300 ảnh); ảnh KITTI của Ultralytics là JPEG mang đuôi `.png` (content-type trên MinIO phải theo định dạng thật).
- Câu hỏi còn mở: YOLOv8 hay YOLOv11.
