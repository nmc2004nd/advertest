# Plan: Phase 7 — Tự tìm ngưỡng

> Phân chia thư mục:
> `ml_core/search/` (agent `ml-search`); `ml_core/metrics/bootstrap.py`, `ml_core/metrics/threshold.py` (agent `ml-metric`);
> `ml_core/runner/`, `backend/worker/` (agent `worker`); `backend/app/`, `backend/migrations/` (agent `backend`); `frontend/` (agent `frontend`).
>
> Thứ tự: Group 0 → (Group 1, 2 song song; Group 4 backend và Group 5–6 frontend bắt đầu với mock) → Group 3 → Group 7.

## Group 0 — Contract `[người duyệt]`

1. Cập nhật contract theo bảng trong `requirements.md`, kể cả: `class_filter: str | None`; `breaking_point` cho `non_monotonic`; `EstimateResponse.max_total_seconds`, `max_exceeds_limit`, `runs` rỗng khi có `searches`; `subset_size ≥ 2`.
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

10. `ml_core/metrics/threshold.py`: tính đại lượng so với ngưỡng cho 3 loại, có và không có `class_filter`, từ `RunResult` và metric sạch; metric của run điền `per_class[*].attack_success_rate` (Group 0).
11. Lưu prediction theo ảnh cho mọi run (`predictions_key`) nếu Phase 2–3 chưa lưu đủ.
12. `ml_core/metrics/bootstrap.py`: lấy mẫu lại theo ảnh với seed; tính `drop_ci` từng điểm; khoảng tin cậy của điểm gãy bằng nội suy; `near_threshold`.

## Group 3 — Worker `[agent: worker]`

13. Thêm `eval_image_ids_sha256` vào `fingerprint_inputs` (null và bỏ khỏi JSON với run toàn slice, theo mẫu `patch_key`); runner hỗ trợ đánh giá trên tập con.
14. Vòng lặp tìm kiếm trong worker: hỏi thuật toán điểm kế tiếp → tạo run qua API → chạy run → đưa kết quả vào thuật toán → gửi `SearchResult` tạm thời.
15. Khôi phục đúng giai đoạn sau gián đoạn bằng cách nạp lại `trajectory` của `bundle.search_results` vào thuật toán (Group 0: không có checkpoint riêng cho trạng thái tìm kiếm); run đang dở tiếp tục từ checkpoint của run.
16. Xử lý `stopped_limit`, hủy, và các trường hợp `failed` (mAP sạch bằng 0, không còn object cho ASR, lỗi không phục hồi).
17. Chạy bootstrap khi kết thúc và gửi `SearchResult` cuối.
18. Thứ tự: attack quét lưới trước, attack tìm ngưỡng sau; `early_stop` (`RunLedger`) không áp cho run của attack tìm ngưỡng.

## Group 4 — Backend `[agent: backend]`

18a. Migration `0008`: cột `runs.scope`, `runs.search_order`, `runs.predictions_key`; nơi lưu `SearchResult` (tạm thời và cuối) theo (experiment, attack); `GRANT` cho `advertest_app` trên bảng mới.
19. Kiểm tra cấu hình `mode = search` theo `requirements.md`; `adv_patch` → `422 not_supported_yet`; trần `MAX_RUNS` tính cả `max_points`.
20. Ước lượng `searches[]`, `max_total_seconds`, `max_exceeds_limit` dùng `ml_core/search/bounds.py`.
21. Endpoint tạo run động: kiểm tra attack, level, số run so với `max_points` (mọi vi phạm → `422`); ghi `scope`, `search_order`; `ordinal` của run động đứng sau mọi run quét lưới của experiment.
22. Lưu `SearchResult` tạm thời và cuối cùng; `ExperimentDetail.search_results`.
22a. `attack_ranking` loại attack `mode = search` và run `scope = subset` (`experiment_views.py::_ranking`); endpoint `skip` (dừng sớm) từ chối run của attack tìm ngưỡng (`422`).
23. Tính trạng thái tiến độ tìm kiếm cho giao diện (điểm đã dùng, khoảng hiện tại, giai đoạn).

## Group 5 — Frontend: wizard `[agent: frontend]`

24. Công tắc chế độ theo attack; form tìm ngưỡng với schema `zod` khớp quy tắc kiểm tra của backend; `tol` mặc định (hi − lo)/256, cảnh báo khi `subset_size` dưới 20.
25. Phần "Nâng cao" thu gọn; khóa chế độ tìm ngưỡng cho `adv_patch` kèm giải thích.
26. Hiển thị chi phí tối đa ở bước 5 và 6.
26a. Nháp wizard cũ mở được: attack thiếu `mode`/`search` là quét lưới.

## Group 6 — Frontend: kết quả `[agent: frontend]`

27. Thẻ tóm tắt điểm gãy với câu kết luận theo trạng thái (đủ 6 trạng thái, kể cả `failed` hiển thị `message`), cảnh báo sát ngưỡng và không đơn điệu.
28. Biểu đồ quỹ đạo (điểm rỗng/đặc, số thứ tự, đường ngưỡng, vùng khoảng, dải khoảng tin cậy) kèm bảng số liệu.
29. Biểu đồ so sánh điểm gãy chuẩn hóa giữa các attack (`not_reached` "> 100%", `below_min` "≤ mức nhỏ nhất").
30. Dòng tiến độ tìm kiếm khi đang chạy.
31. Bố cục điện thoại: chỉ thẻ tóm tắt; chạm để mở biểu đồ toàn màn hình.

## Group 7 — Test nghiệm thu và kiểm tra cuối `[người duyệt]`

32. Viết test nghiệm thu `tests/acceptance/phase_07/` và kịch bản Playwright `frontend/e2e/phase_07/` theo `validation.md`.
33. Chạy các kịch bản manual trên KITTI bằng laptop; so sánh với quét lưới.
34. Trả lời câu hỏi mở; điều chỉnh giá trị mặc định nếu cần.
35. Cập nhật `CHANGELOG.md`, `roadmap.md`; merge.
