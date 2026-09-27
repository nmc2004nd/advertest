# Plan: Phase 7 — Tự tìm ngưỡng

> Phân chia thư mục:
> `ml_core/search/` (agent `ml-search`); `ml_core/metrics/bootstrap.py`, `ml_core/metrics/threshold.py` (agent `ml-metric`);
> `ml_core/runner/`, `backend/worker/` (agent `worker`); `backend/app/` (agent `backend`); `frontend/` (agent `frontend`).
>
> Thứ tự: Group 0 → (Group 1, 2 song song; Group 4 backend và Group 5–6 frontend bắt đầu với mock) → Group 3 → Group 7.

## Group 0 — Contract `[người duyệt]`

1. Cập nhật contract theo bảng trong `requirements.md`.
2. Thêm endpoint nội bộ `POST /internal/worker/experiments/{id}/runs` vào OpenAPI.
3. Viết mock: `SearchResult` cho mỗi trạng thái (kể cả tạm thời khi đang chạy); quỹ đạo có điểm tập con, toàn slice, điểm tổng hợp; `EstimateResponse` có `searches`.
4. `make contracts`; ghi `CHANGELOG.md`.

## Group 1 — Thuật toán tìm kiếm `[agent: ml-search]`

5. `ml_core/search/subset.py`: chọn tập con xác định theo `hash(seed, image_id)`.
6. `ml_core/search/bounds.py`: tính `max_subset_points`, `max_full_points`, `max_points` cho tham số liên tục và rời rạc.
7. `ml_core/search/algorithm.py`: máy trạng thái thuần (không gọi GPU) gồm các giai đoạn quét thô, chia đôi, xác nhận, dịch khoảng; nhận kết quả từng điểm qua callback, trả "điểm cần đánh giá kế tiếp" hoặc kết quả cuối; trạng thái tuần tự hóa được cho checkpoint.
8. Phát hiện không đơn điệu; điểm tổng hợp cho giá trị "không biến đổi".
9. Unit test với hàm mức sụt tổng hợp (đơn điệu, không đơn điệu, bậc thang, có nhiễu giữa tập con và toàn slice).

## Group 2 — Đại lượng ngưỡng và bootstrap `[agent: ml-metric]`

10. `ml_core/metrics/threshold.py`: tính đại lượng so với ngưỡng cho 3 loại, có và không có `class_filter`, từ `RunResult` và metric sạch.
11. Lưu prediction theo ảnh cho mọi run (`predictions_key`) nếu Phase 2–3 chưa lưu đủ.
12. `ml_core/metrics/bootstrap.py`: lấy mẫu lại theo ảnh với seed; tính `drop_ci` từng điểm; khoảng tin cậy của điểm gãy bằng nội suy; `near_threshold`.

## Group 3 — Worker `[agent: worker]`

13. Thêm `eval_image_ids_sha256` vào `fingerprint_inputs`; runner hỗ trợ đánh giá trên tập con.
14. Vòng lặp tìm kiếm trong worker: hỏi thuật toán điểm kế tiếp → tạo run qua API → chạy run → đưa kết quả vào thuật toán → gửi `SearchResult` tạm thời.
15. Lưu trạng thái tìm kiếm vào checkpoint experiment; khôi phục đúng giai đoạn.
16. Xử lý `stopped_limit`, hủy, và các trường hợp `failed` (mAP sạch bằng 0, không còn object cho ASR, lỗi không phục hồi).
17. Chạy bootstrap khi kết thúc và gửi `SearchResult` cuối.
18. Thứ tự: attack quét lưới trước, attack tìm ngưỡng sau.

## Group 4 — Backend `[agent: backend]`

19. Kiểm tra cấu hình `mode = search` theo `requirements.md`; `adv_patch` → `422 not_supported_yet`.
20. Ước lượng `searches[]` dùng `ml_core/search/bounds.py`.
21. Endpoint tạo run động: kiểm tra attack, level, số run so với `max_points`; ghi `scope`, `search_order`.
22. Lưu `SearchResult` tạm thời và cuối cùng; `ExperimentDetail.search_results`.
23. Tính trạng thái tiến độ tìm kiếm cho giao diện (điểm đã dùng, khoảng hiện tại, giai đoạn).

## Group 5 — Frontend: wizard `[agent: frontend]`

24. Công tắc chế độ theo attack; form tìm ngưỡng với schema `zod` khớp quy tắc kiểm tra của backend.
25. Phần "Nâng cao" thu gọn; khóa chế độ tìm ngưỡng cho `adv_patch` kèm giải thích.
26. Hiển thị chi phí tối đa ở bước 5 và 6.

## Group 6 — Frontend: kết quả `[agent: frontend]`

27. Thẻ tóm tắt điểm gãy với câu kết luận theo trạng thái, cảnh báo sát ngưỡng và không đơn điệu.
28. Biểu đồ quỹ đạo (điểm rỗng/đặc, số thứ tự, đường ngưỡng, vùng khoảng, dải khoảng tin cậy) kèm bảng số liệu.
29. Biểu đồ so sánh điểm gãy chuẩn hóa giữa các attack.
30. Dòng tiến độ tìm kiếm khi đang chạy.
31. Bố cục điện thoại: chỉ thẻ tóm tắt; chạm để mở biểu đồ toàn màn hình.

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

32. Viết test nghiệm thu `tests/acceptance/phase_07/` và kịch bản Playwright `frontend/e2e/phase_07/` theo `validation.md`.
33. Chạy các kịch bản manual trên KITTI bằng laptop; so sánh với quét lưới.
34. Trả lời câu hỏi mở; điều chỉnh giá trị mặc định nếu cần.
35. Cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
