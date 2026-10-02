# Requirements: Phase 11a — Landing page

## Scope

Xây landing page cho AdverTest tại `/`, theo vùng B trong `specs/design.md`. Phase này **chỉ làm landing page**; giao diện các trang khác của ứng dụng giữ nguyên và được làm lại ở Phase 11b. Kết quả gồm:

1. **Token và font dùng riêng cho landing**, khai báo theo `design.md` nhưng chỉ có hiệu lực trong landing.
2. **Module lớp overlay** `frontend/src/design/layers.ts` (dùng cho demo; Phase 11b sẽ dùng lại cho trình xem case).
3. **Demo "điểm gãy" tương tác** dựa trên số liệu thật.
4. **Trang landing** đủ 9 section, ô xác minh report, responsive, hỗ trợ chế độ sáng và tối theo hệ thống.

## Out of Scope

- Đổi giao diện bất kỳ trang nào ngoài `/`: đăng nhập, yêu cầu truy cập, chờ duyệt, `/verify/:id`, khung ứng dụng, wizard, chi tiết experiment, trình xem case, không gian review, report PDF. Tất cả chuyển sang **Phase 11b**.
- Nút chuyển chế độ sáng/tối thủ công (landing theo cài đặt hệ thống; nút chuyển chung làm ở Phase 11b).
- Viết lại câu chữ của ứng dụng.
- Tính năng mới, endpoint mới, thay đổi contract hay DB.
- Bản tiếng Anh.

## Data / Fields

Không có thay đổi contract.

**Dữ liệu demo** (`frontend/src/features/landing/demo-data.json`), do người duyệt xuất từ một experiment thật:

| Field | Ý nghĩa |
|---|---|
| `attack` | Tên attack, ví dụ `pgd_linf` |
| `unit` | Đơn vị hiển thị, ví dụ `/255` |
| `threshold` | Ngưỡng mức sụt tương đối, ví dụ 0.2 |
| `points` | Danh sách `{level, relative_drop}` từ kết quả quét lưới hoặc quỹ đạo tìm ngưỡng, sắp tăng dần theo `level` |
| `breaking_point` | Điểm gãy đã tìm được |
| `objects` | 4–6 object của cảnh minh họa, mỗi cái: `kind` (`car` / `truck` / `person`), box `[x1, y1, x2, y2]` trong khung 640×360, `lost_at` (level mà object biến mất; `null` nếu không mất trong dải) |
| `source` | `kind` (`experiment` / `smoke`), `model`, `dataset`, `slice_size`, `experiment_id`, `run_date` |

Ràng buộc: tại mọi điểm trong `points`, tỉ lệ object có `lost_at ≤ level` lệch không quá 0.2 so với `relative_drop` tại điểm đó.

Khi `source.kind = experiment`, `experiment_id` là UUID và `run_date` là thời gian UTC của experiment nguồn.

Khi `source.kind = smoke`, `experiment_id` và `run_date` là `null`; giao diện phải ghi rõ "Dữ liệu minh họa tạm thời". Smoke chỉ được dùng để phát triển Group 1–3 và phải được thay bằng dữ liệu PGD L∞ KITTI 300 trước Group 4.

## Behaviour

### Token và font (cô lập trong landing)
- Token màu, chữ, khoảng cách, bo góc theo `design.md` mục 3–5, khai báo dưới phạm vi phần tử gốc của landing (ví dụ lớp `.zone-landing`), cho cả chế độ sáng và tối qua `prefers-color-scheme`.
- **Không** sửa theme toàn cục của shadcn/ui hay Tailwind; không đổi font của các trang khác.
- Font Be Vietnam Pro tự host qua `@fontsource/be-vietnam-pro`, chỉ được tải khi vào landing (tách theo route).
- Ba dependency của phase được người duyệt pin và commit trong Group 0 trước khi giao code cho `frontend-landing`.
- Không có request tới domain ngoài origin của ứng dụng.

### Module lớp overlay
- `frontend/src/design/layers.ts` định nghĩa màu (theo token), kiểu nét, độ dày, viền ngoài và phím tắt của các lớp trong `design.md` mục 3. Demo landing chỉ lấy màu và kiểu nét từ module này.

### Các section, theo thứ tự
1. **Đầu trang:** tên sản phẩm; link "Xác minh report" (cuộn tới section 8) và "Đăng nhập".
2. **Hero:** tiêu đề, một đoạn mô tả, nút chính "Yêu cầu truy cập" (tới `/request-access`) và nút phụ "Đăng nhập". Người đã đăng nhập: nút chính đổi thành "Vào ứng dụng" (tới `/home`).
3. **Demo điểm gãy:**
   - cảnh đường phố vẽ bằng SVG (không dùng ảnh dataset thật), các box vẽ theo `objects`;
   - thanh trượt "Cường độ nhiễu" chạy trong dải của `points`;
   - kéo thanh trượt: lớp nhiễu trên cảnh dày dần; object có `lost_at ≤ level` chuyển sang kiểu "object bị mất" (magenta, nét liền dày, nhãn ×) rồi mờ dần; object còn lại giữ kiểu "dự đoán đúng" (cyan);
   - biểu đồ mức sụt theo level (nội suy tuyến tính giữa các điểm), đường ngưỡng nét đứt, điểm đang chọn chạy theo thanh trượt;
   - khi level ≥ `breaking_point`: hiện nhãn "Gãy tại ≈ {breaking_point}{unit}" và đánh dấu điểm gãy trên biểu đồ;
   - dòng nguồn số liệu từ `source`;
   - khi tải trang: thanh trượt tự quét một lần từ đầu dải tới `breaking_point` trong khoảng 2 giây rồi dừng; không tự quét khi `prefers-reduced-motion: reduce`; người dùng chạm vào thanh trượt thì dừng tự quét ngay;
   - thao tác bằng bàn phím (mũi tên, Home, End); có nhãn truy cập và giá trị hiện tại cho trình đọc màn hình.
4. **Cách một bài kiểm thử diễn ra:** 4 bước có thứ tự (reviewer chốt protocol → engineer chạy experiment → reviewer duyệt độc lập → report có mã xác minh), mỗi bước ghi vai trò thực hiện.
5. **Vì sao kết quả đáng tin:** tiêu chí chốt trước; người chạy không tự duyệt; kết quả không sửa được; chạy lại cho cùng kết quả; kèm một mẫu tĩnh minh họa ô xác minh (không gọi API).
6. **Ba vai trò:** engineer, reviewer, admin, mỗi vai trò 1–2 câu.
7. **Phạm vi hiện tại và lưu ý:** những gì đang hỗ trợ và chưa hỗ trợ; câu lưu ý "chỉ là môi trường kiểm thử" theo `mission.md` nguyên tắc 8.
8. **Xác minh report:** ô nhập mã report và nút "Xác minh" → `/verify/:id`; mã rỗng thì báo lỗi ngay dưới ô.
9. **Chân trang:** tên sản phẩm và link đăng nhập.

### Yêu cầu chung
- Bố cục một cột chính căn trái, độ dài dòng văn bản ≤ 72 ký tự, theo vùng B.
- Câu chữ của landing nằm trong `frontend/src/copy/vi.ts` (nhóm `landing`), viết theo `design.md` mục 7.
- Khi route `/` được mount, đặt `<title>`, `meta description`, `og:title`, `og:description`; khi rời route, khôi phục các giá trị trước đó để metadata của trang khác không bị thay đổi.
- Phase 11a không tạo `og:image`; ảnh Open Graph được hoãn tới giai đoạn triển khai.
- Không có ảnh bitmap; demo hoàn toàn bằng SVG và CSS.
- Responsive theo `tech-stack.md` mục 5.1; không có thanh cuộn ngang ở 375 px; thanh trượt dùng được bằng ngón tay.
- Độ tương phản chữ đạt WCAG AA ở cả hai chế độ; viền focus nhìn thấy được.

## Decisions

- **Tách landing khỏi phần làm lại giao diện ứng dụng.** *Lý do:* landing là phần mới, độc lập; làm riêng thì nhanh có kết quả để demo và không đụng tới các trang đang chạy ổn.
- **Token và font cô lập trong landing.** *Lý do:* không làm thay đổi giao diện các trang khác trước Phase 11b; khi Phase 11b áp dụng token toàn cục, landing chỉ cần bỏ phạm vi cô lập.
- **Demo dùng số liệu thật, cảnh vẽ bằng SVG.** *Lý do:* số liệu thật biến demo thành bằng chứng; SVG tránh vấn đề quyền riêng tư và giấy phép ảnh, và tải nhanh.
- **Làm `layers.ts` ngay từ phase này.** *Lý do:* ý nghĩa của cyan và magenta trên landing phải giống hệt trong trình xem case sau này; có một nguồn duy nhất từ đầu.
- **Landing theo chế độ sáng/tối của hệ thống.** *Lý do:* đủ cho trang công khai; nút chuyển thủ công thuộc về khung ứng dụng ở Phase 11b.
- **Nguồn demo là PGD L∞ trên slice KITTI 300 ảnh của Phase 7.** Group 0 xuất các điểm đo và định danh experiment thật vào `demo-data.json`.
- **Metadata được cô lập theo vòng đời route.** Landing đặt metadata khi mount và khôi phục khi unmount, giống nguyên tắc cô lập token và font.
- **Chưa tạo ảnh Open Graph.** Phase 11a chỉ cung cấp metadata dạng chữ; asset chia sẻ mạng xã hội được quyết định khi biết môi trường triển khai.
- **Cho phép dữ liệu smoke trong lúc phát triển.** Smoke phải tuân thủ cùng schema và ràng buộc đường cong/object, được ghi nhãn rõ, và không được dùng để nghiệm thu hoặc đóng phase.

## Context

- `specs/design.md`: vùng B, token, lớp overlay, câu chữ, danh sách không được dùng.
- `mission.md` nguyên tắc 8 (chỉ là kiểm thử), 9 (riêng tư); `tech-stack.md` mục 5, 5.1.
- Phase 4: route `/` hiện là trang giới thiệu tối giản; phase này thay thế nó. Phase 8: `/verify/:id`.

## Open Questions

- [x] Dùng PGD L∞ trên slice KITTI 300 ảnh của Phase 7.
- [x] Không tạo ảnh Open Graph trong Phase 11a; để tới lúc triển khai.
