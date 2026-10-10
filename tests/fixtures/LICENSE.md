# Nguồn và giấy phép của fixture

## Ảnh KITTI (`kitti/image_2/`)

5 ảnh thuộc tập training của KITTI Vision Benchmark Suite (2D object detection), lấy qua bản
phân phối lại của Ultralytics (`kitti.zip`, release `v0.0.0` của `ultralytics/assets`), giữ nguyên
tên ảnh gốc.

- Giấy phép: Creative Commons Attribution-NonCommercial-ShareAlike 3.0 (CC BY-NC-SA 3.0).
- Chỉ dùng cho mục đích phi thương mại (kiểm thử của dự án).
- Trích dẫn: A. Geiger, P. Lenz, R. Urtasun. "Are we ready for Autonomous Driving? The KITTI
  Vision Benchmark Suite". CVPR 2012.

Label (`kitti/label_2/`) sẽ lấy từ file label gốc của KITTI (`data_object_label_2.zip`), cùng
giấy phép trên.

## Weights YOLOv8n (`yolov8n.pt`)

Tải từ release `v8.3.0` của `ultralytics/assets`, giấy phép AGPL-3.0 của Ultralytics.

## Model Phase R2 (`yolov8n.onnx`, `fcos_resnet50_fpn_coco.safetensors`)

Sinh bằng `scripts/make_r2_fixtures.py`, tải từ release `fixtures-v2` của repo này.

- `yolov8n.onnx`: xuất từ `yolov8n.pt` ở trên, cùng giấy phép AGPL-3.0 của Ultralytics.
- `fcos_resnet50_fpn_coco.safetensors`: weights `FCOS_ResNet50_FPN_Weights.COCO_V1` của torchvision
  (BSD-3-Clause), đổi sang định dạng safetensors.
