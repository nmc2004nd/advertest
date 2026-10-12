# Đăng ký model qua web

Tài liệu này hướng dẫn đưa model detection của bạn lên AdverTest để chạy experiment: chọn định dạng, chuẩn bị file, điền form, đọc kết quả kiểm tra và xử lý lỗi thường gặp.

## 1. Ai đăng ký được

| Role | Quyền |
|---|---|
| Engineer | Đăng ký model của mình; thêm version vào model **do mình tạo**; kiểm tra lại model của mình |
| Admin | Như engineer, không giới hạn theo người tạo (để hỗ trợ) |
| Reviewer | Chỉ xem model |

Trang đăng ký: mục **Model** trên thanh điều hướng (`/models`). Mọi role xem được danh sách model đã đăng ký khi tạo experiment.

## 2. Chọn định dạng

Web chỉ nhận **`.safetensors`** và **`.onnx`**, tối đa **500 MB**. File `.pt`, `.pth`, `.pkl`, `.zip` bị từ chối (xem mục 7).

| Framework | File | Kiến trúc hỗ trợ | Gradient |
|---|---|---|---|
| `ultralytics` | `.safetensors` | YOLOv8 (n, s, m, l, x), YOLOv9 (t, s, m, c, e), YOLO11 và YOLO12 (n, s, m, l, x), bản detect | Có, nếu đạt bài kiểm tra gradient |
| `torchvision` | `.safetensors` | `fasterrcnn_resnet50_fpn_v2`, `retinanet_resnet50_fpn_v2`, `fcos_resnet50_fpn` | Có, nếu đạt bài kiểm tra gradient |
| `onnx` | `.onnx` | Bất kỳ, miễn đầu ra theo layout ở mục 3.3 | Không |

**Gradient quyết định attack nào chạy được.** Attack biến đổi ảnh (mờ, nhiễu, độ sáng, thời tiết…) chạy trên mọi model. Attack cần gradient (FGSM, PGD, patch train trên model) chỉ chạy trên model có gradient.

Có YOLO Ultralytics: dùng `ultralytics`. Chỉ cần đánh giá với attack biến đổi ảnh, hoặc model có kiến trúc riêng: dùng `onnx`.

## 3. Chuẩn bị file

### 3.1. YOLO Ultralytics (`.pt` → `.safetensors`)

Chạy trên máy bạn, trong thư mục repo AdverTest:

```bash
uv sync --extra cpu
uv run --extra cpu advertest model export-safetensors yolo11n.pt
# models/yolo11n.safetensors — kiến trúc yolo11n, 80 class
```

| Tùy chọn | Dùng khi |
|---|---|
| `-o duong-dan.safetensors` | Đổi chỗ ghi file (mặc định cạnh file `.pt`) |
| `--architecture yolo11s` | Lệnh không nhận ra kiến trúc, ví dụ checkpoint tên `best.pt` sau khi train |

Lệnh đọc checkpoint bằng Ultralytics rồi ghi:

- trọng số (state dict, float32);
- metadata `framework=ultralytics`, `architecture`, `names` (tên class theo thứ tự index), `imgsz=640`, để form trên web tự điền.

Lệnh nạp file `.pt` (pickle), nên chỉ chạy với checkpoint bạn tin, ví dụ checkpoint của chính bạn hoặc bản phát hành chính thức của Ultralytics.

Model train lại với số class khác (ví dụ 3 class KITTI) vẫn dùng được: số class lấy theo `names` trong checkpoint. Model **sửa kiến trúc** (thêm lớp, đổi head) không khớp config chuẩn của Ultralytics, nên không đăng ký theo đường này được; dùng ONNX (mục 3.3) hoặc nhờ admin đăng ký qua CLI (mục 8).

### 3.2. torchvision (`.safetensors`)

```python
from safetensors.torch import save_file
save_file(
    {k: v.contiguous() for k, v in model.state_dict().items()},
    "fcos.safetensors",
    metadata={"architecture": "fcos_resnet50_fpn", "class_names": json.dumps(class_names)},
)
```

`class_names` theo đúng thứ tự index của lớp phân loại, gồm cả `__background__` nếu model có.

### 3.3. ONNX

Từ Ultralytics:

```python
from ultralytics import YOLO
YOLO("yolo11n.pt").export(format="onnx", imgsz=640)   # giữ nms=False, dynamic=False
```

Đầu ra phải theo một trong hai layout:

| Layout | Đầu ra |
|---|---|
| YOLO | Một tensor `(1, 4 + C, N)`, box xywh tâm (pixel) cộng C điểm class, chưa NMS. Ví dụ COCO: `(1, 84, 8400)` |
| Đã NMS | Ba tensor tên `boxes` (K, 4, xyxy pixel), `scores` (K), `labels` (K) |

Không dùng được: YOLOv5 (`(1, 25200, 85)`), RT-DETR và bản end-to-end như YOLOv10 hoặc export với `nms=True` (`(1, 300, 6)`). Đầu vào phải là `(N, 3, S, S)` với S bằng kích thước đầu vào khai báo trong form.

## 4. Điền form đăng ký

Chọn file trước: form đọc metadata ngay trên trình duyệt (không upload) và điền sẵn các ô.

| Ô | Ý nghĩa |
|---|---|
| File weights | `.safetensors` hoặc `.onnx`. Dòng "Đọc được từ file: …" cho biết form đã lấy gì từ metadata |
| Tên model | Mặc định theo tên file. Đăng ký file khác cùng tên thì thành version mới của model đó (chỉ khi bạn là người tạo) |
| Framework | Tự chọn theo file: `.onnx` → onnx; `.safetensors` có metadata Ultralytics → ultralytics; còn lại → torchvision |
| Kiến trúc | ultralytics, torchvision: chọn trong danh sách, quyết định mạng được dựng. onnx: chỉ là mô tả cho người xem, hệ thống không dùng |
| Kích thước đầu vào | Cạnh ảnh vuông sau letterbox. ultralytics cố định 640 |
| Danh sách class | Theo thứ tự index của model; số class phải khớp đầu ra. Có sẵn bộ COCO 80 (YOLO), COCO 91 (torchvision), hoặc tự nhập |

Bấm **Đăng ký**: file được tải thẳng lên kho lưu trữ (thanh tiến độ), rồi model chuyển sang trạng thái **Đang kiểm tra**.

## 5. Kiểm tra tự động

Worker công cụ kiểm tra từng model mới, dừng ở bước đầu tiên không đạt:

1. sha256 của file khớp file đã upload;
2. nạp model:
   - ultralytics: dựng mạng từ config `<kiến trúc>.yaml` có sẵn trong thư viện Ultralytics, rồi nạp trọng số, khớp tuyệt đối từng lớp;
   - torchvision: dựng kiến trúc torchvision, rồi nạp trọng số;
   - onnx: mở bằng onnxruntime, nhận layout đầu ra;
3. số class của model bằng số class khai báo;
4. chạy thử trên ảnh mẫu: box hữu hạn, label nằm trong danh sách class;
5. (ultralytics, torchvision) bài kiểm tra gradient.

| Kết quả | Ý nghĩa |
|---|---|
| **Sẵn sàng**, có gradient | Dùng được với mọi attack |
| **Sẵn sàng**, không có gradient | Dùng được với attack biến đổi ảnh. Với ultralytics và torchvision: bài kiểm tra gradient không đạt (lý do ở trang chi tiết), model vẫn dùng được |
| **Kiểm tra không đạt** | Không dùng được. Trang chi tiết model ghi bước nào hỏng |

Trên CPU, một model nano mất khoảng 10 đến 30 giây. Trang chi tiết model tự cập nhật.

Model **Kiểm tra không đạt** vì lỗi tạm thời (worker bị ngắt, hết bộ nhớ) có thể bấm **Kiểm tra lại** ở trang chi tiết. Lỗi do file thì phải sửa file rồi đăng ký lại.

## 6. Lỗi thường gặp

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ nhận file .onnx hoặc .safetensors | Chọn file `.pt` hoặc đuôi khác | Đổi sang safetensors (mục 3.1) hoặc ONNX (mục 3.3) |
| File không phải safetensors hợp lệ | File đổi đuôi, nội dung là pickle, zip hoặc hỏng | Tạo lại bằng `export-safetensors` hoặc `safetensors.torch.save_file` |
| Model … phải là file … | Đuôi file không khớp framework | Chọn lại framework |
| Đã có model cùng weights (trùng sha256) | File này đã được đăng ký (bởi bạn hoặc người khác) | Dùng model đã có trong danh sách |
| Tên model … đã thuộc người khác | Trùng tên model do người khác tạo | Đặt tên khác |
| Mất kết nối khi tải file lên | Trình duyệt không gọi được kho lưu trữ | Người vận hành kiểm tra `MINIO_PUBLIC_ENDPOINT` (xem `deploy/README.md`) |
| Kiểm tra không đạt: Weights không khớp … | Chọn sai kiến trúc hoặc sai số class | Kiểm tra kiến trúc (ví dụ yolo11n hay yolo11s) và danh sách class |
| Kiểm tra không đạt: Model có X class, model card khai báo Y | Số class trong form khác đầu ra của model | Sửa danh sách class |
| Kiểm tra không đạt: Input ONNX … khác … | Kích thước đầu vào khác lúc export | Chọn đúng kích thước, hoặc export lại |
| Kiểm tra không đạt: Đầu ra ONNX không theo layout | Model ONNX ngoài hai layout ở mục 3.3 | Export lại với `nms=False`, hoặc dùng ultralytics |

## 7. Vì sao web không nhận `.pt`

File `.pt` là pickle: ngoài dữ liệu, nó chứa lệnh gọi hàm, và `torch.load` thực thi các lệnh đó khi đọc file. Nhận `.pt` qua web nghĩa là bất kỳ ai đăng ký được model cũng chạy được mã tùy ý trên worker (đọc token, truy cập ảnh và kết quả của người khác). Chế độ an toàn `weights_only=True` không nạp được checkpoint Ultralytics, vì checkpoint lưu cả object model. Đây là nguyên tắc 10 trong `specs/mission.md`.

Cách hiện tại tách hai phần của model:

- **cấu trúc mạng** (là code): lấy từ thư viện Ultralytics hoặc torchvision đã cài trong hệ thống, không đến từ file upload;
- **trọng số** (chỉ là số): lấy từ file safetensors, định dạng chỉ gồm header JSON và mảng số, đọc không thực thi gì.

Kết quả bằng nạp `.pt` trực tiếp (đã so trên YOLOv8n, YOLOv9t, YOLO11n, YOLO12n), và model vẫn có gradient. Bước chuyển `.pt` → safetensors chạy trên máy người dùng, với file của chính họ.

## 8. Đăng ký `.pt` qua CLI (admin)

Model không đi được đường web (kiến trúc tự sửa) có thể được admin đăng ký từ file `.pt` Ultralytics sau khi review file, trên máy chủ:

```bash
# 1. Đăng ký vào LocalStore: hash weights, chạy bài kiểm tra gradient, ghi model card.
uv run --extra cpu advertest --store-dir <thư mục LocalStore> model register --weights model.pt --name ten-model
# 2. Đưa LocalStore lên hệ thống.
advertest-admin import-local --store <thư mục LocalStore> --as <email admin>
```

Chi tiết lệnh `import-local` xem [`van-hanh-worker.md`](van-hanh-worker.md) mục 3.
