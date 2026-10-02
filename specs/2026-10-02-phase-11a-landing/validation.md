# Validation: Phase 11a — Landing page

> Test trong `frontend/e2e/phase_11a/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Ảnh chụp chuẩn chỉ người duyệt được cập nhật.

## Automated Tests

### Không ảnh hưởng phần còn lại
- [ ] `make check` pass, bao gồm toàn bộ test nghiệm thu và E2E của Phase 0–8.
- [ ] `git diff` của phase chỉ chạm: `frontend/src/features/landing/`, `frontend/src/design/`, `frontend/src/copy/`, phần import lười và gắn route `/`, `frontend/package.json` và lockfile, `specs/`, `CLAUDE.md`, `CHANGELOG.md`, test của phase.
- [ ] `frontend/package.json` chứa đúng ba dependency đã pin của Phase 11a; lockfile đồng bộ.
- [ ] Trang `/login` và `/home`: font và màu nền (computed style) giống hệt trước phase này.
- [ ] Mở `/login` trực tiếp (không qua landing): không có request tải file font Be Vietnam Pro.
- [ ] Điều hướng `/` → `/login`: title và các meta của landing được gỡ hoặc khôi phục, không rò sang `/login`.

### Token và lớp overlay
- [ ] Script tương phản: mọi cặp chữ/nền của landing đạt ≥ 4.5:1 ở cả hai chế độ; màu lớp "dự đoán đúng" và "object bị mất" đạt ≥ 3:1 so với nền cảnh demo.
- [ ] Quét mã nguồn `frontend/src/features/landing/`: không có mã màu hex hay `rgb(` viết thẳng; màu box chỉ lấy từ `frontend/src/design/layers.ts`.
- [ ] Unit test `layers.ts`: từng lớp có đúng token màu, dash pattern, độ dày, viền ngoài và phím tắt theo `design.md`.
- [ ] Quét mã nguồn xác nhận mọi chuỗi giao diện của landing được lấy từ nhóm `landing` trong `frontend/src/copy/vi.ts`.
- [ ] Mở landing: không có request nào tới domain ngoài origin của ứng dụng.

### Dữ liệu demo
- [ ] `demo-data.json` hợp lệ theo schema trong `requirements.md`; `points` tăng dần theo `level`.
- [ ] Tại mọi điểm của `points`, tỉ lệ object có `lost_at ≤ level` lệch không quá 0.2 so với `relative_drop`.
- [ ] `source.kind = smoke`: `experiment_id` và `run_date` là null, giao diện hiện "Dữ liệu minh họa tạm thời".
- [ ] `source.kind = experiment`: `experiment_id` là UUID, `run_date` là UTC và nguồn hiện đầy đủ trên giao diện.
- [ ] Cả hai loại dữ liệu đều thỏa ràng buộc đường cong/object.
- [ ] Trước Group 4 và trong CI nghiệm thu cuối: `source.kind = experiment`; production build không còn chuỗi `smoke-fixture`.

### Demo điểm gãy (Playwright, 3 viewport)
- [ ] Thanh trượt điều khiển được bằng phím mũi tên, Home, End; có nhãn truy cập và giá trị hiện tại đọc được.
- [ ] Level dưới `breaking_point`: không có nhãn "Gãy tại". Level từ `breaking_point` trở lên: nhãn hiện đúng giá trị trong `demo-data.json`.
- [ ] Tại một level bất kỳ, số box ở kiểu "object bị mất" bằng số object có `lost_at ≤ level`.
- [ ] Khi tăng level qua ít nhất ba mốc, mật độ lớp nhiễu không giảm.
- [ ] Với object đã qua `lost_at`, opacity không tăng khi level tiếp tục tăng; object chưa mất giữ nguyên opacity và kiểu cyan.
- [ ] Điểm đang chọn trên biểu đồ có tung độ bằng giá trị nội suy tuyến tính của `relative_drop` tại level đó (sai số ±0.01).
- [ ] Khi tải trang (chuyển động bình thường): sau khoảng 2.5 giây, thanh trượt dừng tại `breaking_point`.
- [ ] Với `prefers-reduced-motion: reduce`: thanh trượt đứng yên ở đầu dải khi tải trang.
- [ ] Chạm hoặc nhấn phím vào thanh trượt trong lúc tự quét: tự quét dừng ngay.
- [ ] Ở viewport 390 px: kéo thanh trượt bằng thao tác chạm mô phỏng hoạt động.

### Trang landing (Playwright, 3 viewport)
- [ ] Đủ 9 section theo đúng thứ tự trong `requirements.md`.
- [ ] Chưa đăng nhập: nút chính "Yêu cầu truy cập" dẫn tới `/request-access`. Đã đăng nhập: nút chính "Vào ứng dụng" dẫn tới `/home`.
- [ ] Link "Xác minh report" ở đầu trang cuộn tới section xác minh.
- [ ] Ô xác minh: mã rỗng → hiện lỗi dưới ô, không chuyển trang; có mã → chuyển tới `/verify/<mã>`.
- [ ] Có `<title>`, `meta description`, `og:title`, `og:description`.
- [ ] Không có `og:image`.
- [ ] Section quy trình có đủ bốn bước và vai trò thực hiện; section độ tin cậy có đủ bốn nguyên tắc; section phạm vi có lưu ý "chỉ là môi trường kiểm thử".
- [ ] Khối văn bản chính có computed `max-inline-size` không vượt `72ch`.
- [ ] Mọi nút, link, input và thanh trượt có vùng chạm ít nhất 44×44 px ở viewport điện thoại.
- [ ] Không có thanh cuộn ngang ở 375 px.
- [ ] Mọi phần tử tương tác có viền focus nhìn thấy được khi điều hướng bằng Tab.

### Truy cập và hiệu năng
- [ ] axe: không có vi phạm mức `serious` hoặc `critical` trên landing, ở cả chế độ sáng và tối.
- [ ] Lighthouse cho landing ở chế độ điện thoại: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 90, SEO ≥ 90.
- [ ] Landing không tải ảnh bitmap nào.

### Ảnh chụp chuẩn
- [ ] Landing khớp baseline đã duyệt: sáng và tối, 3 viewport, với thanh trượt đặt ở đầu dải và ở `breaking_point`.

## Manual Checks

- [ ] Xem landing trên điện thoại Android và iPhone thật: demo kéo mượt bằng ngón tay; tiêu đề hero không ngắt dòng xấu.
- [ ] Cho một người chưa biết dự án xem landing 30 giây rồi hỏi "điểm gãy là gì": họ trả lời được đại ý.
- [ ] Đọc lại toàn bộ câu chữ: không có câu kiểu quảng cáo; phạm vi và lưu ý "chỉ là môi trường kiểm thử" hiện rõ.
- [ ] Rà landing theo danh sách "không được dùng" trong `design.md` mục 8.
- [ ] So số liệu trên demo với kết quả của experiment nguồn: khớp. Mục này không thể đánh dấu đạt khi `source.kind = smoke`.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện.
- [ ] Người duyệt đã duyệt `design.md`, `demo-data.json` và ảnh chụp chuẩn.
- [ ] `demo-data.json` dùng `source.kind = experiment`; dữ liệu smoke đã được loại khỏi bản nghiệm thu.
- [ ] `roadmap.md` đã có Phase 11b và 11c.
- [ ] Câu hỏi mở đã có câu trả lời.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 11a được đánh dấu hoàn thành.
