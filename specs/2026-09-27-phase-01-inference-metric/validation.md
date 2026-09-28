# Validation: Phase 1 — Inference và metric

> Test trong `tests/acceptance/phase_01/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Toàn bộ test tự động chạy được trên CPU bằng fixture của Phase 0.

## Automated Tests

### Chung
- [x] `make check` pass (lint, type check, unit test, test nghiệm thu Phase 0 và Phase 1).
- [x] `make contracts` không tạo thay đổi so với bản đã commit.
- [x] Mock `ModelCard`, `CleanEvalResult`, `SliceSpec`, `ClassMapping` validate được.
- [x] `IgnoreRegion` chấp nhận `source = difficulty:Car`; manifest fixture giữ nguyên `dataset_version_sha256`.
- [x] `advertest --help` liệt kê đủ các nhóm lệnh `model`, `dataset`, `slice`, `mapping`, `eval`, `viz`.

### Letterbox — `test_letterbox.py`
- [x] Ảnh 1242×375 sau letterbox có kích thước 640×640, vùng pad có giá trị 114/255.
- [x] Chuyển một box sang không gian letterbox rồi chuyển ngược: sai lệch mỗi tọa độ ≤ 1 pixel.
- [x] Box sau letterbox nằm trong khung [0, 640].

### Dữ liệu — `test_data.py`
- [x] Parser đọc đúng bbox, class, truncated, occluded từ một dòng label KITTI mẫu.
- [x] `DontCare` trở thành ignore region, không trở thành annotation.
- [x] Sau khi áp mapping `kitti-coco`: `Van` → `car`, `Person_sitting` → `person`, `Cyclist` trở thành ignore region với `source = unmapped:Cyclist`.
- [x] Import hai lần trên cùng dữ liệu cho cùng `dataset_version_sha256`.
- [x] Sửa một dòng label → `dataset_version_sha256` khác.
- [x] `slice create` cùng seed cho cùng `image_ids_sha256`; khác seed cho kết quả khác.
- [x] Mọi ảnh trong slice mặc định có ít nhất 1 object đã map.
- [x] ID của slice, mapping và dataset là uuid5 xác định từ hash (tính lại cho cùng giá trị).
- [x] Cùng danh sách image ID nhưng khác `dataset_version_sha256` → `slice_sha256` và `id` khác nhau.
- [x] `import-kitti` trên `tests/fixtures/kitti/` chạy được và cho manifest validate được.
- [x] GT `Car` cao 20px (ảnh gốc) → ignore region `difficulty:Car`; GT `Car` có `occluded = 2` hoặc `truncated = 0.5` → ignore region; GT `Car` cao 30px, `occluded = 1`, `truncated = 0.2` → giữ làm annotation.
- [x] Ảnh chỉ có object bị chuyển thành ignore region do độ khó không lọt vào slice mặc định.
- [x] `slice create` chạy được mà không cần model hay mapping; đổi một ngưỡng trong `filter.difficulty` → `slice_sha256` khác.
- [x] File slice và mapping lưu trong store validate được theo `SliceSpec` và `ClassMapping`.

### Model — `test_model.py`
- [x] Prediction của wrapper khớp predict gốc của Ultralytics trên 5 ảnh fixture: cùng số box; mỗi box ghép cặp có IoU ≥ 0.99, cùng class, chênh lệch score < 1e-3.
- [x] Output predict đúng định dạng: list độ dài N, mỗi phần tử có `boxes` (K×4, xyxy), `labels` (K), `scores` (K).
- [x] `estimator.predict` và `estimator.loss_gradient` chạy được với input `(N, 3, 640, 640)`.
- [x] Gradient hữu hạn (không NaN/Inf) và không toàn 0.
- [x] Một bước `x + 2/255 · sign(grad)` (cắt về [0, 1]) làm loss tăng.
- [x] Hash `state_dict` và running mean/var của BatchNorm giống hệt trước và sau khi gọi `loss_gradient`.
- [x] `model register` trên weights fixture tạo `ModelCard` hợp lệ với `supports_gradients = true`.
- [x] Đăng ký lại cùng weights cho cùng `id`.
- [x] Một model giả có gradient bằng 0 (fixture test) → `supports_gradients = false` và `gradient_check.details` ghi lý do.

### Metric — `test_metric.py`
- [x] Prediction trùng hệt ground truth (score 1.0) → mAP@0.5 = 1.0.
- [x] Không có prediction nào → mAP@0.5 = 0.
- [x] `MeanAveragePrecision` chạy với backend `pycocotools` trên CPU.
- [x] Một prediction nằm hoàn toàn trong ignore region không làm giảm mAP (so với khi không có prediction đó).
- [x] Prediction thuộc class không có trong mapping (ví dụ `traffic light`) không làm thay đổi mAP.
- [x] `per_class` có đủ các class đích `car`, `truck`, `person` với `num_gt` đúng; trên fixture (sau mapping `kitti-coco` và lọc Moderate) là `car = 14`, `truck = 1`, `person = 6`.

### Đánh giá và cache — `test_eval.py`
- [x] `advertest eval` trên fixture xuất file validate được theo `CleanEvalResult`.
- [x] mAP@0.5 và mAP@0.5:0.95 trên fixture nằm trong ±0.01 so với `tests/fixtures/golden/phase_01.json`.
- [x] Chạy lần hai cùng tham số: `cache.hit = true` và model không được gọi (kiểm tra bằng mock/spy).
- [x] Đổi `inference_params.conf` → cache miss.
- [x] Đổi mapping (cùng model, cùng slice, cùng tham số) → cache hit, metric được tính lại.
- [x] `inference_params` trong kết quả ghi đúng `conf = 0.001`, `iou = 0.7`, `max_det = 300`, `operating_conf = 0.25`.

## Manual Checks

- [x] Tải KITTI (split training) vào `data/raw/kitti/`, chạy `dataset import-kitti` thành công; ghi lại số ảnh và `dataset_version_sha256`.
- [x] Tạo slice 300 ảnh, seed 42; tạo mapping `kitti-coco`.
- [ ] Chạy `advertest eval` trên GPU local; ghi baseline mAP@0.5, mAP@0.5:0.95, `sec_per_image`, batch size dùng được vào `CHANGELOG.md`.
- [ ] Chạy `eval` lần hai trên GPU: xác nhận cache hit và thời gian giảm rõ rệt.
- [x] Chạy `viz` với 8 ảnh: box ground truth và prediction khớp vị trí object; ignore region phủ đúng người đi xe đạp và vùng `DontCare`.
- [x] Nếu mAP@0.5 sạch < 0.4: ghi nhận vào `roadmap.md` mục Backlog kèm con số, để quyết định fine-tune hoặc đổi kích thước đầu vào.
- [ ] Theo dõi VRAM khi chạy eval trên laptop; ghi batch size lớn nhất chạy ổn định.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; baseline đã ghi lại.
- [x] Người duyệt đã chấp nhận thay đổi contract (`ModelCard`, `CleanEvalResult`).
- [x] Câu hỏi mở về baseline đã có câu trả lời hoặc đã chuyển vào backlog.
- [x] Nếu phương án Faster R-CNN đã kích hoạt: `requirements.md` và `tech-stack.md` đã cập nhật tương ứng.
- [x] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 1 được đánh dấu hoàn thành.
