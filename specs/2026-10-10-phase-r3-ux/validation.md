# Validation: Phase R3 — UX ứng dụng

> Test backend nằm trong `tests/acceptance/phase_r3/`; E2E nằm trong `frontend/e2e/phase_r3/` (Playwright, 3 viewport theo `tech-stack.md` mục 5). Người duyệt viết hoặc duyệt các test này; agent chỉ đọc. Test được thêm theo group (`plan.md` bước 4); ở mỗi thời điểm, mọi test đã có đều phải pass. E2E tìm phần tử theo role, nhãn hoặc `data-testid`, không theo câu chữ dài.

## Automated Tests

### Chung
- [ ] `make check` pass, gồm test nghiệm thu Phase 0–8, R1 và R2.
- [ ] `make test-db` pass; golden R1 (CLI và worker) vẫn khớp.
- [ ] `contracts-check` sạch; `spec_sha256` của 10 spec seed không đổi.
- [ ] `pnpm --dir frontend verify:build` pass.

### Group 1 — Backend (`test_model_recheck.py`, `test_report_insight.py`, `test_purge_orphans.py`; `db`)
- [ ] `POST /models/{id}/check`:
  - từ `check_failed` → 202, status `checking`, có job `model_check` mới và audit `model.rechecked`;
  - từ `ready` hoặc `checking` → 409;
  - weights đã xóa → 409;
  - engineer gọi → 403.
- [ ] Report xuất sau R3 có `snapshot.insight` bằng insight của experiment tại lúc xuất; PDF có section "Điểm yếu chính".
- [ ] Report fixture xuất trước R3 (snapshot không có `insight`): `json_sha256` không đổi, `/verify` vẫn khớp, PDF dựng lại không có section mới.
- [ ] `ExperimentDetail.promoted_from` có với experiment tạo qua promote, không có ở experiment khác.
- [ ] `purge_orphans`:
  - xóa object `quick-tries/<id>/` cũ hơn 30 phút không có dòng, hoặc có dòng đã `deleted_at`;
  - giữ object mới hơn 30 phút và object của lượt còn hạn.
- [ ] Endpoint mới có `x-permission` đúng (test ma trận quyền mở rộng).

### Group 2 — Attack (`test_fixture_inputs.py`, `test_validate_art_class.py`)
- [ ] `fixture_inputs(with_estimator=False)` trả 4 ảnh letterbox, `estimator = None`; `with_estimator=True` có estimator.
- [ ] `validate` với `art_class` không hỗ trợ → `InvalidSpec`; `POST /admin/attack-specs` → 422 (`db`). Spec seed validate được.

### Group 3 — Worker (`test_tool_worker_r3.py`; `db`)
- [ ] `spec_check` qua worker và CLI selfcheck cho cùng `items` trên spec seed `fog` và `fgsm`.
- [ ] Làm mờ thử nhanh, với fixture có người chỉ được phát hiện ở score trong [0.05, `operating_conf`):
  - vùng đó khác ảnh gốc trên ảnh sạch và mọi level;
  - bảng object không chứa object đó.
- [ ] Object chỉ được phát hiện ở một level: vùng của nó bị làm mờ ở mọi ảnh của lượt.

### Group 4 — Nền giao diện (Vitest; E2E `experiment-page.spec.ts`, `home.spec.ts`)
- [ ] `status-config` đủ mọi giá trị của `AttackSpecStatus`, `ModelStatus`, `ToolJobStatus`, `ExperimentMode`, so với mảng enum sinh từ contract.
- [ ] Thanh vòng đời, hàm thuần, theo bảng: mỗi tổ hợp `status` × `review` × `report` → trạng thái 6 bước; experiment Khám phá chỉ có 3 bước.
- [ ] Trang experiment có đúng 5 tab; `?tab=cost` và `?tab=repro` mở Tổng quan, đúng section.
- [ ] Hàm gom việc cần làm, bảng theo vai trò: engineer, reviewer, admin, nhiều vai trò (không trùng), không có việc.
- [ ] `Term` mở tooltip bằng Tab và đóng bằng Esc; có `aria-describedby`.
- [ ] Hộp gửi duyệt, cột quyết định review và trang report hiện bảng ý nghĩa quyết định.

### Group 5 — Wizard và kết quả (Vitest; E2E `wizard.spec.ts`, `insight.spec.ts`)
- [ ] Wizard có 3 bước. Experiment Khám phá tạo được trong 3 bước, chỉ dùng lựa chọn mặc định cộng chọn model/slice (E2E, 3 viewport).
- [ ] Config tạo qua wizard có `config_sha256` bằng config từ `POST /experiments/draft` với cùng lựa chọn.
- [ ] Chính thức: attack và level bắt buộc của protocol không bỏ được trong bước 3.
- [ ] Không có `input[type=number]` tự do ngoài phần "Tùy chỉnh nâng cao".
- [ ] Tab Kết quả:
  - hiện câu kết luận, điểm yếu, ma trận 4 dải và chú thích thang màu;
  - ô `null` ghi "Chưa chạy";
  - `no_data` hiện trạng thái trống;
  - bấm điểm yếu mở Failure case đã lọc đúng attack và level.
- [ ] Hàm sinh câu của từng biểu đồ: bảng dữ liệu → câu; mỗi biểu đồ có nút "Cách đọc".
- [ ] "Nâng lên chính thức":
  - chỉ hiện với experiment Khám phá đã kết thúc;
  - đi tới wizard bước 3 có `promoted_from`;
  - tạo xong, trang experiment mới có link nguồn.

### Group 6 — Admin và duyệt (Vitest; E2E `catalog.spec.ts`, `models.spec.ts`)
- [ ] Form sinh từ `params_schema` của mỗi adapter trong mock `GET /attack-adapters`: enum thành danh sách chọn, số tôn trọng `minimum`/`maximum`. Schema có kiểu chưa hỗ trợ thì hiện thông báo.
- [ ] Luồng E2E: admin tạo biến thể corruption → thấy `checking` rồi kết quả 7 mục → reviewer khác kích hoạt (hộp xác nhận nêu version cũ `retired`) → spec có trong wizard.
- [ ] Reviewer là người tạo spec: nút kích hoạt bị vô hiệu kèm lý do. Từ chối mà không có lý do thì không gửi được.
- [ ] Đăng ký model:
  - file `.pt` hoặc > 500 MB bị chặn ở client;
  - form ONNX hiện ghi chú hai layout;
  - model `check_failed` có nút "Kiểm tra lại".

### Group 7 — Thử nhanh (Vitest; E2E `quick-try.spec.ts`)
- [ ] Danh sách attack ẩn patch, và ẩn attack cần gradient khi model không có gradient.
- [ ] Kéo thanh trượt level: ảnh và bảng đổi, không có request mạng mới.
- [ ] Box `lost` vẽ magenta có ×, `new` magenta nét đứt (kiểm qua `layers` dùng cho canvas).
- [ ] Nhãn "Không phải kết quả kiểm thử" luôn hiện, kèm giờ xóa; 429 hiện link tới lượt đang chạy; 410 hiện "Thử lại".

## Manual Checks

- [ ] Docker: `make up` (gồm `worker-tools`). Admin tạo spec `snow_light`, kiểm tra pass, reviewer kích hoạt, engineer chọn được trong wizard, tất cả không cần chạy worker ngoài Docker.
- [ ] Demo M1–M8: một người chưa dùng ứng dụng tạo experiment Khám phá trong 3 bước, rồi đọc được điểm yếu chính mà không cần giải thích. Ghi lại người thử và chỗ họ vướng.
- [ ] Thử nhanh trên ảnh KITTI: kéo thanh trượt và thấy object biến mất. Đo lại thời gian (mục tiêu < 10 giây khi model đã cache), ghi vào `CHANGELOG.md`.
- [ ] Ảnh thử nhanh có người nhỏ hoặc mờ: không thấy rõ mặt hay biển số ở bất kỳ level nào (nguyên tắc 9).
- [ ] Màn hình mới (thử nhanh, admin model, duyệt spec) đặt cạnh trang cũ cùng loại không lệch phong cách: cùng khung, header, panel, màu nút. Không có màu hex hay token mới trong diff `frontend/src/` (`git diff dev -- frontend/src | grep -E '#[0-9a-fA-F]{6}'` rỗng, ngoài test).
- [ ] Màn hình mới xem được ở 390×844 và 1440×900, ở chế độ sáng và tối hiện có, không vỡ bố cục.
- [ ] Đăng ký thử một model ONNX ngoài fixture; ghi kết quả vào Open Question về layout.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass.
- [ ] Manual Checks đã làm; số liệu và quan sát ghi vào `CHANGELOG.md`.
- [ ] Mỗi M1–M8 có ít nhất một test tự động hoặc mục Manual Check đã đạt.
- [ ] `design.md` và `roadmap.md` đã cập nhật theo Group 0; Phase R3 được đánh dấu hoàn thành.
