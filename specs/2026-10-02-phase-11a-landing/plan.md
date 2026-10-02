# Plan: Phase 11a — Landing page

> Làm tuần tự trong một tab, mỗi group một nhánh. Toàn bộ code nằm trong các thư mục ghi ở từng group; không sửa trang nào khác.
> Thứ tự: Group 0 → 1 → 2 → 3 → 4.
> Có thể giao Group 1–3 với dữ liệu smoke sau khi phần chuẩn bị tương ứng của Group 0 đã merge. Chỉ bắt đầu Group 4 sau khi smoke đã được thay bằng dữ liệu experiment thật.

## Group 0 — Chuẩn bị `[người duyệt]`

1. Duyệt và commit `specs/design.md`; thêm nó vào thứ tự đọc trong `CLAUDE.md`.
2. Cập nhật `roadmap.md`:
   - **Phase 11a — Landing page** (phase này, làm ngay sau Phase 8);
   - **Phase 11b — Giao diện ứng dụng:** token toàn cục và nút chuyển sáng/tối; khung ứng dụng và trang vùng C; dải kết luận và lưới biểu đồ nhỏ ở chi tiết experiment; trình xem case vùng A và không gian review hai cột; gom và viết lại câu chữ; trang đăng nhập, yêu cầu truy cập, chờ duyệt, xác minh theo vùng B; font và màu của report PDF;
   - **Phase 11c — Hoàn thiện:** so sánh nhiều experiment, rà soát bảo mật, tài liệu vận hành, kiểm thử trên thiết bị thật toàn ứng dụng.
3. Pin và commit `@fontsource/be-vietnam-pro`, `@axe-core/playwright`, `@lhci/cli` trong `frontend/package.json` và lockfile; đồng bộ phiên bản chính xác vào `tech-stack.md`.
4a. Khi chưa có experiment thật, tạo `frontend/src/features/landing/demo-data.json` smoke hợp lệ, `source.kind = smoke`, có 4–6 object và đường cong nhất quán; dữ liệu phải hiện nhãn "Dữ liệu minh họa tạm thời".
4b. Sửa `scripts/export_demo_data.py` để xuất đúng toàn bộ schema trong `requirements.md` và pass Ruff.
4c. Trước Group 4, chạy script với PGD L∞ trên KITTI 300, thay smoke bằng dữ liệu thật có `source.kind = experiment`, UUID và `run_date`.
5. Viết test nghiệm thu `frontend/e2e/phase_11a/` theo `validation.md`.

## Group 1 — Nền tảng của landing `[agent: frontend-landing]` — nhánh `phase11a-foundation`

Thư mục: `frontend/src/design/`, `frontend/src/copy/`, `frontend/src/features/landing/` (chỉ phần style và khung).

6. Token theo `design.md` mục 3–5, khai báo trong phạm vi `.zone-landing`, sáng và tối qua `prefers-color-scheme`.
7. Font Be Vietnam Pro tự host, chỉ tải trong route landing (tách code theo route).
8. `frontend/src/design/layers.ts` khai đủ màu token, kiểu nét, độ dày, viền ngoài và phím tắt theo `design.md` mục 3.
9. `frontend/src/copy/vi.ts` với nhóm `landing`; component landing không viết thẳng chuỗi giao diện ngoài nhóm này.
10. Script kiểm tra độ tương phản các cặp token của landing (chạy trong `make test`).

## Group 2 — Demo điểm gãy `[agent: frontend-landing]` — nhánh `phase11a-demo`

Thư mục: `frontend/src/features/landing/demo/`.

11. Đọc và kiểm tra `demo-data.json` (schema, `points` tăng dần).
12. Cảnh đường phố SVG; lớp box vẽ bằng `layers.ts`; mật độ nhiễu tăng theo level; object qua `lost_at` đổi sang kiểu bị mất và giảm opacity dần khi level tiếp tục tăng.
13. Thanh trượt có hỗ trợ bàn phím, chạm, nhãn và giá trị truy cập.
14. Biểu đồ mức sụt (nội suy tuyến tính), đường ngưỡng, điểm đang chọn, nhãn và điểm đánh dấu điểm gãy.
15. Tự quét một lần khi tải trang; dừng khi người dùng chạm; tắt khi giảm chuyển động.
16. Dòng nguồn số liệu; với smoke phải hiện nhãn dữ liệu minh họa tạm thời, với experiment hiện đầy đủ nguồn thật.

## Group 3 — Trang landing `[agent: frontend-landing]` — nhánh `phase11a-page`

Thư mục: `frontend/src/features/landing/`, file định tuyến (chỉ phần import lười và gắn route `/`). Không đổi metadata tĩnh dùng chung trong `frontend/index.html`.

17. Bố cục 9 section theo `requirements.md`, vùng B, căn trái, một cột chính; đủ nội dung bắt buộc của từng section và giới hạn dòng tối đa `72ch`.
18. Nút chính đổi theo trạng thái đăng nhập.
19. Ô xác minh report có kiểm tra mã rỗng, chuyển tới `/verify/:id`.
20. Component metadata đặt title và meta chữ khi landing mount, khôi phục giá trị cũ khi unmount; không tạo `og:image`.
21. Responsive 3 nhóm màn hình; kiểm tra 375 px và vùng chạm của mọi phần tử tương tác tối thiểu 44×44 px.

## Group 4 — Nghiệm thu và đóng phase `[người duyệt]`

22. Duyệt ảnh chụp chuẩn của landing (sáng, tối, 3 viewport).
23. Chạy Lighthouse và axe; chạy toàn bộ test các phase trước.
24. Manual check trên thiết bị thật; rà danh sách "không được dùng" trong `design.md` mục 8.
25. Cập nhật `CHANGELOG.md`, `roadmap.md`; đóng phase.
