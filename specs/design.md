# Design: AdverTest

> File constitution về giao diện. Mọi trang, component, report PDF đều theo file này. Agent frontend không tự chọn màu, font, khoảng cách hay câu chữ ngoài những gì ghi ở đây; cần thêm thì đề xuất cập nhật file này trước.

## 1. Định hướng

- **Chủ đề:** kiểm định độ bền của model nhận diện camera cho robot và xe tự hành.
- **Ý tưởng chủ đạo:** chất liệu lấy từ thế giới computer vision và kiểm định: khung bounding box, lớp overlay annotation, đường ngưỡng, dấu xác minh.
- **Một điểm nhấn duy nhất:** demo "điểm gãy" tương tác trên landing page. Mọi thứ khác tiết chế.
- **Nhất quán ngữ nghĩa màu:** cyan luôn là "model nhận đúng", magenta luôn là "model thất bại", hổ phách luôn là "ngưỡng / cảnh báo", ở mọi nơi: landing, ứng dụng, biểu đồ, report PDF.

## 2. Ba vùng phong cách

| Vùng | Trang | Hướng | Học từ | Đặc điểm |
|---|---|---|---|---|
| **B – Hồ sơ an toàn** | Landing `/`, `/verify/:id`, `/login`, `/request-access`, `/pending`, report PDF | Điềm tĩnh, nhiều khoảng trắng, đọc như tài liệu đáng tin | Trang an toàn của Waymo, tài liệu Stripe | Một cột chính căn trái, câu chữ giải thích số liệu |
| **C – Quy trình dev tool** | Khung ứng dụng, `/home`, danh sách, wizard, chi tiết experiment, hàng đợi review, protocol, admin | Gọn, trạng thái rõ, bảng là chính, phím tắt | Linear, GitHub PR review, Weights & Biases | Mật độ vừa, bảng số căn phải |
| **A – Công cụ kỹ thuật** | Trình xem failure case, `/reviews/:id/cases/:caseId` | Ưu tiên ảnh và overlay, panel, tối là mặc định | Foxglove, Rerun | Nền trung tính quanh ảnh, chú thích lớp cố định |

Chỉ học **nguyên tắc tổ chức**. Không dùng màu thương hiệu, logo, hình minh họa hay bố cục đặc trưng của các hãng trên.

## 3. Màu

### Bảng gốc

| Token | Sáng | Tối | Dùng cho |
|---|---|---|---|
| `--ink` | `#1E2630` | `#E6EAEE` | Chữ chính |
| `--ink-muted` | `#5B6673` | `#9AA6B2` | Chữ phụ |
| `--bg` | `#EEF1F4` | `#151B22` | Nền trang |
| `--surface` | `#FFFFFF` | `#1C242D` | Panel, bảng, hộp thoại |
| `--border` | `#D5DBE1` | `#2C3640` | Viền, đường kẻ |
| `--detect` (cyan) | `#00A3B4` | `#2BC4D4` | Phát hiện đúng; màu nhấn chính; nút chính |
| `--fail` (magenta) | `#D6336C` | `#F0568A` | Object bị mất, phát hiện sai, mức sụt, failure case |
| `--threshold` (hổ phách) | `#E8A317` | `#F2B53A` | Đường ngưỡng, cảnh báo, "sát ngưỡng" |
| `--approved` (xanh) | `#2F8F5B` | `#4CB67C` | Chỉ cho: đã chấp nhận, xác minh khớp, tiêu chí đạt |
| `--viewer-canvas` | `#4A4F55` | `#4A4F55` | Nền quanh ảnh trong vùng A (giống nhau ở hai chế độ để không ảnh hưởng cảm nhận màu ảnh) |

### Màu trạng thái

| Trạng thái | Màu | Icon (lucide) |
|---|---|---|
| `queued` | `--ink-muted` | `clock` |
| `running` | `--detect` | `loader` (xoay, tắt khi giảm chuyển động) |
| `completed` | `--ink` | `check` |
| `failed` | `--fail` | `x-circle` |
| `skipped` | `--ink-muted` | `skip-forward` |
| `stopped_limit` | `--threshold` | `timer-off` |
| `cancelled` | `--ink-muted` | `ban` |
| `approved` | `--approved` | `badge-check` |
| `changes_requested` | `--threshold` | `pencil` |
| `rejected` | `--fail` | `x-octagon` |

Trạng thái luôn hiển thị **màu + icon + chữ**.

### Lớp overlay trên ảnh

| Lớp | Màu | Kiểu nét | Phím tắt |
|---|---|---|---|
| Ground truth | trắng 80% | đứt 4-3, dày 1.5 px | `G` |
| Dự đoán đúng (sạch và sau tấn công) | `--detect` | liền, dày 2 px | `C` / `A` |
| Object bị mất | `--fail` | liền, dày 2.5 px, nhãn có ký hiệu × | luôn hiện |
| Phát hiện sai mới | `--fail` | đứt 6-3, dày 2 px | luôn hiện |
| Ignore region | xám 50% | gạch chéo | `I` |

Mọi box có thêm viền ngoài 1 px màu `rgba(0,0,0,0.6)` để nổi trên mọi nền ảnh. Màu luôn đi kèm kiểu nét, để người mù màu vẫn phân biệt được.

### Biểu đồ

- Đường mức sụt: `--fail`. Đường ngưỡng: `--threshold`, nét đứt. Điểm gãy: chấm tròn `--fail` kèm nhãn. Đường mAP sạch: `--ink-muted`, nét đứt.
- Nhiều attack trên cùng biểu đồ: không dùng; thay bằng lưới biểu đồ nhỏ (mục 6).

## 4. Chữ

- **Font:** Be Vietnam Pro (tự host qua `@fontsource/be-vietnam-pro`, không gọi Google Fonts). Lý do: thiết kế cho tiếng Việt, dấu chuẩn, có số dạng bảng.
- **Mono** (chỉ cho hash, fingerprint, mã report, mã lệnh): `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`.
- **Số liệu:** luôn `font-variant-numeric: tabular-nums`; căn phải trong bảng.

| Cấp | Cỡ / dòng | Trọng lượng | Dùng cho |
|---|---|---|---|
| Hero | 44/52 (điện thoại 32/40) | 600 | Chỉ tiêu đề landing |
| H1 | 28/36 | 600 | Tiêu đề trang |
| H2 | 20/28 | 600 | Tiêu đề section |
| H3 | 16/24 | 600 | Tiêu đề panel |
| Body | 16/26 (landing), 14/22 (ứng dụng) | 400 | Văn bản |
| Small | 12/18 | 400–500 | Chú thích, nhãn bảng |

Độ dài dòng văn bản tối đa 72 ký tự.

## 5. Khoảng cách, bo góc, đổ bóng, chuyển động

- **Khoảng cách:** bội số của 4 px. Trong ứng dụng: 8 / 12 / 16 / 24. Landing: section cách nhau 96 px (điện thoại 64 px).
- **Bo góc theo cấp bậc:** 4 px (ô nhập, badge, nút), 8 px (panel, bảng), 12 px (hộp thoại, bottom sheet). Ảnh trong vùng A không bo góc.
- **Đổ bóng:** chỉ cho lớp nổi (hộp thoại, menu, bottom sheet). Panel dùng viền, không dùng bóng.
- **Chuyển động:** 150 ms ease-out cho thay đổi do người dùng gây ra (mở, đóng, lưu). Không có hiệu ứng xuất hiện khi cuộn. Ngoại lệ duy nhất: demo trên landing tự quét một lần khi tải trang. Mọi chuyển động tắt khi `prefers-reduced-motion: reduce`.

## 6. Mẫu giao diện chính

- **Dải kết luận** (đầu trang chi tiết experiment): câu trạng thái tổng hợp; tình trạng tuân thủ protocol; ba con số: mAP sạch, mức sụt lớn nhất, điểm gãy nhỏ nhất.
- **Lưới biểu đồ nhỏ:** mỗi attack một ô, cùng trục hoành chuẩn hóa (% dải của spec), cùng thang trục tung, cùng đường ngưỡng.
- **Bảng:** tiêu đề cột cố định khi cuộn; số căn phải; hash rút gọn giữa kèm nút copy; điện thoại chuyển sang thẻ (bảng so sánh số liệu thì cuộn ngang, cột đầu cố định).
- **Trình xem case (vùng A):** nền `--viewer-canvas`; chú thích lớp cố định góc trên trái kèm phím tắt; dải ảnh thu nhỏ các case ở cạnh dưới; ảnh nhiễu khuếch đại xem dạng chia đôi; mặc định chế độ tối.
- **Không gian review:** hai cột; cột trái cố định chứa danh sách kiểm tra, tiến độ case theo attack ("PGD 3/5") và nút quyết định; cột phải là nội dung.
- **Trạng thái trống:** nói điều gì đang thiếu và nút hành động tiếp theo.

## 7. Câu chữ

- Viết theo góc nhìn người dùng, câu chủ động, động từ rõ. Không quảng cáo, không thán từ.
- Nút nói đúng điều sẽ xảy ra; tên hành động giữ nguyên suốt luồng ("Gửi duyệt" → thông báo "Đã gửi duyệt").
- Lỗi nói rõ chuyện gì xảy ra và cách sửa, không xin lỗi. Ví dụ: "Không tạo được: thiếu PGD eps 4 theo protocol KITTI v1. Thêm level này ở bước 4."
- Viết hoa kiểu câu (chỉ viết hoa chữ đầu và tên riêng).
- Toàn bộ chuỗi giao diện nằm trong `frontend/src/copy/vi.ts`.

## 8. Những thứ không được dùng

Danh sách này dùng khi review:
- Nhãn nhỏ viết hoa toàn bộ phía trên tiêu đề.
- Nhấn một từ trong tiêu đề bằng màu, nghiêng hoặc đậm khác.
- Lưới thẻ giống hệt nhau cùng bóng mờ; gradient trang trí.
- Hiệu ứng trượt lên ở mọi section khi cuộn.
- Mũi tên "→" gắn sau chữ của nút hay link.
- Đánh số 01 / 02 / 03 cho nội dung không phải trình tự.
- Font mono cho nhãn trang trí.
- Chuỗi siêu dữ liệu nối bằng dấu chấm giữa ("A · B · C").
