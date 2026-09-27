# Validation: Phase 1 — Inference và metric

> Test trong `tests/acceptance/phase_01/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Toàn bộ test tự động chạy được trên CPU bằng fixture của Phase 0.

## Automated Tests

### Chung
- [ ] `make check` pass (lint, type check, unit test, test nghiệm thu Phase 0 và Phase 1).
- [ ] `make contracts` không tạo thay đổi so với bản đã commit.
- [ ] Mock `ModelCard` và `CleanEvalResult` validate được.
- [ ] `advertest --help` liệt kê đủ các nhóm lệnh `model`, `dataset`, `slice`, `mapping`, `eval`, `viz`.

### Letterbox — `test_letterbox.py`
- [ ] Ảnh 1242×375 sau letterbox có kích thước 640×640, vùng pad có giá trị 114/255.
- [ ] Chuyển một box sang không gian letterbox rồi chuyển ngược: sai lệch mỗi tọa độ ≤ 1 pixel.
- [ ] Box sau letterbox nằm trong khung [0, 640].

### Dữ liệu — `test_data.py`
- [ ] Parser đọc đúng bbox, class, truncated, occluded từ một dòng label KITTI mẫu.
- [ ] `DontCare` trở thành ignore region, không trở thành annotation.
- [ ] Sau khi áp mapping `kitti-coco`: `Van` → `car`, `Person_sitting` → `person`, `Cyclist` trở thành ignore region với `source = unmapped:Cyclist`.
- [ ] Import hai lần trên cùng dữ liệu cho cùng `dataset_version_sha256`.
- [ ] Sửa một dòng label → `dataset_version_sha256` khác.
- [ ] `slice create` cùng seed cho cùng `image_ids_sha256`; khác seed cho kết quả khác.
- [ ] Mọi ảnh trong slice mặc định có ít nhất 1 object đã map.
- [ ] ID của slice, mapping và dataset là uuid5 xác định từ hash (tính lại cho cùng giá trị).
- [ ] Cùng danh sách image ID nhưng khác `dataset_version_sha256` → `slice_sha256` và `id` khác nhau.
- [ ] `import-kitti` trên `tests/fixtures/kitti/` chạy được và cho manifest validate được.
- [ ] GT `Car` cao 20px (ảnh gốc) → ignore region `difficulty:Car`; GT `Car` có `occluded = 2` hoặc `truncated = 0.5` → ignore region; GT `Car` cao 30px, `occluded = 1`, `truncated = 0.2` → giữ làm annotation.
- [ ] Ảnh chỉ có object bị chuyển thành ignore region do độ khó không lọt vào slice mặc định.

### Model — `test_model.py`
- [ ] Prediction của wrapper khớp predict gốc của Ultralytics trên 5 ảnh fixture: cùng số box; mỗi box ghép cặp có IoU ≥ 0.99, cùng class, chênh lệch score < 1e-3.
- [ ] Output predict đúng định dạng: list độ dài N, mỗi phần tử có `boxes` (K×4, xyxy), `labels` (K), `scores` (K).
- [ ] `estimator.predict` và `estimator.loss_gradient` chạy được với input `(N, 3, 640, 640)`.
- [ ] Gradient hữu hạn (không NaN/Inf) và không toàn 0.
- [ ] Một bước `x + 2/255 · sign(grad)` (cắt về [0, 1]) làm loss tăng.
- [ ] Hash `state_dict` và running mean/var của BatchNorm giống hệt trước và sau khi gọi `loss_gradient`.
- [ ] `model register` trên weights fixture tạo `ModelCard` hợp lệ với `supports_gradients = true`.
- [ ] Đăng ký lại cùng weights cho cùng `id`.
- [ ] Một model giả có gradient bằng 0 (fixture test) → `supports_gradients = false` và `gradient_check.details` ghi lý do.

### Metric — `test_metric.py`
- [ ] Prediction trùng hệt ground truth (score 1.0) → mAP@0.5 = 1.0.
- [ ] Không có prediction nào → mAP@0.5 = 0.
- [ ] Một prediction nằm hoàn toàn trong ignore region không làm giảm mAP (so với khi không có prediction đó).
- [ ] Prediction thuộc class không có trong mapping (ví dụ `traffic light`) không làm thay đổi mAP.
- [ ] `per_class` có đủ các class đích `car`, `truck`, `person` với `num_gt` đúng; trên fixture (sau mapping `kitti-coco` và lọc Moderate) là `car = 14`, `truck = 1`, `person = 6`.

### Đánh giá và cache — `test_eval.py`
- [ ] `advertest eval` trên fixture xuất file validate được theo `CleanEvalResult`.
- [ ] mAP@0.5 và mAP@0.5:0.95 trên fixture nằm trong ±0.01 so với `tests/fixtures/golden/phase_01.json`.
- [ ] Chạy lần hai cùng tham số: `cache.hit = true` và model không được gọi (kiểm tra bằng mock/spy).
- [ ] Đổi `inference_params.conf` → cache miss.
- [ ] Đổi mapping (cùng model, cùng slice, cùng tham số) → cache hit, metric được tính lại.
- [ ] `inference_params` trong kết quả ghi đúng `conf = 0.001`, `iou = 0.7`, `max_det = 300`, `operating_conf = 0.25`.

## Manual Checks

- [ ] Tải KITTI (split training) vào `data/raw/kitti/`, chạy `dataset import-kitti` thành công; ghi lại số ảnh và `dataset_version_sha256`.
- [ ] Tạo slice 300 ảnh, seed 42; tạo mapping `kitti-coco`.
- [ ] Chạy `advertest eval` trên GPU local; ghi baseline mAP@0.5, mAP@0.5:0.95, `sec_per_image`, batch size dùng được vào `CHANGELOG.md`.
- [ ] Chạy `eval` lần hai trên GPU: xác nhận cache hit và thời gian giảm rõ rệt.
- [ ] Chạy `viz` với 8 ảnh: box ground truth và prediction khớp vị trí object; ignore region phủ đúng người đi xe đạp và vùng `DontCare`.
- [ ] Nếu mAP@0.5 sạch < 0.4: ghi nhận vào `roadmap.md` mục Backlog kèm con số, để quyết định fine-tune hoặc đổi kích thước đầu vào.
- [ ] Theo dõi VRAM khi chạy eval trên laptop; ghi batch size lớn nhất chạy ổn định.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; baseline đã ghi lại.
- [ ] Người duyệt đã chấp nhận thay đổi contract (`ModelCard`, `CleanEvalResult`).
- [ ] Câu hỏi mở về baseline đã có câu trả lời hoặc đã chuyển vào backlog.
- [ ] Nếu phương án Faster R-CNN đã kích hoạt: `requirements.md` và `tech-stack.md` đã cập nhật tương ứng.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 1 được đánh dấu hoàn thành.
