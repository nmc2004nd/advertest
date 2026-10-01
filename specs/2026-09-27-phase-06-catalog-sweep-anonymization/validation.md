# Validation: Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

> Test trong `tests/acceptance/phase_06/` và `frontend/e2e/phase_06/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Test tự động chạy trên CPU với fixture; patch dùng `max_iter` nhỏ trong test.

## Automated Tests

### Chung
- [x] `make check` pass, bao gồm test nghiệm thu các phase trước.
- [x] `make contracts` không tạo thay đổi; 7 spec mới validate được và `spec_sha256` khớp.
- [x] `spec_sha256` của 3 spec cũ, fingerprint của mock manifest cũ và `config_sha256` của experiment cũ không đổi sau khi thêm trường Phase 6.
- [x] `roadmap.md` đã phản ánh việc chuyển làm mờ sang Phase 6.

### Seed theo ảnh — `test_per_image_seed.py`
- [x] Với `snow`, `frost`, `bbox_occlusion`: cùng `seed` và `image_id` cho cùng kết quả dù ảnh nằm ở batch khác nhau, batch size khác nhau (1 và 5) hay thứ tự ảnh bị đảo.
- [x] Khác `image_id` cho kết quả khác.

### Corruption — `test_corruptions.py`
- [x] Cả 5 corruption chạy được ở cả 5 severity trên ảnh letterbox của KITTI (vùng ảnh thật khoảng 640×193) và của fixture.
- [x] Vùng pad không đổi (so sánh chính xác).
- [x] Ảnh kết quả nằm trong [0, 1], đúng shape và dtype.
- [x] Mức khác biệt trung bình so với ảnh gốc tăng theo severity với `contrast` (mọi cặp mức) và `fog` (1 < 2 < 3, 4 < 5, 2 < 4, 1 < 5; mức 3 và 4 của tham số gốc imagecorruptions cùng cường độ 2.5, chỉ khác độ nhám, nên không so; chốt ở Group 7).

### Occlusion — `test_occlusion.py`
- [x] `occlusion_ratio = 0` → ảnh không đổi.
- [x] Với mỗi object đã map: diện tích bị tô bằng tỉ lệ yêu cầu (sai số ±2% diện tích box), vùng tô nằm hoàn toàn trong box.
- [x] Điểm ảnh ngoài mọi box và trong ignore region không đổi.

### Patch — `test_patch.py`
- [x] Slice huấn luyện giao với slice đánh giá, khác dataset version, hoặc nhiều hơn 50 ảnh → tạo experiment bị `422`; thiếu `training_slice_id` với patch → `422`.
- [x] Chạm giới hạn thời gian giữa lúc train → run `stopped_limit`; thời gian train đã được cộng vào thời gian đã dùng của experiment.
- [x] Train patch với `max_iter` nhỏ tạo `PatchArtifact` hợp lệ; giá trị mục tiêu cuối tốt hơn giá trị đầu.
- [x] Diện tích patch bằng `area_ratio` × diện tích vùng ảnh thật (sai số ±1% diện tích vùng ảnh thật: patch vuông cạnh nguyên không đạt ±1% tương đối ở tỉ lệ nhỏ; chốt ở Group 2); patch nằm hoàn toàn trong vùng ảnh thật.
- [x] Chạy experiment thứ hai cùng khóa patch → không train lại (spy), dùng patch có cùng `patch_sha256`.
- [x] Ngắt worker giữa lúc train; worker mới train tiếp từ checkpoint, tổng số vòng lặp đúng `max_iter`.
- [x] `fingerprint_inputs.patch_key` có mặt với run patch, null với run khác.
- [x] Tiến độ báo `phase = training` rồi `evaluating`.

### Thứ tự và dừng sớm — `test_grid_order_early_stop.py`
- [x] Hàm sắp thứ tự: level `[2, 4, 8, 16, 32]` → `[2, 8, 32, 4, 16]`.
- [x] Experiment mới có `ordinal` của run theo thứ tự thô → mịn trong từng attack.
- [x] Ngắt worker sau khi một level kích hoạt dừng sớm; worker mới vẫn đánh dấu đúng các level lớn hơn là `skipped` (`early_stop`).
- [x] Run `early_stop` có `status_reason.trigger_run_id` đúng run kích hoạt; `POST /runs/{id}/skip` với run không ở `queued` → `409`.
- [x] `slice create --exclude-slice` tạo slice không giao; `GET /slices?disjoint_from=` không trả slice giao.
- [x] Dựng tình huống level 8 làm mAP ≤ 5% mAP sạch: level 16 và 32 chưa chạy bị `skipped` (`early_stop`), attack không được gọi cho chúng; level nhỏ hơn vẫn chạy.
- [x] `early_stop = false` → mọi level đều chạy.
- [x] Dừng sớm của attack này không ảnh hưởng attack khác.
- [x] Experiment bị dừng do giới hạn sau lượt một vẫn có kết quả ở level nhỏ nhất và lớn nhất.

### Xếp hạng — `test_ranking.py`
- [x] `auc_drop` đúng quy tắc hình thang trên dữ liệu dựng sẵn với `x = level / max` (severity 1 → 0.2), có điểm (0, 0) ở đầu, tính đến `coverage` và không ngoại suy.
- [x] Level `early_stop` được tính bằng `relative_drop` của level kích hoạt.
- [x] Attack có dưới 2 điểm (level có metric cộng level `early_stop`) → `auc_drop = null`, xếp cuối; attack sụp ở level đầu rồi các level còn lại bị `early_stop` vẫn có `auc_drop`.
- [x] Run `partial` hoặc `stopped_limit` → cờ `partial = true`.
- [x] `attack_ranking` trả qua API trùng với kết quả gọi trực tiếp hàm trong `ml_core`.

### Ước lượng — `test_estimate_phase06.py`
- [x] Patch chưa có → `training_seconds = max_iter × số ảnh slice huấn luyện × sec_per_image_iteration`, đã cộng vào `total_seconds` và `exceeds_limit`; patch đã có → `null`.
- [x] Calibration cho `adv_patch` tạo cost profile có `sec_per_image_iteration`.
- [x] Calibration cho corruption và occlusion chạy được trên máy chưa có cost profile (batch đo có `image_id` như khi chạy run; lỗi phát hiện ở Group 7 làm experiment kẹt ở `running`).

### Làm mờ — `test_anonymization.py`
- [x] Vùng làm mờ `rule_v1` đúng quy tắc trên dữ liệu dựng sẵn: 1/3 trên của `person`, 40% dưới của `car`/`truck`, toàn bộ ignore region; lấy từ hợp ground truth và prediction (score ≥ 0.25).
- [x] Với ảnh sạch, ảnh sau biến đổi và ảnh thứ ba: điểm ảnh trong vùng làm mờ khác bản chưa làm mờ; ngoài vùng làm mờ giống hệt.
- [x] Mọi failure case mới có `anonymization.applied = true`, `method = rule_v1`.
- [x] Không có đối tượng nào trong MinIO của một run mới chứa ảnh hiển thị chưa làm mờ (so sánh vùng làm mờ với ảnh gốc tái tạo từ dataset).
- [x] Metric của run không đổi khi bật hoặc tắt bước làm mờ (làm mờ không đụng vào ảnh đưa vào model).
- [x] Case mới của dataset chưa ẩn danh → `display_mode = normal`; case cũ không có `anonymization` → vẫn `hidden_unanonymized`.
- [x] `FailureCaseView` có `display_mode = hidden_unanonymized` không chứa khóa MinIO.

### Quyền — `test_permissions_phase06.py`
- [x] Endpoint catalog đầy đủ cho `/admin/attacks`: admin → `200`; engineer, reviewer → `403`.

### Frontend — unit và E2E (Playwright, 3 viewport)
- [x] Wizard: chọn patch mà chưa chọn slice huấn luyện → không sang bước tiếp; danh sách slice huấn luyện không chứa slice giao với slice đánh giá.
- [x] Preset "Toàn bộ catalog" chọn đủ 10 attack với level mặc định; `adv_patch` có 2 level (0.1, 0.25).
- [x] Nháp wizard cũ (`advertest.wizard.v1`) không làm hỏng wizard (khóa mới `v2`).
- [x] Ước lượng hiển thị `training_seconds` khi patch cần train; công tắc dừng sớm bật mặc định.
- [x] Engineer chạy experiment toàn catalog (level rút gọn) trên fixture → `completed`; tab Kết quả có bảng xếp hạng và biểu đồ cột. Run `early_stop` hiển thị đúng lý do: kiểm bằng Vitest (giao diện) và test nghiệm thu backend với worker thật; trên fixture 3 ảnh chỉ `bbox_occlusion` 0.9 (level lớn nhất) làm model sụp nên E2E không dựng được run bị bỏ (chốt ở Group 7).
- [x] Chuyển trục hoành chuẩn hóa → mọi attack hiển thị trên dải 0–100%.
- [x] Run patch hiển thị "Đang train patch" trước "Đang đánh giá" (E2E dùng seed `adv_patch` với `max_iter = 4` và kiểm "Đang train patch (x/4)"; giai đoạn đánh giá 3 ảnh ngắn hơn chu kỳ cập nhật 2 giây nên "Đang đánh giá" kiểm bằng Vitest và thứ tự giai đoạn kiểm ở test nghiệm thu backend; chốt ở Group 7).
- [x] Trình xem case hiển thị dải "Đã làm mờ mặt và biển số" và nhãn ảnh thứ ba đúng theo loại.
- [x] Admin mở `/admin/attacks` thấy đủ 10 spec; engineer bị chuyển tới `/forbidden`.
- [x] Ở viewport 390px: bảng xếp hạng và `/admin/attacks` hiển thị dạng thẻ, không cuộn ngang.

## Manual Checks

- [x] Chạy experiment toàn catalog trên slice KITTI 300 ảnh bằng laptop; ghi thời gian train patch, thời gian mỗi attack và bảng xếp hạng vào `CHANGELOG.md`.
- [x] Hiệu chỉnh `learning_rate` và `max_iter` của patch sao cho giá trị mục tiêu hội tụ trong thời gian chấp nhận được; nếu đổi, cập nhật seed và `version`.
- [x] Xem patch đã train và vị trí dán trên vài ảnh.
- [x] Xem mỗi corruption ở severity 1, 3, 5 trên cùng một ảnh: hình ảnh hợp lý, không có viền lạ ở ranh giới vùng pad.
- [x] Xem occlusion ở tỉ lệ 0.25, 0.5, 0.75.
- [x] Kiểm tra bằng mắt ít nhất 20 failure case có người và xe: không nhận ra được mặt hay biển số. Nếu có trường hợp lọt, điều chỉnh quy tắc (`rule_v2`) trước khi merge.
- [x] Mức sụt của các corruption tăng theo severity (kỳ vọng chung); bất thường nào cũng được ghi nhận và giải thích.

## Definition of Done

- [x] Toàn bộ Automated Tests pass trên CI.
- [x] Toàn bộ Manual Checks đã thực hiện, đặc biệt là kiểm tra làm mờ bằng mắt.
- [x] Người duyệt đã chấp nhận thay đổi `roadmap.md`, contract và seed catalog.
- [x] Nếu phải thay thế imagecorruptions, `tech-stack.md` đã cập nhật.
- [ ] Câu hỏi mở đã có câu trả lời.
- [x] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase 6 được đánh dấu hoàn thành.
