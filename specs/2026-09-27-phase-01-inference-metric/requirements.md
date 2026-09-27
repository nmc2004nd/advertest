# Requirements: Phase 1 — Inference và metric

## Scope

Đo được hiệu năng của model detection trên ảnh sạch, theo cách tái lập được và sẵn sàng cho attack ở Phase 2. Kết quả của phase gồm:

1. **Model wrapper cho ART**: bọc Ultralytics YOLO thành estimator của ART, có hai chế độ: tính loss (để lấy gradient) và predict.
2. **Đăng ký model**: tạo model card có hash weights, kèm bài kiểm tra gradient tự động quyết định cờ `supports_gradients`.
3. **Converter KITTI** sang manifest nội bộ, kèm map class về class của model.
4. **Dataset version và slice** định danh bằng hash, tạo được slice cố định khoảng 300 ảnh.
5. **Metric** mAP@0.5 và mAP@0.5:0.95, có xử lý vùng bỏ qua (ignore region).
6. **Cache prediction** trên ảnh sạch.
7. **CLI** `advertest eval` xuất kết quả JSON đúng contract.

Đây là mốc bắt buộc của tuần 1: cuối phase, CLI in được mAP của YOLO trên slice KITTI.

## Out of Scope

- Attack và biến đổi ảnh (Phase 2).
- Ghi vào Postgres, gọi API, dùng MinIO (Phase 3). Phase này làm việc với kho lưu trữ trên đĩa local.
- Converter YOLO và COCO, upload dataset qua web (Phase 10).
- Fine-tune model trên KITTI. Nếu baseline quá thấp, ghi nhận và đưa vào backlog để quyết định sau.
- Faster R-CNN. Chỉ làm nếu phương án dự phòng được kích hoạt (xem Decisions).
- Calibration cost profile (Phase 3).
- Làm mờ mặt và biển số (Phase 10).

## Data / Fields

### Thay đổi contract (cần người duyệt chấp nhận)

Thêm schema mới `CleanEvalResult` vào `contracts/`, và thêm `ModelCard` để mô tả model đã đăng ký. Đây là thay đổi contract nên phải được người duyệt thêm và merge trước khi agent bắt đầu Group 4 trong `plan.md`.

**`ModelCard`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid | ✓ | uuid5 từ `weights_sha256` |
| `name` | string | ✓ | Ví dụ `yolov8n-coco` |
| `framework` | string | ✓ | `ultralytics` |
| `architecture` | string | ✓ | Ví dụ `yolov8n` |
| `weights_sha256` | string | ✓ | |
| `class_names` | string[] | ✓ | Theo thứ tự index của model |
| `input_size` | int | ✓ | 640 |
| `supports_gradients` | bool | ✓ | Chỉ `true` khi bài kiểm tra gradient pass |
| `gradient_check` | object | ✓ | `passed`, `checked_at`, `details` (lý do nếu fail) |
| `lib_versions` | object | ✓ | `torch`, `ultralytics`, `art` |

**`CleanEvalResult`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `model` | object | ✓ | `id`, `weights_sha256` |
| `slice` | object | ✓ | `id`, `image_ids_sha256`, `dataset_version_sha256` |
| `class_mapping_sha256` | string | ✓ | |
| `inference_params` | object | ✓ | `conf`, `iou`, `max_det`, `operating_conf`, `input_size` |
| `metrics` | object | ✓ | `map50`, `map50_95`, `per_class` (mỗi class: `ap50`, `ap50_95`, `num_gt`) |
| `num_images` | int | ✓ | |
| `cache` | object | ✓ | `key`, `hit` (bool) |
| `timing` | object | ✓ | `total_s`, `sec_per_image` |
| `device` | string | ✓ | Ví dụ `cuda:0 (NVIDIA ...)` hoặc `cpu` |
| `lib_versions` | object | ✓ | |
| `git_commit` | string | ✓ | |

### Manifest dataset nội bộ

| Phần | Nội dung |
|---|---|
| `images` | `image_id`, `file_name`, `sha256`, `width`, `height`, `attributes` |
| `annotations` | `image_id`, `bbox` (xyxy, **pixel của ảnh gốc**), `category`, `attributes` (`truncated`, `occluded`) |
| `ignore_regions` | `image_id`, `bbox` (xyxy, pixel ảnh gốc), `source` (`dont_care` hoặc `unmapped:<class>`) |
| `categories` | Danh sách class gốc của dataset |
| `source` | `format` (`kitti`), `split`, thông tin converter |

Hash của dataset version là sha256 của manifest đã chuẩn hóa (`canonical_json`).

### Class mapping mặc định KITTI → COCO

| Class KITTI | Class model | Xử lý |
|---|---|---|
| `Car`, `Van` | `car` | Tính vào metric |
| `Truck` | `truck` | Tính vào metric |
| `Pedestrian`, `Person_sitting` | `person` | Tính vào metric |
| `Cyclist`, `Tram`, `Misc` | — | Chuyển thành ignore region |
| `DontCare` | — | Chuyển thành ignore region |

Class mapping là một file JSON riêng, có hash, tham chiếu đến dataset version và model.

### Slice

| Field | Notes |
|---|---|
| `id` | uuid5 từ `image_ids_sha256` |
| `dataset_version_sha256` | |
| `filter` | Mặc định: ảnh có ít nhất 1 object thuộc class đã map |
| `seed` | |
| `size` | Mặc định 300 |
| `image_ids` | Danh sách đã sắp xếp |
| `image_ids_sha256` | |

## Behaviour

### Letterbox
- Resize giữ tỉ lệ để cạnh dài bằng 640, pad về 640×640 bằng giá trị 114/255, căn giữa.
- Lưu `scale` và `pad` để chuyển ngược tọa độ.
- Ground truth và ignore region được chuyển sang không gian letterbox khi nạp; manifest luôn lưu tọa độ ảnh gốc.

### Wrapper và estimator
- Ở chế độ predict: nhận batch `(N, 3, 640, 640)` float32 [0, 1], trả list dict `{"boxes", "labels", "scores"}` theo quy ước `tech-stack.md` mục 2.1.
- Ở chế độ loss: nhận ảnh và target, trả loss vô hướng khả vi theo ảnh đầu vào.
- **Tính gradient không được làm thay đổi model**: weights và running stats của BatchNorm giữ nguyên sau khi gọi `loss_gradient`. Model luôn ở chế độ eval khi tính loss.
- Prediction của wrapper phải khớp với predict gốc của Ultralytics trên cùng ảnh đã letterbox.

### Đăng ký model
- `advertest model register --weights <file> --name <name>` tính hash, tạo `ModelCard`, chạy bài kiểm tra gradient trên fixture và đặt `supports_gradients` theo kết quả.
- Bài kiểm tra gradient pass khi: gradient hữu hạn, không toàn 0; một bước theo dấu gradient với eps nhỏ làm loss tăng; model không bị thay đổi sau khi tính gradient.
- Đăng ký lại cùng weights trả về cùng `id`.

### Dataset và slice
- `advertest dataset import-kitti --root <dir> --split training` tạo manifest, lưu vào kho local, in ra `dataset_version_sha256`. Chạy lại trên cùng dữ liệu cho cùng hash.
- `advertest slice create --dataset <sha> --size 300 --seed 42` tạo slice. Cùng tham số cho cùng `image_ids_sha256`.
- `advertest mapping create --dataset <sha> --model <id> --preset kitti-coco` tạo class mapping.

### Đánh giá
- `advertest eval --model <id> --slice <id> --mapping <id> [--device] [--batch-size] --out <file>` xuất `CleanEvalResult`.
- Tham số inference mặc định khi tính mAP: `conf = 0.001`, `iou = 0.7`, `max_det = 300`.
- `operating_conf = 0.25` được ghi vào kết quả để Phase 2 dùng khi tính tỷ lệ tấn công thành công và chọn failure case.
- Prediction thuộc class model không có trong mapping bị loại trước khi tính metric.
- Prediction có IoA (diện tích giao / diện tích prediction) ≥ 0.5 với một ignore region bị loại trước khi tính metric.
- Metric tính bằng `torchmetrics` `MeanAveragePrecision` (`box_format="xyxy"`, `iou_type="bbox"`, `class_metrics=True`).

### Cache
- Khóa cache = sha256 của: `weights_sha256`, `image_ids_sha256`, `dataset_version_sha256`, cấu hình letterbox, `inference_params`, phiên bản `torch` và `ultralytics`.
- Cache lưu prediction thô (trước khi lọc class và ignore region), để đổi mapping không phải chạy lại model.
- Chạy lại cùng khóa: không gọi model, `cache.hit = true`.

### Kho lưu trữ local
- Interface `ArtifactStore` với hai thao tác chính `put(key, bytes)` và `get(key)`. Phase này chỉ cài `LocalStore` (thư mục `data/store/`). Phase 3 thêm `MinioStore` cùng interface.
- Bố cục theo nội dung: `datasets/<sha>/manifest.json`, `slices/<sha>.json`, `mappings/<sha>.json`, `models/<weights_sha>/card.json`, `cache/predictions/<key>.json`.

### Trực quan hóa
- `advertest viz --slice <id> --mapping <id> --model <id> --n 8 --out <dir>` xuất ảnh PNG vẽ ground truth, prediction và ignore region, để kiểm tra bằng mắt rằng box khớp sau letterbox.

## Decisions

- **Dùng `PyTorchYolo` của ART với wrapper tự viết cho Ultralytics.** *Lý do:* giữ đúng giao diện estimator mà các attack của ART dùng. Nếu `PyTorchYolo` của phiên bản ART đã pin không tương thích, viết estimator riêng kế thừa các mixin object detector của ART. Nếu sau khoảng 2 ngày vẫn không có gradient đúng, kích hoạt phương án dự phòng Faster R-CNN (`tech-stack.md` mục 2) và cập nhật spec.
- **Model mặc định cho phát triển là `yolov8n`**, bản lớn hơn chọn sau khi có baseline. *Lý do:* nhẹ, vừa VRAM laptop, cùng weights với fixture.
- **Manifest lưu tọa độ ảnh gốc, letterbox áp dụng khi nạp.** *Lý do:* dataset không phụ thuộc vào kích thước đầu vào của model nào.
- **Ignore region cho `DontCare` và các class không map được.** *Lý do:* model COCO sẽ phát hiện người trên xe đạp (Cyclist) hay tàu điện; nếu không bỏ qua, chúng bị tính là false positive và làm sai lệch mAP. Cách xử lý gần với cách đánh giá chính thức của KITTI.
- **Giữ ảnh vuông 640×640 dù KITTI có tỉ lệ rất rộng (khoảng 1242×375).** *Lý do:* thống nhất quy ước trong `tech-stack.md` và kích thước đầu vào cố định của estimator ART. Hệ quả: object bị thu nhỏ, baseline có thể thấp. Nếu mAP@0.5 sạch dưới 0.4, ghi nhận và đưa quyết định (fine-tune, đổi kích thước đầu vào) vào backlog.
- **ID được sinh bằng uuid5 từ hash nội dung.** *Lý do:* cùng dữ liệu luôn cho cùng ID, khi Phase 3 đưa vào Postgres không phải ánh xạ lại.
- **Cache lưu prediction thô.** *Lý do:* đổi mapping hoặc ignore rule không tốn GPU.
- **Phase này chỉ dùng kho local qua interface `ArtifactStore`.** *Lý do:* ML core chạy được độc lập với backend; Phase 3 chỉ thêm một cài đặt mới.

## Context

- `mission.md` nguyên tắc 3 và 4: mọi đầu ra định danh bằng hash và tái lập được.
- `tech-stack.md` mục 2 (ML core, quy ước dữ liệu, wrapper, metric), mục 8 (thư mục `ml_core/`), mục 9 (luật cho agent).
- Phase 0: dùng `canonical_json`, `sha256_of` từ `advertest_contracts`; fixture YOLOv8n và 5 ảnh.
- KITTI yêu cầu đăng ký để tải. Dữ liệu gốc đặt tại `data/raw/kitti/`, không commit vào repo.
- Máy phát triển là laptop GPU VRAM thấp: batch size là tham số, không đặt cứng.

## Open Questions

- [ ] Baseline mAP@0.5 sạch trên slice KITTI là bao nhiêu, và có cần fine-tune hay đổi kích thước đầu vào không (trả lời sau manual check).
- [ ] Chốt YOLOv8 hay YOLOv11 cho model chính (sau khi wrapper chạy được với bản nano).
