# Design: AdverTest

> File constitution về giao diện. Mọi trang, component, report PDF đều theo file này. Agent frontend không tự chọn màu, font, khoảng cách hay câu chữ ngoài những gì ghi ở đây; cần thêm thì đề xuất cập nhật file này trước.
>
> Ngày 2026-10-10, file này được viết lại để mô tả đúng giao diện đang chạy. Nguồn sự thật của giá trị là `frontend/src/index.css` (token, lớp component) và `frontend/src/components/status/status-config.ts` (trạng thái). Sửa giá trị ở đó thì phải sửa file này cùng commit.

## 1. Định hướng

- **Chủ đề:** kiểm định độ bền của model nhận diện camera cho robot và xe tự hành.
- **Phong cách "phòng thử nghiệm kỹ thuật".** Nền trắng khói, chữ than chì, xanh dương kỹ thuật cho hành động chính. Vàng an toàn và cam cảnh báo lấy cảm hứng từ vạch kẻ đường thử và dấu mốc crash test. Motif computer vision: khung bounding box bốn góc, lưới lục giác mờ.
- **Đầu trang có họa tiết:** trang danh sách và trang tổng quan dùng `PageHero` (gradient hồng/tím nhẹ, lưới lục giác). Trang chi tiết và form dùng `PageHeader` gọn.
- **Nhất quán ngữ nghĩa màu:** xanh dương (`--detect`) luôn là "model nhận đúng / đang chạy", đỏ (`--fail`) luôn là "thất bại / mất object", hổ phách (`--threshold`) luôn là "ngưỡng / cảnh báo", xanh lá (`--approved`) luôn là "đạt / đã chấp nhận". Áp dụng ở mọi nơi: landing, ứng dụng, biểu đồ.
- **Sáng là mặc định; tối là tùy chọn** (nút chuyển trong `AppShell`, lưu ở `localStorage` `advertest-theme`). Ngữ nghĩa màu giữ nguyên ở hai chế độ.

## 2. Bố cục theo loại trang

| Loại | Trang | Đặc điểm |
|---|---|---|
| **Công khai** | Landing `/`, `/login`, `/request-access`, `/pending`, `/verify/:id` | `PublicLayout` / `AuthShowcase`; một cột nội dung, câu chữ giải thích số liệu |
| **Ứng dụng** | `/home`, danh sách, wizard, chi tiết experiment, hàng đợi review, protocol, admin | `AppShell` (thanh bên, command palette), `PageHero` hoặc `PageHeader`, panel và bảng; số căn phải |
| **Xem ảnh** | Trình xem failure case, `/reviews/:id/cases/:caseId`, thử nhanh | Ảnh và overlay là chính; nền `--viewer-canvas` quanh ảnh; chú thích lớp luôn hiện |

Chỉ học **nguyên tắc tổ chức** của sản phẩm khác. Không dùng màu thương hiệu, logo hay hình minh họa của hãng khác.

## 3. Màu

### Token (`frontend/src/index.css`)

| Token | Sáng | Tối | Dùng cho |
|---|---|---|---|
| `--ink` | `#1e293b` | `#e2e8f0` | Chữ chính |
| `--ink-muted` | `#475569` | `#94a3b8` | Chữ phụ |
| `--app-bg` | `#f4f5f7` | `#0f172a` | Nền trang |
| `--surface-solid` | `#ffffff` | `#1e293b` | Panel, bảng, hộp thoại |
| `--surface-raised` | `#eef1f5` | trắng 6% | Đầu bảng, hàng khi rê chuột, nền phụ |
| `--line` | `#e4e7ec` | `#94a3b8` 18% | Viền, đường kẻ |
| `--input` | `#8492a6` | `#64748b` | Viền ô nhập (≥ 3:1, WCAG 1.4.11) |
| `--detect` | `#0284c7` | `#38bdf8` | Nhận đúng, đang chạy, focus ring |
| `--fail` | `#dc2626` | `#f87171` | Thất bại, object bị mất, mức sụt, failure case; cũng là `--destructive` |
| `--threshold` | `#b45309` | `#fbbf24` | Đường ngưỡng, cảnh báo, "sát ngưỡng" (chữ cảnh báo trên nền sáng) |
| `--approved` | `#15803d` | `#4ade80` | Chỉ cho: đạt, đã chấp nhận, xác minh khớp |
| `--cta` | `#2563eb` | `#3b82f6` | Nút hành động chính, link, `ring` |
| `--navy` | `#1e293b` | `#e2e8f0` | `--primary`: nút mặc định, tab đang chọn |
| `--safety` | `#f59e0b` | — | Chỉ làm nền (chữ than chì) hoặc trang trí (vạch hazard, dấu crash test) |
| `--warning` / `--warning-text` | `#ea580c` / `#c2410c` | — / `#fb923c` | Cảnh báo mạnh (băng cảnh báo trên đầu trang) |
| `--pink`, `--violet` (+ `-soft`) | `#ec4899`, `#7c3aed` | nền mờ 14–16% | Chỉ trang trí: hero, ô biểu tượng (`tile`), avatar. Không mang nghĩa trạng thái |
| `--viewer-canvas` | `#475569` | `#475569` | Nền quanh ảnh (giống nhau ở hai chế độ để không ảnh hưởng cảm nhận màu ảnh) |

Không dùng `--pink`/`--violet` cho dữ liệu, trạng thái hay overlay.

### Màu trạng thái

Trạng thái hiển thị bằng `StatusBadge`: viên bo tròn, nền là màu của tông ở 12–14%, chữ và icon cùng màu. Có 6 tông:

| Tông | Lớp | Dùng cho |
|---|---|---|
| `neutral` | nền `--surface-raised`, chữ `--ink` 80% | Chờ, nháp |
| `info` | `--detect` | Đang chạy, đã gửi, đang duyệt, đang kiểm tra |
| `success` | `--approved` | Hoàn thành, đã duyệt, sẵn sàng, đang dùng |
| `warning` | `--threshold` | Dừng do giới hạn, yêu cầu sửa, chờ duyệt, điểm gãy |
| `danger` | `--fail` | Thất bại, từ chối, kiểm tra không đạt |
| `muted` | nền `--muted`, chữ `--ink-muted` | Bỏ qua, đã hủy, đã thay thế |

Bảng đầy đủ trạng thái → nhãn, icon (lucide) và tông nằm trong `status-config.ts`; trạng thái mới phải thêm vào đó. Trạng thái luôn hiển thị **màu + icon + chữ**.

Trạng thái catalog và model (Phase R3):

| Trạng thái | Tông | Icon | Nhãn |
|---|---|---|---|
| spec `draft` | `neutral` | `file-pen` | Nháp |
| spec/model `checking` | `info` | `loader-circle` | Đang kiểm tra |
| spec/model `check_failed` | `danger` | `circle-x` | Kiểm tra không đạt |
| spec `pending_approval` | `warning` | `hourglass` | Chờ duyệt |
| spec `active` | `success` | `badge-check` | Đang dùng |
| spec `retired` | `muted` | `archive` | Đã thay thế |
| model `ready` | `success` | `circle-check` | Sẵn sàng |

**Mode:** Khám phá dùng tông `neutral` với icon `flask-conical`; Chính thức dùng tông `info` với icon `shield-check`. Mode không dùng `success`.

### Lớp overlay trên ảnh

Màu cố định, không theo theme (`frontend/src/components/case-viewer/boxes.ts`, `BOX_COLORS`):

| Lớp | Màu | Kiểu nét |
|---|---|---|
| Ground truth | `#22c55e` | đứt 8-4, dày 2 px |
| Dự đoán ảnh sạch | `#3b82f6` | liền, dày 2 px |
| Dự đoán sau tấn công (giữ được) | `#f97316` | liền, dày 2 px |
| Object bị mất | `#ef4444` | liền, dày 3 px, nhãn có ký hiệu × |
| Phát hiện sai mới (thử nhanh) | `#f97316` | đứt 3-3, dày 2 px |
| Vùng bỏ qua | `#a3a3a3` | đứt 4-3 |

- Nhãn box có nền đen chữ trắng.
- Chú thích lớp đặt cạnh ảnh, dạng nút bật/tắt có ô màu.
- Màu luôn đi kèm kiểu nét hoặc ký hiệu, để người mù màu vẫn phân biệt được.

Phase R3 bổ sung các phần mà code hiện chưa có:
- nét đứt của ground truth;
- ký hiệu × của object bị mất;
- lớp phát hiện sai mới.

### Biểu đồ

- Đường dữ liệu chính: `--foreground`. Lưới và trục: `--muted-foreground`, độ mờ 25%. Phần kết quả một phần và khoảng tin cậy: `--destructive` nét đứt.
- Đường ngưỡng: `--threshold`, nét đứt. Điểm gãy: chấm tròn `--fail` kèm nhãn.
- Nhiều attack trên cùng biểu đồ: không dùng; thay bằng lưới biểu đồ nhỏ hoặc biểu đồ xếp hạng.

### Thang màu ma trận độ bền (Phase R3)

| Mức sụt tương đối lớn nhất của ô | Nền ô |
|---|---|
| < 0.1 | `--surface-solid` |
| 0.1–0.3 | `--fail` 20% |
| 0.3–0.5 | `--fail` 50% |
| ≥ 0.5 | `--fail` 85% (chữ trắng) |

- Ô ≥ `WEAKNESS_DROP` (0.3) thêm viền 2 px `--fail`.
- Ô chưa chạy có nền gạch chéo `--line` và chữ "Chưa chạy".
- Số phần trăm luôn hiện trong ô, và luôn có chú thích thang màu cạnh ma trận.

## 4. Chữ

- **Font:** Inter Variable (tự host qua `@fontsource-variable/inter`, không gọi Google Fonts). Dùng một font cho cả tiêu đề và nội dung.
- **Mono** (chỉ cho hash, fingerprint, mã report, mã lệnh): `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`.
- **Số liệu:** `font-variant-numeric: tabular-nums` (mặc định cho mọi `td`); căn phải trong bảng.
- Tiêu đề `h1`–`h3`: `letter-spacing` âm (−0.025em đến −0.035em), `text-wrap: balance`. Đoạn văn: `text-wrap: pretty`.

| Cấp | Cỡ / dòng | Trọng lượng | Dùng cho |
|---|---|---|---|
| H1 hero | `clamp(1.85rem, 2.6vw, 2.5rem)` / 1.1 | 700 | `PageHero` |
| H1 | `clamp(1.6rem, 2.2vw, 2rem)` / 1.15 | 700 | `PageHeader` |
| H2 | 20/28 | 600 | Tiêu đề section |
| H3 | 16/24 | 600 | Tiêu đề panel |
| Body | 14/22 (ứng dụng), 15/24 (mô tả dưới tiêu đề) | 400 | Văn bản |
| Đầu bảng | 12, 600 | 600 | `thead th`, màu `--ink-muted` |
| Small | 12–13 | 500–600 | Chú thích, nhãn, eyebrow của `PageHeader` |

Độ dài dòng văn bản tối đa khoảng 62–72 ký tự (`max-w-[62ch]`).

## 5. Khoảng cách, bo góc, đổ bóng, chuyển động

- **Khoảng cách:** bội số của 4 px (thang Tailwind). Trong ứng dụng, chủ yếu 8 / 12 / 16 / 20 / 24.
- **Bo góc:**
  - 4–6 px: badge nhỏ, ô nhập (`--radius-sm`, `--radius-md`);
  - 10 px: nút, mục điều hướng, `seg`, `tile` (`--radius` = 0.625rem);
  - 12 px: panel và vùng chứa bảng (`.panel`);
  - viên (`rounded-full`): badge trạng thái, chip, eyebrow.

  Ảnh trong trình xem ảnh không bo góc.
- **Đổ bóng:**
  - Panel: viền 1 px `--line` cộng bóng rất nhẹ (`--shadow-soft`).
  - Thẻ bấm được: nhấc lên 2 px khi rê chuột (`.lift`).
  - Lớp nổi (hộp thoại, menu): bóng rõ hơn.
- **Trang trí nền:**
  - `app-backdrop`: lưới lục giác cộng hai vệt hồng/xanh rất mờ;
  - `grain`: lớp hạt;
  - `hero`: gradient đầu trang.

  Chỉ dùng các lớp đã có trong `index.css`; không thêm gradient hay họa tiết mới.
- **Chuyển động:** 150–280 ms ease-out cho thay đổi do người dùng gây ra (mở, đóng, rê chuột, đổi tab). Hiệu ứng trang trí (chấm trạng thái nhấp nháy, đếm số, họa tiết trôi) chỉ chạy khi `prefers-reduced-motion: no-preference`. Mọi chuyển động tắt khi `reduce`.

## 6. Mẫu giao diện chính

- **Tab:** thanh tab dạng viên (`.seg`); tab đang chọn nền `--navy`.
- **Dải kết luận** (đầu trang chi tiết experiment): câu trạng thái tổng hợp; tình trạng tuân thủ protocol; ba con số: mAP sạch, mức sụt lớn nhất, điểm gãy nhỏ nhất.
- **Bảng:**
  - đầu bảng nền `--surface-raised`, chữ 12 px;
  - hàng đổi nền khi rê chuột; số căn phải;
  - hash rút gọn ở giữa, kèm nút copy;
  - điện thoại: chuyển sang thẻ, trừ bảng so sánh số liệu (cuộn ngang, cột đầu cố định).
- **Trình xem case:**
  - nền `--viewer-canvas`;
  - chú thích lớp bật/tắt cạnh ảnh;
  - ảnh nhiễu khuếch đại xem dạng ảnh thứ ba;
  - vuốt ngang trên điện thoại để chuyển case.
- **Không gian review:** hai cột. Cột trái cố định chứa danh sách kiểm tra, tiến độ case theo attack ("PGD 3/5") và nút quyết định; cột phải là nội dung.
- **Trạng thái trống** (`EmptyState`): nói điều gì đang thiếu, kèm nút hành động tiếp theo.
- **Hộp xác nhận** (`ConfirmDialog`) cho hành động không đảo ngược, kèm tóm tắt hệ quả.

## 7. Câu chữ

- Viết theo góc nhìn người dùng, câu chủ động, động từ rõ. Không quảng cáo, không thán từ, không emoji trong câu chữ chức năng.
- Nút nói đúng điều sẽ xảy ra; tên hành động giữ nguyên suốt luồng ("Gửi duyệt" → thông báo "Đã gửi duyệt").
- Lỗi nói rõ chuyện gì xảy ra và cách sửa, không xin lỗi. Ví dụ: "Không tạo được: thiếu PGD eps 4 theo protocol KITTI v1. Thêm level này ở bước 3."
- Viết hoa kiểu câu (chỉ viết hoa chữ đầu và tên riêng). Ngoại lệ: eyebrow và kicker (chữ nhỏ viết hoa, giãn chữ) chỉ dùng ở `PageHero` và trang công khai.
- Chuỗi giao diện mới đặt trong `frontend/src/copy/`. Việc gom chuỗi cũ vào `frontend/src/copy/vi.ts` thuộc Phase R3b.

## 8. Những thứ không được dùng

Danh sách này dùng khi review phần mới thêm:
- Màu hex, token, font hay họa tiết nền mới ngoài `index.css`.
- Dùng `--pink`/`--violet`/`--safety` để biểu thị trạng thái hoặc dữ liệu; dùng `--approved` cho thứ chưa được chấp nhận.
- Trạng thái chỉ bằng màu (thiếu icon hoặc chữ).
- Nhấn một từ trong tiêu đề bằng màu, nghiêng hoặc đậm khác.
- Hiệu ứng trượt lên ở mọi section khi cuộn; chuyển động không tắt khi `prefers-reduced-motion: reduce`.
- Đánh số 01 / 02 / 03 cho nội dung không phải trình tự.
- Font mono cho nhãn trang trí.
