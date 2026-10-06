## Phase 5 — Wizard tạo experiment và theo dõi tiến độ

**Trạng thái:** ✅ hoàn thành 2026-09-30, còn tồn đọng. Group 0–7 đã merge.

### Replan sau Phase 5 — 2026-09-30
- Phase 6 `requirements.md` mục Context: ghi các giả định từ code Phase 5 (`display_mode` tính trong `artifacts.py`, cần lưu `anonymization` và bỏ khóa MinIO khi ẩn; `training_seconds` cộng vào `total_seconds` và `exceeds_limit`; preset "Toàn bộ catalog" khoảng 45 run sát trần 50; nháp wizard `v1` gộp nông; E2E trúng cache, máy `e2e-offline`; `early_stop` đếm vào "bỏ qua").
- Phase 7 `requirements.md` mục Context: `not_supported_yet` hiện áp mọi spec; `max_seconds` phải ghép với `total_seconds` và `exceeds_limit`.
- `roadmap.md`: Phase 6 thêm đo sai số ước lượng PGD 300 ảnh (tồn đọng Phase 5) và lỗi stdout của CLI khi Ultralytics import lần đầu; Phase 11 thêm khả năng tiếp cận của box trên canvas và nháp wizard có tài nguyên đã xóa.
- Người dùng chấp nhận toàn bộ đề xuất.

### Phase 5 — Tổng kết (phase-close) — 2026-09-30
- **Giao được:** API experiment (tạo có kiểm tra cấu hình `422` kèm `fields`, ước lượng từ cost profile `images × spp × 1.2`, xem, hủy, nhân bản, giới hạn 3 experiment đang chờ, tên mặc định do DB đặt); đọc tài nguyên cho wizard; URL ảnh `/artifacts/<token>` (HMAC 10 phút, cần phiên), `display_mode` theo `anonymized` và `DEV_ALLOW_UNBLURRED`; email khi kết thúc qua outbox (Mailpit ở dev); frontend wizard 6 bước giữ nháp, danh sách và chi tiết experiment 5 tab (tiến độ polling, biểu đồ Recharts, failure case có watermark, chi phí, tái lập), trình xem case (zoom, slider, vuốt), khối engineer trên `/home`.
- **Contract:** 3 `ErrorCode` mới, `DisplayMode`, `ErrorBody.fields`, 15 schema, OpenAPI các route Phase 5; đề xuất 001 (`RunView.fingerprint` được null khi run chưa bắt đầu). Người dùng chấp nhận (làm thay người duyệt theo ủy quyền).
- **Số liệu cuối:** `make check` (804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest), `make test-db` (353 test, gồm 36 test nghiệm thu Phase 5 với worker CPU thật), `make test-e2e` (60 test, gồm 21 test Phase 5 = 7 kịch bản × 3 viewport, khoảng 2 phút).
- **`validation.md`:** Automated Tests đủ; Manual Checks 6/7 (người dùng xác nhận); Definition of Done 4/5.
- **CI:** xanh trên `68cf796` gồm job `e2e` với worker thật (sau khi sửa `e2e.sh`; người dùng xác nhận, kiểm tra qua GitHub API).
- **Tồn đọng (cập nhật khi có kết quả):** manual check PGD eps 2/4/8/16 trên slice KITTI 300 ảnh qua wizard; sai số ước lượng so với thời gian thực tế chưa đo.
- **Chuyển tiếp (không chặn):** khóa MinIO trong `FailureCaseView.artifacts` vẫn trả khi ảnh bị ẩn; box trên canvas chưa đọc được bằng trình đọc màn hình; nháp cũ có model/slice đã xóa chỉ báo qua `422`; CLI `advertest` có thể lẫn thông báo của Ultralytics vào stdout ở lần đầu (xem replan).
- **Lưu ý:** Group 0, 7, việc review, merge và phase-close do agent làm thay người duyệt theo ủy quyền của người dùng; review và test nghiệm thu do chính agent đã viết code thực hiện nên không độc lập.

### Phase 5 — Group 7 (người duyệt, người dùng giao) — 2026-09-30
#### Thêm
- Test nghiệm thu `tests/acceptance/phase_05/` (36 test `db`, worker CPU thật qua `JobRunner`, fixture KITTI 5 ảnh và YOLOv8n): kiểm tra cấu hình (`422` có `fields`), ước lượng, giới hạn 3 experiment đang chờ, vòng đời (hủy khi đang `running` sau batch đầu, `finished_at`; chuyển từ Group 2; tên mặc định; giới hạn 28800 được chấp nhận), cache theo fingerprint, URL ảnh (token, hết hạn, cần phiên), `display_mode`, email qua outbox (thử lại rồi `failed`), đọc tài nguyên. Spec tự tạo có nội dung không hợp lệ đặt `is_active = false` (task 33).
- E2E `frontend/e2e/phase_05/` (7 kịch bản × 3 viewport = 21): đi hết wizard (seed 0 ở bước 6) → chi tiết → tiến độ tự cập nhật → kết quả (biểu đồ) → chi phí → failure case (watermark, dải cảnh báo dev, bật tắt lớp box, slider trên điện thoại) → tái lập (fingerprint, tải manifest); giữ nháp khi tải lại; level ngoài dải chặn bước 4; nhân bản mở bước 6; reviewer không thấy "Tạo experiment"; hủy qua hộp xác nhận; `/home` có khối experiment đang chờ và lần gửi thứ 4 báo `queue_limit_reached`.
- `scripts/e2e.sh` (task 3a): dựng dữ liệu fixture bằng CLI và `import-local`, tạo bucket MinIO, chạy worker CPU thật cho `local-dev`, máy `e2e-offline` không có worker, `DEV_ALLOW_UNBLURRED=true`, không gửi email; in log worker khi fail. CI job e2e thêm MinIO và fixture.
#### Phát hiện khi làm
- Viewport chạy sau dùng cùng cấu hình nên run trúng cache: E2E chờ trạng thái `completed` và chấp nhận câu "0/2 hoàn thành, 2 bỏ qua".
- Chạy chung `make test-db`: MinIO còn object của Phase 3 (card cùng key, khác thời điểm đăng ký) → `KeyConflictError`; fixture Phase 5 dọn bucket khi dựng lại DB.
- CI job e2e fail lần đầu (sau merge): Ultralytics lần đầu import in thông báo tạo settings ra stdout, lẫn vào JSON của CLI `advertest` mà `e2e.sh` đọc. `e2e.sh` dùng `YOLO_CONFIG_DIR` riêng và import trước một lần (máy local nay chạy như CI).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest. `make test-db`: 353 test. `make test-e2e`: 60 test trong khoảng 2,3 phút.
#### Chưa làm (cần người dùng, task 34)
- KITTI 300 ảnh, PGD eps 2/4/8/16 qua wizard (ghi sai số ước lượng); theo dõi trên điện thoại thật; email trong Mailpit và bấm link; ảnh chưa làm mờ bị ẩn, bật cờ dev thì hiện kèm dải cảnh báo; pinch-zoom, slider, vuốt; iPhone (thanh dưới không bị thanh home che, ô nhập không tự zoom); biểu đồ chế độ sáng và tối. Máy phát triển không có GPU.
#### Review
- Phát hiện chặn (đã sửa trước merge): thiếu 5 mục validation — tên mặc định và giới hạn 28800 (test nghiệm thu), seed 0 ở bước 6, `queue_limit_reached`, `/home` và tab Chi phí (E2E). Ghi vào spec (người dùng chốt): E2E chấp nhận run trúng cache giữa các viewport, máy `e2e-offline` (`validation.md`); fixture dọn MinIO khi dựng lại DB (`plan.md` task 33).
#### Lưu ý
- Test nghiệm thu, E2E và sửa script do agent làm thay người duyệt theo ủy quyền của người dùng (không độc lập).

### Phase 5 — Group 6 (frontend) — 2026-09-30
#### Thêm
- `/experiments`: lọc Của tôi / Tất cả, trạng thái, model; bảng (≥ 1280px) / thẻ; Tải thêm; polling khi còn experiment đang chạy.
- `/experiments/:id`: 5 tab (Tổng quan, Kết quả, Failure case, Chi phí, Tái lập) giữ trên `?tab=`; Hủy (chủ sở hữu, `queued`/`running`, hộp xác nhận); Nhân bản mở wizard `?clone=`; tab Failure case có watermark và ô "Ảnh bị ẩn"; tab Tái lập có fingerprint rút gọn, git commit, cảnh báo `git_dirty`, phiên bản thư viện, Docker image, môi trường, tải `manifest.json`.
- `/failure-cases/:id`: `CaseViewer`, chuyển case trong run (`?run=`), xin lại URL khi ảnh lỗi.
- `/home`: khối engineer (đang chạy hoặc chờ, 5 kết thúc gần nhất, nút tạo).
- Điều hướng: bật "Experiment", thêm "Tạo experiment"; `AppShell` tự tính mục đang sáng (có đường dẫn loại trừ). Vitest 187 → 201.
#### Thay đổi
- Test điều hướng và `/home` (Vitest) theo điều hướng mới; E2E Phase 4 `onboarding.spec.ts`: engineer có 4 mục (commit `phase05(reviewer)`, task 37, người dùng cho phép).
#### Kiểm tra
- Chromium 390/820/1440 với mock: 10 trang không cuộn ngang, không lỗi console; `make test-e2e` 39/39.
#### Quyết định (đã ghi vào `requirements.md`)
- Người dùng chốt: sửa `router.tsx`, `nav/config.ts`, `HomePage.tsx`, `AppShell.tsx`, E2E Phase 4.
- Agent chọn, người duyệt chấp nhận ở review: bộ lọc mặc định theo quyền, tab trên URL, `?run=` cho trình xem, khối `/home` từ 50 experiment mới nhất.
#### Review
- Phát hiện #1 (sửa trước merge): trình xem mở không có `?run=` gọi `GET /runs/` rỗng → `useRun` chỉ gọi khi có id (có test). Ghi nhận: luồng với backend thật (hủy khi đang chạy, tiến độ, tải manifest) chờ E2E Group 7; bảng "Thêm" của admin trên điện thoại chưa có E2E thao tác.
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 201 Vitest; `verify:build` pass; `make test-e2e` 39 test.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 5 (frontend) — 2026-09-30
#### Thêm
- `features/wizard/`: wizard 6 bước tại `/experiments/new` (chặn theo `experiment.create`): thanh bước, cột tóm tắt (desktop), thanh dưới cố định nằm trên thanh tab điều hướng (điện thoại); nháp `sessionStorage` (`advertest.wizard.v1`), xóa khi tạo thành công; protocol, model, dataset version và slice (class mapping tự chọn khi chỉ có một, báo lỗi khi không có), attack với chip level (kiểm dải, trùng, tối đa 12) và bộ gợi ý, "Tự tìm ngưỡng" hiện "Sắp có", máy chạy và giới hạn (phút); ước lượng debounce 500 ms; bước 6 tóm tắt, ước lượng từng run, ô tên, hộp xác nhận; lỗi 422 về đúng bước và trường, 409 `queue_limit_reached` giữ nháp; nhân bản `?clone=<id>` mở bước 6 kèm cảnh báo.
- `ApiError.fields`; chế độ mock trả `POST /experiments/estimate`. Vitest 151 → 187.
#### Kiểm tra
- Chromium 390 và 1440 với mock: đi hết wizard, level ngoài dải chặn bước 4, tải lại giữ nháp, hộp xác nhận, nhân bản mở bước 6, không cuộn ngang. Phát hiện và sửa: thanh tab điều hướng của khung ứng dụng che thanh dưới của wizard trên điện thoại.
#### Quyết định (đã ghi vào `requirements.md`)
- Người dùng chốt: sửa `router.tsx`, `api/errors.ts`, `api/mocks.ts`; chọn sẵn máy local.
- Agent chọn, người duyệt chấp nhận ở review: tự chọn protocol duy nhất, giới hạn theo phút, bộ level gợi ý, bỏ lựa chọn phụ thuộc khi đổi model/dataset, ô tên tùy chọn.
#### Review
- Phát hiện #1 (sửa trước merge): lỗi ô nhập level của attack đã bỏ chọn vẫn khóa nút "Tiếp" → chỉ tính attack đang chọn (có test). Sửa kèm: tên không thuộc body ước lượng; nhân bản báo lỗi khi không tải được slice. Ghi nhận: nháp cũ có model/slice đã xóa chỉ được báo qua 422 (xem lại ở Phase 11).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 187 Vitest; `verify:build` pass.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 4 (frontend) — 2026-09-30
#### Thêm
- `features/experiments/api.ts`: hook experiment, danh sách (Tải thêm), run, manifest, failure case; polling 2 giây khi `queued`/`running`, dừng ở trạng thái cuối, tạm dừng khi tab ẩn; xin lại URL ảnh trước khi hết hạn 60 giây và khi ảnh tải lỗi (một lần mỗi bộ URL); `artifactSrc` thêm `VITE_API_BASE_URL`.
- `statusSentence` và `ExperimentStatusSummary` (cùng cách viết với email).
- `components/charts/MetricCurves`: mỗi attack một khối (mAP@0.5 có đường mAP sạch, tỷ lệ tấn công thành công), run `partial` đánh dấu, bảng số liệu, tab trên điện thoại.
- `components/case-viewer/CaseViewer`: cạnh nhau có zoom đồng bộ (desktop), slider + pinch-zoom + vuốt (điện thoại), 4 lớp box trên canvas theo `devicePixelRatio`, object bị mất tô đỏ, ảnh nhiễu, watermark, khung giữ chỗ `hidden_unanonymized`, dải cảnh báo `dev_unblurred`, slot `aside` cho Phase 8.
- Mock mọi GET của Phase 5 (`src/api/mocks.ts`); `useRun` dừng polling khi run kết thúc (từ Phase 0).
- Dependency: `recharts` 3.10.1, `react-is` 19.2.8 (peer của Recharts), `react-zoom-pan-pinch` 4.2.0. Vitest 103 → 151.
#### Kiểm tra
- Chromium 3 viewport với mock (trang thử tạm, không commit): không cuộn ngang, không lỗi console, Recharts render, slider chỉ ở 390px, canvas theo DPR.
#### Quyết định (đã ghi vào `requirements.md`, `tech-stack.md`)
- Người dùng chốt: sửa `src/api/mocks.ts`, `queries.ts`; bố cục biểu đồ mỗi attack một khối.
- Agent chọn, người duyệt chấp nhận ở review: định nghĩa object bị mất; ngưỡng nhãn; xin lại URL; vuốt; màu box cố định.
#### Review
- Phát hiện #1 (sửa trước merge): cột `aside` chiếm chỗ khi không có form, khung ảnh desktop ~450px nên nhãn box bị ẩn → cột chỉ có khi có `aside`, nhãn theo màn hình từ 768px (khung 618px ở 1440px). Ghi nhận: tương tác zoom/pinch/vuốt chưa thử thật (E2E Group 7, manual); box trên canvas không đọc được bằng trình đọc màn hình (xem lại ở Phase 11).
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 151 Vitest; `verify:build` pass.
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 3 (backend) — 2026-09-30
#### Thêm
- `backend/app/services/notifications.py`: mẫu email tiếng Việt (HTML và văn bản, escape tên), thêm vào `email_outbox` trong cùng transaction khi experiment chuyển `completed` (`runs._after_run`) hoặc `cancelled` (`experiments.cancel`, cả API và CLI); `deliver_due` (SKIP LOCKED, backoff 30/60/120/240 giây, `failed` sau 5 lần, `last_error`); gửi bằng `smtplib` (không thêm dependency); vòng nền 10 giây trong `lifespan` khi có `SMTP_HOST`.
- Mailpit trong `docker/compose.yaml` (pin digest, giao diện `127.0.0.1:8025`); biến `SMTP_*` cho API và `.env.example`.
- Test: `tests/test_notifications.py` (nội dung, câu tóm tắt, escape, SMTP giả), `tests/db/test_email_outbox.py` (completed/cancelled/rollback, backoff, `failed`, trạng thái experiment không đổi).
#### Kiểm tra
- Gửi thật qua container Mailpit tạm: nhận đúng tiêu đề và nội dung tiếng Việt.
#### Quyết định (đã ghi vào `requirements.md` Phase 5, mục Email)
- Câu tóm tắt, tiêu đề, link; email hủy gửi ngay lúc hủy; không có `SMTP_HOST` thì chờ; backoff; gửi có thể trùng khi commit lỗi (không mất); Mailpit `v1.27`.
#### Review
- Không có phát hiện chặn. Ghi nhận: vòng nền không có test tự động (manual check với `make up`); API chạy ngoài Docker cần bỏ trống `SMTP_HOST`.
#### Số liệu
- `make check`: 804 test Python, 209 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 317 test.
#### Lưu ý
- Code, review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 2 (backend) — 2026-09-30
#### Thêm
- `services/experiment_config.py`: kiểm tra cấu hình dùng chung cho ước lượng và tạo, gom mọi lỗi với đường dẫn trường (`InvalidConfig` → `422 invalid_request` hoặc `not_supported_yet`); lỗi sai schema cũng trả `fields`.
- Ước lượng theo run (`skip_reason = incompatible`, `missing_profiles`, `exceeds_limit` theo cận dưới, `queue.position`, `ahead_seconds`); `POST /experiments/estimate`.
- `POST /experiments` (dùng chung `create_experiment` với CLI `submit`; giới hạn 3 experiment `queued` có khóa dòng user → `409 queue_limit_reached`); `GET /experiments` (lọc `owner`, `status`, `model`, keyset), `GET /experiments/{id}`, `/runs`, `GET /runs/{id}`, `/runs/{id}/manifest`, `POST /experiments/{id}/cancel` (chỉ chủ sở hữu), `GET /experiments/{id}/clone`.
- `services/artifacts.py`: URL ảnh `/artifacts/<token>` (HMAC, 10 phút, chỉ khóa `runs/`), `display_mode` theo `anonymized` và `DEV_ALLOW_UNBLURRED`; `GET /runs/{id}/failure-cases` (thumbnail), `GET /failure-cases/{id}`, `GET /artifacts/{token}` (cần phiên).
- `finished_at` khi `completed` và khi hủy; migration `0005` điền lại `finished_at` còn thiếu.
- `ARTIFACT_TOKEN_SECRET`, `DEV_ALLOW_UNBLURRED` trong compose và `.env.example`.
- Test: `test_experiment_api.py` (29 test, Postgres và MinIO thật).
#### Contract (đề xuất 001, người dùng duyệt)
- `RunView.fingerprint` null khi và chỉ khi run chưa bắt đầu; `RunResult` của worker giữ nguyên (lớp cơ sở chung `_RunCommon`). Mock `run_view` cập nhật, thêm test contract.
#### Thay đổi
- Test nghiệm thu Phase 0 (`IMPLEMENTED_GROUPS` thêm `/experiments`, `/runs`, `/failure-cases`) và Phase 4 (`POST /experiments` đại diện `experiment.create` nay trả `422 invalid_request`): commit `phase05(reviewer)`, người dùng cho phép. Test backend `test_errors.py`: chỉ lỗi `422` có `fields`, không lặp lại giá trị gửi lên ở bất kỳ đâu trong body (review #1).
#### Quyết định (đã ghi vào `requirements.md` Phase 5)
- Người dùng chốt: đề xuất 001; khóa token từ biến môi trường; sửa test nghiệm thu trong nhánh.
- Agent chọn, người duyệt chấp nhận ở review: `fields` cho lỗi sai schema; từ chối attack spec trùng; hàng đợi chỉ `queued`, thứ tự `submitted_at`, `id`; ước lượng không kiểm giới hạn 3; `GET /runs/{id}`; chi tiết URL ảnh (khóa `runs/`, đọc trọn, `Cache-Control`, thumbnail dự phòng); nhân bản giữ spec cũ khi không có version mới.
#### Phát hiện khi làm
- Route ảnh và manifest mở MinIO trước khi kiểm tra token/run (token sai → `500` khi thiếu cấu hình MinIO): nay chỉ đọc MinIO sau khi hợp lệ.
#### Số liệu
- `make check`: 796 test Python, 209 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 312 test.
#### Chuyển cho Group 7
- Test API hủy experiment đang `running` (validation "worker dừng").
#### Lưu ý
- Code, review, sửa sau review và ghi spec do cùng một agent làm (không độc lập).

### Phase 5 — Group 1 (backend) — 2026-09-29
#### Thêm
- Migration `0004`: `compute_targets.max_time_limit_s` (mặc định 28800, CHECK mặc định ≤ tối đa); `experiments.created_at` (điền `submitted_at`, index `(created_at, id)`), `name` NOT NULL (trigger `experiments_default_name` đặt `<model> · <slice> · <ngày UTC>` khi bỏ trống; experiment cũ điền cùng quy tắc), `cloned_from`, `finished_at` (experiment cũ đã kết thúc lấy thời điểm run cuối cùng xong); bảng `email_outbox` (có `next_attempt_at`; app không xóa được).
- `advertest-admin compute-target create --max-time-limit`, `compute-target set-limits` (audit `compute_target.update_limits`), `list` in giới hạn tối đa.
- `backend/app/services/catalog.py` và route `GET /models`, `/models/{id}`, `/datasets`, `/dataset-versions/{id}`, `/slices`, `/class-mappings`, `/attack-specs` (chỉ đang hoạt động), `/protocols` (`active`, `dev`), `/compute-targets` (`online` theo heartbeat 60 giây, `queue_length` đếm `queued`); `404` khi không có.
- API nội bộ của worker khai `422` là `ErrorResponse` (task 5a); OpenAPI không còn `HTTPValidationError`.
- Test: `test_migration_0004.py` (nâng từ 0003 với dữ liệu kiểu Phase 3), `test_catalog_api.py`, `set-limits` ở service và CLI.
#### Thay đổi
- Test nghiệm thu Phase 0 `test_api.py`: `IMPLEMENTED_GROUPS` thêm 6 nhóm (commit `phase05(reviewer)`, người dùng cho phép). Test backend: `SAMPLE_CALLS`, test CSRF cho GET dùng `/budget` (route còn là khung).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 5)
- `email_outbox.next_attempt_at`; người duyệt cập nhật `IMPLEMENTED_GROUPS` trong nhánh.
- Review: `GET /attack-specs` giữ nghiêm (spec hỏng → `500`), dữ liệu test tự tạo spec rỗng phải `is_active = false` (`plan.md` task 33); Group 2 điền lại `finished_at` còn thiếu (task 13).
- Agent tự chọn, người duyệt chấp nhận ở review: tên mặc định bằng trigger DB (để test Phase 0 chèn experiment không tên vẫn chạy); `queue_length` chỉ đếm `queued`; lệnh `set-limits`.
#### Số liệu
- `make check`: 801 test Python, 212 test nghiệm thu không cần DB (6 nhóm khung ít hơn), 103 Vitest. `make test-db`: 283 test.
#### Lưu ý
- Code, review và ghi spec do cùng một agent làm (review không độc lập).

### Phase 5 — Group 0 (người duyệt, người dùng giao) — 2026-09-29
#### Contract
- `ErrorCode` thêm `not_supported_yet` (422), `queue_limit_reached` (409), `internal_error` (500); enum mới `DisplayMode` (`normal`, `hidden_unanonymized`, `dev_unblurred`).
- `ErrorBody.fields` (`FieldError {path, message}`, path dạng `attacks.0.grid.levels`); bỏ khỏi body khi không có, nên lỗi cũ vẫn chỉ có `{code, message}`.
- 15 schema mới: `ExperimentCreate` (`ExperimentConfig` + `name`, `cloned_from`), `ExperimentClone {config, warnings}`, `EstimateResponse` (run có `skip_reason = incompatible` thì `est_seconds = 0`; `total_seconds` null khi và chỉ khi có run thiếu profile; `missing_profiles` đúng bằng các attack đó), `ExperimentSummary` (`finished_at` null khi và chỉ khi `draft`/`queued`/`running`), `ExperimentDetail` (`queue_position` chỉ khi `queued`, `limit` bằng `config.limit`), `ExperimentPage`, `RunView` (`RunResult` + tên, version, tham số chính của spec), `FailureCaseView` (`hidden_unanonymized` thì không URL nào; URL dạng `/artifacts/<token>` tương đối với gốc API), `ComputeTargetPublic`, `ModelSummary`, `DatasetSummary`, `DatasetVersionSummary`, `SliceSummary`, `ClassMappingSummary`, `ProtocolSummary`. 54 JSON Schema.
- Mock sinh bằng script, ID tham chiếu chéo khớp nhau: experiment đủ 10 trạng thái; experiment `completed` có 8 run (hoàn thành, `cached`, lỗi, `stopped_limit` có `metrics.partial`, chưa chạy do chạm trần); run đủ 7 trạng thái; `EstimateResponse` đủ, thiếu profile, vượt giới hạn, `incompatible`; `FailureCaseView` đủ 3 `display_mode`; lỗi có `fields`, `queue_limit_reached`, `not_supported_yet`. Test độ phủ mock trong `contracts/python/tests/test_experiment_models.py`.
- OpenAPI: khung `501` qua `**guard(p)` cho `GET /models`, `/models/{id}`, `/datasets`, `/dataset-versions/{id}`, `/slices`, `/class-mappings`, `/attack-specs`, `/protocols`, `/compute-targets`, `GET|POST /experiments` (`POST` trả `201`), `POST /experiments/estimate`, `GET /experiments/{id}`, `/runs`, `POST /cancel` (`experiment.cancel_own`), `GET /clone`, `GET /runs/{id}` (nay trả `RunView`), `/runs/{id}/manifest`, `/runs/{id}/failure-cases`, `/failure-cases/{id}`, `/artifacts/{token}` (`experiment.read`, trả `image/png`/`image/webp`). Route người dùng khai `422` là `ErrorResponse`. Permission có route: 12 → 14.
#### Thay đổi
- `backend/app/api/errors.py`: `VALIDATION_ERROR_RESPONSE`; `ApiError` và `error_response` nhận `fields`; handler lỗi không lường trước trả `500 internal_error`, không lộ chi tiết (ghi log).
- Test Phase 0 (`test_contracts.py`, `contracts/python/tests/test_enums.py`): bảng enum thêm mã Phase 5 và `DisplayMode`.
- Ngoài thư mục người duyệt (người dùng cho phép): `backend/app/api/public.py`, `errors.py`, `backend/app/tests/api/test_skeleton.py` (route mới, kiểm tra `422` khai `ErrorResponse`, `500`, `fields`), `backend/app/tests/db/test_route_protection_db.py` (14 permission), `frontend/src/api/messages.ts` (thông điệp 3 mã mới).
#### Quyết định (người dùng chốt, đã ghi vào spec Phase 5)
- Kickoff: ảnh qua API proxy bằng token 10 phút; `skip_reason` và `ExperimentClone` trong contract; E2E bật `DEV_ALLOW_UNBLURRED`; seed cố định 0; code backend mở rộng `backend/app/services/`; `max_time_limit_s` mặc định 28800; tên experiment do server đặt khi bỏ trống; làm mờ giữ ở Phase 10; giữ giới hạn 3 experiment đang chờ.
- Group 0: `GET /artifacts/{token}` cần cả phiên (`experiment.read`) lẫn token, không công khai (không phải sửa test Phase 4, thêm một lớp bảo vệ); thêm cột `experiments.created_at` (Group 1, điền `submitted_at`).
- Người duyệt (agent) tự chọn: `ModelSummary` dùng `framework` thay kiến trúc (DB không có cột); `GET /experiments` mặc định `owner=all`; danh sách tài nguyên của wizard trả mảng (không phân trang).
#### Chuyển cho group sau (`plan.md` task 5a, 5b)
- Router API nội bộ của worker vẫn khai `422` là `HTTPValidationError` (chỉ OpenAPI; runtime đã trả `ErrorResponse`).
- Khi route khung được cài đặt thật: cập nhật `IMPLEMENTED_GROUPS` (Phase 0), `test_multiple_roles_get_the_union` (Phase 4) và `test_union_of_roles` (backend), vốn đòi `POST /experiments` trả `501`.
#### Số liệu
- `make check`: 808 test Python, 218 test nghiệm thu không cần DB, 103 Vitest. `make test-db`: 264 test.
#### Review (phase-review, 2026-09-29)
- Không có phát hiện chặn. Phát hiện #1 (người dùng yêu cầu sửa trước merge): contract cấm `exceeds_limit = true` khi thiếu profile, nên phần ước lượng được đã vượt giới hạn cũng không cảnh báo → bỏ ràng buộc, `exceeds_limit` tính trên cận dưới; ghi vào `requirements.md` mục Ước lượng và `validation.md`. Phát hiện #6: `cloned_from` phải tồn tại (ghi vào `plan.md` task 9).
- Ghi nhận: khóa MinIO trong `FailureCaseView.artifacts` vẫn trả khi ảnh bị ẩn (không cho quyền đọc; xem lại ở Phase 11).
#### Lưu ý
- Group 0, review và phần sửa sau review do cùng một agent làm thay người duyệt theo ủy quyền của người dùng; không độc lập.

### Kickoff Phase 5 — 2026-09-29
- Chốt 8 câu hỏi (xem Quyết định ở Group 0), bổ sung độ phủ vào `validation.md` (đọc tài nguyên, `online`/`queue_length`, lọc và phân trang, `finished_at` khi hủy, xin lại URL, `queue_limit_reached` trên giao diện, `/home`, tab Chi phí) và task 3a (worker và `DEV_ALLOW_UNBLURRED` trong `scripts/e2e.sh`).
