# Plan: Phase 1 — Inference và metric

> Toàn bộ phase thuộc phần ML core, nhưng được chia thành các thư mục con riêng để có thể giao cho nhiều agent song song mà không đụng file của nhau:
> `ml_core/data/` (agent `ml-data`), `ml_core/models/` (agent `ml-model`), `ml_core/metrics/` (agent `ml-metric`), `ml_core/cli/` và `ml_core/store/` (agent `ml-core`).
>
> Thứ tự: Group 0 → Group 1 → (Group 2, 3, 4 song song) → Group 5 → Group 6.

## Group 0 — Cập nhật contract `[người duyệt]`

1. Thêm `ModelCard` và `CleanEvalResult` vào `contracts/python/advertest_contracts/`, tăng `schema_version` của gói contract.
2. Thêm mock cho hai schema mới vào `contracts/mocks/`.
3. Chạy `make contracts`, commit file sinh ra.
4. Ghi thay đổi contract vào `CHANGELOG.md`.

## Group 1 — Nền tảng dùng chung `[agent: ml-core]`

5. `ml_core/store/`: interface `ArtifactStore` (`put`, `get`, `exists`, `list`) và cài đặt `LocalStore` tại `data/store/`.
6. `ml_core/ids.py`: hàm `content_id(sha256) -> UUID` dùng uuid5 với namespace cố định của dự án.
7. `ml_core/preprocess/letterbox.py`: letterbox ảnh về 640×640 (pad 114/255), trả `scale` và `pad`; hàm chuyển box sang không gian letterbox và chuyển ngược.
8. Khung CLI `advertest` (Typer) với các nhóm lệnh rỗng: `model`, `dataset`, `slice`, `mapping`, `eval`, `viz`.

## Group 2 — Dữ liệu `[agent: ml-data]`

9. Parser file label KITTI: đọc bbox (left, top, right, bottom), class, truncated, occluded.
10. Converter `import-kitti`: duyệt ảnh và label, tính sha256 từng ảnh, tạo manifest nội bộ, ghi ignore region cho `DontCare`.
11. Preset mapping `kitti-coco` theo bảng trong `requirements.md`; class không map được chuyển thành ignore region khi áp mapping.
12. Tạo và lưu class mapping có hash (`mapping create`).
13. Tạo slice: lọc ảnh có ít nhất 1 object đã map, lấy mẫu theo seed, sắp xếp ID, tính hash (`slice create`).
14. Dataset loader: nạp ảnh theo slice, áp letterbox cho ảnh, ground truth và ignore region; trả batch numpy float32 channels_first [0, 1].
15. Lệnh CLI `dataset import-kitti`, `mapping create`, `slice create`.

## Group 3 — Model `[agent: ml-model]`

16. Wrapper Ultralytics: chế độ predict (NMS với `conf`, `iou`, `max_det` truyền vào) trả list dict đúng quy ước.
17. Chế độ loss: tính loss detection của Ultralytics trên target đã letterbox, model ở eval mode, trả loss vô hướng khả vi theo input.
18. Tạo estimator ART (`PyTorchYolo`, hoặc estimator riêng nếu không tương thích) với `input_shape=(3, 640, 640)`, `clip_values=(0, 1)`, `channels_first=True`.
19. Bài kiểm tra gradient: gradient hữu hạn và khác 0; một bước theo dấu gradient làm loss tăng; hash `state_dict` và running stats BatchNorm không đổi.
20. Lệnh `model register`: tính hash weights, chạy bài kiểm tra gradient trên fixture, ghi `ModelCard`.
21. Nếu đến hết ngày thứ 2 của group này mà bài kiểm tra gradient vẫn fail: dừng, báo người duyệt để quyết định kích hoạt phương án Faster R-CNN.

## Group 4 — Metric `[agent: ml-metric]`

22. Lọc prediction: bỏ class không có trong mapping, đổi label sang class đích.
23. Lọc ignore region: bỏ prediction có IoA ≥ 0.5 với bất kỳ ignore region nào của ảnh.
24. Tính mAP@0.5, mAP@0.5:0.95 và metric theo class bằng `torchmetrics`.
25. Hàm tạo `CleanEvalResult` từ metric, thông tin model, slice, mapping, timing, thiết bị, phiên bản thư viện.

## Group 5 — Đánh giá, cache, trực quan hóa `[agent: ml-core]`

26. Tính khóa cache prediction theo `requirements.md`.
27. Lệnh `eval`: kiểm tra cache → nếu miss thì chạy predict theo batch và lưu prediction thô → lọc → tính metric → ghi `CleanEvalResult`.
28. Batch size là tham số; xử lý lỗi hết VRAM bằng thông báo rõ ràng gợi ý giảm batch size.
29. Lệnh `viz`: vẽ ground truth (xanh), prediction (đỏ), ignore region (xám) lên ảnh letterbox, xuất PNG.

## Group 6 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

30. Viết test nghiệm thu `tests/acceptance/phase_01/` theo `validation.md`.
31. Chạy `advertest eval` trên fixture, ghi golden value vào `tests/fixtures/golden/phase_01.json`.
32. Tải KITTI, chạy toàn bộ luồng trên slice 300 ảnh bằng GPU local, ghi baseline mAP và thời gian mỗi ảnh vào `CHANGELOG.md`.
33. Chạy `viz`, kiểm tra bằng mắt ít nhất 8 ảnh.
34. Trả lời câu hỏi mở về baseline; cập nhật `requirements.md` nếu cần.
35. Cập nhật `roadmap.md`, `CHANGELOG.md`; merge.
