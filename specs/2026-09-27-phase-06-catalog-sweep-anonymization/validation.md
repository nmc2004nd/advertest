# Validation: Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

> Test trong `tests/acceptance/phase_06/` và `frontend/e2e/phase_06/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Test tự động chạy trên CPU với fixture; patch dùng `max_iter` nhỏ trong test.

## Automated Tests

### Chung
- [ ] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [ ] `make contracts` không tạo thay đổi; 7 spec mới validate được và `spec_sha256` khớp.
- [ ] `roadmap.md` đã phản ánh việc chuyển làm mờ sang Phase 6.

### Seed theo ảnh — `test_per_image_seed.py`
- [ ] Với `snow`, `frost`, `bbox_occlusion`: cùng `seed` và `image_id` cho cùng kết quả dù ảnh nằm ở batch khác nhau, batch size khác nhau (1 và 5) hay thứ tự ảnh bị đảo.
- [ ] Khác `image_id` cho kết quả khác.

### Corruption — `test_corruptions.py`
- [ ] Cả 5 corruption chạy được ở cả 5 severity trên ảnh letterbox của KITTI (vùng ảnh thật khoảng 640×193) và của fixture.
- [ ] Vùng pad không đổi (so sánh chính xác).
- [ ] Ảnh kết quả nằm trong [0, 1], đúng shape và dtype.
- [ ] Mức khác biệt trung bình so với ảnh gốc tăng theo severity với `fog` và `contrast`.

### Occlusion — `test_occlusion.py`
- [ ] `occlusion_ratio = 0` → ảnh không đổi.
- [ ] Với mỗi object đã map: diện tích bị tô bằng tỉ lệ yêu cầu (sai số ±2% diện tích box), vùng tô nằm hoàn toàn trong box.
- [ ] Điểm ảnh ngoài mọi box và trong ignore region không đổi.

### Patch — `test_patch.py`
- [ ] Slice huấn luyện giao với slice đánh giá → tạo experiment bị `422`; thiếu `training_slice_id` với patch → `422`.
- [ ] Train patch với `max_iter` nhỏ tạo `PatchArtifact` hợp lệ; giá trị mục tiêu cuối tốt hơn giá trị đầu.
- [ ] Diện tích patch bằng `area_ratio` × diện tích vùng ảnh thật (sai số ±1%); patch nằm hoàn toàn trong vùng ảnh thật.
- [ ] Chạy experiment thứ hai cùng khóa patch → không train lại (spy), dùng patch có cùng `patch_sha256`.
- [ ] Ngắt worker giữa lúc train; worker mới train tiếp từ checkpoint, tổng số vòng lặp đúng `max_iter`.
- [ ] `fingerprint_inputs.patch_key` có mặt với run patch, null với run khác.
- [ ] Tiến độ báo `phase = training` rồi `evaluating`.

### Thứ tự và dừng sớm — `test_grid_order_early_stop.py`
- [ ] Hàm sắp thứ tự: level `[2, 4, 8, 16, 32]` → `[2, 8, 32, 4, 16]`.
- [ ] Dựng tình huống level 8 làm mAP ≤ 5% mAP sạch: level 16 và 32 chưa chạy bị `skipped` (`early_stop`), attack không được gọi cho chúng; level nhỏ hơn vẫn chạy.
- [ ] `early_stop = false` → mọi level đều chạy.
- [ ] Dừng sớm của attack này không ảnh hưởng attack khác.
- [ ] Experiment bị dừng do giới hạn sau lượt một vẫn có kết quả ở level nhỏ nhất và lớn nhất.

### Xếp hạng — `test_ranking.py`
- [ ] `auc_drop` đúng quy tắc hình thang trên dữ liệu dựng sẵn (có điểm (0, 0) ở đầu).
- [ ] Level `early_stop` được tính bằng `relative_drop` của level kích hoạt.
- [ ] Attack có dưới 2 level có kết quả → `auc_drop = null`, xếp cuối.
- [ ] Run `partial` hoặc `stopped_limit` → cờ `partial = true`.
- [ ] `attack_ranking` trả qua API trùng với kết quả gọi trực tiếp hàm trong `ml_core`.

### Ước lượng — `test_estimate_phase06.py`
- [ ] Patch chưa có → `training_seconds = max_iter × sec_per_iteration`; patch đã có → `null`.
- [ ] Calibration cho `adv_patch` tạo cost profile có `sec_per_iteration`.

### Làm mờ — `test_anonymization.py`
- [ ] Vùng làm mờ `rule_v1` đúng quy tắc trên dữ liệu dựng sẵn: 1/3 trên của `person`, 40% dưới của `car`/`truck`, toàn bộ ignore region; lấy từ hợp ground truth và prediction (score ≥ 0.25).
- [ ] Điểm ảnh trong vùng làm mờ khác ảnh gốc; ngoài vùng làm mờ giống hệt ảnh gốc.
- [ ] Mọi failure case mới có `anonymization.applied = true`, `method = rule_v1`.
- [ ] Không có đối tượng nào trong MinIO của một run mới chứa ảnh hiển thị chưa làm mờ (so sánh vùng làm mờ với ảnh gốc tái tạo từ dataset).
- [ ] Metric của run không đổi khi bật hoặc tắt bước làm mờ (làm mờ không đụng vào ảnh đưa vào model).
- [ ] Case mới của dataset chưa ẩn danh → `display_mode = normal`; case cũ không có `anonymization` → vẫn `hidden_unanonymized`.

### Quyền — `test_permissions_phase06.py`
- [ ] Endpoint catalog đầy đủ cho `/admin/attacks`: admin → `200`; engineer, reviewer → `403`.

### Frontend — unit và E2E (Playwright, 3 viewport)
- [ ] Wizard: chọn patch mà chưa chọn slice huấn luyện → không sang bước tiếp; danh sách slice huấn luyện không chứa slice giao với slice đánh giá.
- [ ] Preset "Toàn bộ catalog" chọn đủ 10 attack với level mặc định.
- [ ] Engineer chạy experiment toàn catalog (level rút gọn) trên fixture → `completed`; tab Kết quả có bảng xếp hạng và biểu đồ cột; run `early_stop` hiển thị đúng lý do.
- [ ] Chuyển trục hoành chuẩn hóa → mọi attack hiển thị trên dải 0–100%.
- [ ] Run patch hiển thị "Đang train patch" trước "Đang đánh giá".
- [ ] Trình xem case hiển thị dải "Đã làm mờ mặt và biển số" và nhãn ảnh thứ ba đúng theo loại.
- [ ] Admin mở `/admin/attacks` thấy đủ 10 spec; engineer bị chuyển tới `/forbidden`.
- [ ] Ở viewport 390px: bảng xếp hạng hiển thị dạng thẻ, không cuộn ngang.

## Manual Checks

- [ ] Chạy experiment toàn catalog trên slice KITTI 300 ảnh bằng laptop; ghi thời gian train patch, thời gian mỗi attack và bảng xếp hạng vào `CHANGELOG.md`.
- [ ] Hiệu chỉnh `learning_rate` và `max_iter` của patch sao cho giá trị mục tiêu hội tụ trong thời gian chấp nhận được; nếu đổi, cập nhật seed và `version`.
- [ ] Xem patch đã train và vị trí dán trên vài ảnh.
- [ ] Xem mỗi corruption ở severity 1, 3, 5 trên cùng một ảnh: hình ảnh hợp lý, không có viền lạ ở ranh giới vùng pad.
- [ ] Xem occlusion ở tỉ lệ 0.25, 0.5, 0.75.
- [ ] Kiểm tra bằng mắt ít nhất 20 failure case có người và xe: không nhận ra được mặt hay biển số. Nếu có trường hợp lọt, điều chỉnh quy tắc (`rule_v2`) trước khi merge.
- [ ] Mức sụt của các corruption tăng theo severity (kỳ vọng chung); bất thường nào cũng được ghi nhận và giải thích.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện, đặc biệt là kiểm tra làm mờ bằng mắt.
- [ ] Người duyệt đã chấp nhận thay đổi `roadmap.md`, contract và seed catalog.
- [ ] Nếu phải thay thế imagecorruptions, `tech-stack.md` đã cập nhật.
- [ ] Câu hỏi mở đã có câu trả lời.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 6 được đánh dấu hoàn thành.
