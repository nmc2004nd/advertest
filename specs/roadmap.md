# Roadmap: AdverTest

> Roadmap trả lời "làm gì tiếp theo" ở cấp dự án. Mỗi phase là một lát cắt dọc: cuối phase luôn có thứ demo được. Chi tiết cách làm nằm trong feature spec `specs/YYYY-MM-DD-<phase>/` (requirements, plan, validation), được viết khi bắt đầu phase.

## Cách dùng

- Làm các phase theo thứ tự phụ thuộc. Các phase ghi "song song với" có thể giao cho các agent khác nhau cùng lúc.
- Bên trong một phase, mỗi task group trong `plan.md` ghi rõ agent sở hữu: `ml-core`, `attack`, `backend`, `frontend`.
- Đánh dấu `[x]` cho từng đầu việc khi hoàn thành, và đánh dấu phase xong khi đạt definition of done chung bên dưới.

## Definition of done chung (áp dụng cho mọi phase)

- [ ] Toàn bộ lệnh trong `validation.md` của phase pass.
- [ ] Test nghiệm thu các phase trước vẫn pass.
- [ ] Lint và type check sạch.
- [ ] Spec đã cập nhật nếu cách làm thay đổi so với kế hoạch.
- [ ] `CHANGELOG.md` đã cập nhật.
- [ ] Đã được review (agent review + người duyệt) và merge.
- [ ] Phase được đánh dấu hoàn thành trong file này.

## Tổng quan

| Phase | Kết quả demo được | Agent | Phụ thuộc | Song song với |
|---|---|---|---|---|
| 0 ✅ | Contract và khung dự án | Người duyệt (chính) | — | — |
| 1 ✅ | CLI đo mAP trên slice KITTI | ml-core | 0 | — |
| 2 ✅ | FGSM/PGD trên CLI, có manifest | ml-core, attack | 1 | 4 |
| 3 ✅ | Job chạy qua API trên máy local | backend, attack | 2 | 4 |
| 4 ✅ | Yêu cầu truy cập, duyệt, RBAC | backend, frontend | 0 | 2, 3 |
| 5 ✅ | Wizard tạo experiment, theo dõi tiến độ | frontend, backend | 3, 4 | 6 |
| 6 | Đủ catalog, quét lưới, làm mờ ảnh | attack, ml-core, backend, frontend | 3, 5 | — |
| 7 | Tự tìm ngưỡng | attack, frontend | 5, 6 | 8 |
| 8 | Protocol, review, report | backend, frontend | 5 | 7 |
| 9 | Máy thuê và ngân sách | backend | 3, 5 | 10 |
| 10 | Dataset riêng | ml-core, frontend | 5 | 9 |
| 11 | Hoàn thiện, responsive, hardening | frontend | 7, 8, 9, 10 | — |

Phân bổ thời gian dự kiến cho 4 tuần: tuần 1 gồm phase 0–2, tuần 2 gồm phase 3–6, tuần 3 gồm phase 7–9, tuần 4 gồm phase 10–11. Nếu chỉ có 3 tuần, xem mục "Thứ tự cắt giảm".

---

## Phase 0 — Contract và khung dự án ✅ Hoàn thành (2026-09-28)

**Mục tiêu:** tạo nền tảng chung để các agent làm song song mà không phải đoán định dạng của nhau. Phase này do người duyệt viết hoặc duyệt từng dòng.

- [x] Repo theo cấu trúc trong `tech-stack.md` mục 8, kèm `CLAUDE.md`.
- [x] Docker Compose chạy được `postgres`, `minio`, `api` rỗng.
- [x] Pin phiên bản thư viện, ghi vào `tech-stack.md`.
- [x] `contracts/`: enum trạng thái, schema `AttackSpec`, `AttackConfig`, `RunResult`, `Manifest`, `SearchResult`.
- [x] DB schema đầu tiên (migration Alembic): users, roles, compute_targets, models, datasets, dataset_versions, slices, attack_specs, protocols, experiments, runs, ledger, reviews, reports, audit_log.
- [x] OpenAPI khung cho các nhóm endpoint chính và API nội bộ của worker.
- [x] Mock data theo từng schema để frontend dùng trước.
- [x] Fixture test: khoảng 5 ảnh và một model rất nhỏ chạy trên CPU.
- [x] CI chạy lint, type check, test.

**Demo:** `docker compose up` chạy được; CI xanh; mock `RunResult` hợp lệ theo schema.

## Phase 1 — Inference và metric ✅ Hoàn thành (2026-09-28), còn tồn đọng

**Mục tiêu:** đo được mAP của model trên ảnh sạch. Đây là mốc bắt buộc của tuần 1.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): 3 manual check cần GPU trong `validation.md` (eval trên GPU, lần hai trên GPU, VRAM và batch size lớn nhất). Baseline hiện đo trên CPU. CI đã xanh sau khi push `main` (người dùng xác nhận).

- [x] Wrapper YOLO cho ART, có chế độ loss và predict.
- [x] Bài kiểm tra gradient tự động cho wrapper.
- [x] Converter KITTI → manifest nội bộ, map class về class của model.
- [x] Dataset version bằng hash; tạo slice cố định khoảng 300 ảnh.
- [x] Metric mAP@0.5, mAP@0.5:0.95; cache prediction ảnh sạch.
- [x] CLI: `advertest eval --model ... --slice ...` xuất JSON.

**Demo:** CLI in ra mAP của YOLO trên slice KITTI.

## Phase 2 — Attack white-box đầu tiên ✅ Hoàn thành (2026-09-28), còn tồn đọng

**Mục tiêu:** chạy FGSM/PGD từ đầu đến cuối, có đủ dữ liệu để tái lập.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): 2 manual check cần GPU trong `validation.md` (thời gian mỗi ảnh và batch lớn nhất khi tính gradient, `--force` trên GPU). Số liệu KITTI hiện đo trên CPU. CI đã xanh sau khi push `main` (người dùng xác nhận, 2026-09-29).

- [x] Interface `Perturbation` và registry attack.
- [x] FGSM và PGD (bước nhảy tỷ lệ theo eps).
- [x] Tỷ lệ tấn công thành công và mức sụt tương đối.
- [x] Fingerprint và `manifest.json` cho mỗi run.
- [x] CLI: `advertest run --config ...` xuất `RunResult` đúng schema.
- [x] Test: cùng config và seed cho metric nằm trong sai số.

**Demo:** mAP trước và sau PGD ở vài mức eps; chạy lại cho kết quả khớp trong sai số.

## Phase 3 — Worker và máy local ✅ Hoàn thành (2026-09-29), còn tồn đọng

**Mục tiêu:** chạy job qua API thay vì CLI, trên máy local.

> Tồn đọng (người dùng cho phép đóng phase): manual check profile `gpu` và số calibration trên GPU (máy phát triển không có GPU). Chưa làm (chuyển tiếp, xem mục "Từ Phase 3" ở các phase sau): user MinIO riêng cho API (Phase 0); `DEFAULT_STORE_DIR` chỉ đúng khi cài editable (Phase 1). CI xanh sau khi push `main` (người dùng xác nhận, 2026-09-29).

- [x] Bảng `compute_targets`, token cho worker.
- [x] API nội bộ: lấy job, báo tiến độ, heartbeat, xin presigned URL.
- [x] Worker gọi lại logic CLI của phase 2.
- [x] Upload artifact lên MinIO, sinh thumbnail cho failure case.
- [x] Đầy đủ trạng thái run, có lý do cho trạng thái bất thường.
- [x] Cache theo fingerprint (`skipped` với lý do `cached`).
- [x] Trần thời gian cho máy local, dừng với `stopped_limit`.
- [x] Lưu tiến độ theo batch, chạy tiếp sau gián đoạn.
- [x] Calibration cost profile cho máy local.
- [ ] (Từ Phase 0) User MinIO riêng cho api và worker thay cho root; image CUDA dùng chung (`TORCH=cuda`); chặn ghi kết quả ở API (chỉ worker); `lease` trả `204` hoặc `WorkerJobBundle`.
- [ ] (Từ Phase 1) `MinioStore` thay đường dẫn tuyệt đối trong `datasets/<sha>/sources/` bằng ảnh lưu theo sha256; `DEFAULT_STORE_DIR` chỉ đúng khi cài editable; `import-local` đọc bố cục `LocalStore` (`index/`, `models/<sha>/weights.pt`, `cache/predictions/` có trường `device`); chỉ admin được đăng ký model (weights nạp bằng pickle).
- [x] (Từ Phase 2) `RunExecutor` giữ hành vi Phase 2 (mask áp lại sau `generate`, lọc/ghép prediction, top-K chép riêng ảnh), checkpoint không chứa ảnh; image đặt `GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`; xử lý `FailureCaseRecord.id` trùng khi hai run cùng fingerprint chạy đồng thời.

**Demo:** gửi job qua API, xem tiến độ; tắt worker giữa chừng, bật lại thì job chạy tiếp.

## Phase 4 — Xác thực và phân quyền ✅ Hoàn thành (2026-09-29)

**Mục tiêu:** ba role hoạt động đúng quyền.

- [x] Yêu cầu truy cập, đăng nhập, đăng xuất (argon2, phiên phía server trong cookie httpOnly).
- [x] Admin duyệt/từ chối tài khoản, gán role.
- [x] `require_permission` (ma trận quyền trong contract) cho mọi endpoint.
- [x] Audit log cho các sự kiện tài khoản; thu hồi quyền `UPDATE/DELETE` trên `audit_log`.
- [x] Frontend: trang giới thiệu tối giản, yêu cầu truy cập, đăng nhập, chờ duyệt, quản lý người dùng.
- [x] Khung điều hướng theo role, mobile-first.
- [x] (Từ Phase 0) Email chuyển về chữ thường; mọi lỗi (kể cả `422`) dùng `ErrorResponse`; mô tả cookie theo phiên phía server.

**Demo:** tài khoản mới ở trạng thái chờ; admin duyệt và gán role; mỗi role chỉ thấy đúng trang của mình.

## Phase 5 — Wizard tạo experiment và theo dõi tiến độ ✅ Hoàn thành (2026-09-30), còn tồn đọng

**Mục tiêu:** engineer làm được việc chính trên web.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): manual check PGD eps 2/4/8/16 trên slice KITTI 300 ảnh qua wizard và sai số ước lượng so với thực tế chưa đo. CI xanh sau khi push `main` (người dùng xác nhận, kiểm tra qua GitHub API, 2026-09-30).

- [x] API experiment: tạo, xem, hủy.
- [x] Wizard: model → slice → attack và chế độ quét lưới → chọn máy và giới hạn → xác nhận.
- [x] Ước lượng thời gian từ cost profile.
- [x] Trang chi tiết: tab Tổng quan, Kết quả, Failure case (có watermark), Chi phí, Tái lập.
- [x] Biểu đồ đường cong metric.
- [x] Email khi experiment xong.
- [x] (Từ Phase 0) `useRun` dừng polling khi run kết thúc.

**Demo:** engineer tạo experiment trên web, theo dõi tiến độ trên điện thoại, xem đường cong khi xong.

## Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh

**Mục tiêu:** bộ attack và biến đổi đầy đủ cho MVP; ảnh failure case được làm mờ để report ở Phase 8 có ảnh.

- [x] Patch attack: train một lần, lưu MinIO, quét theo kích thước.
- [x] Corruption: fog, snow, frost, motion blur, contrast (severity 1–5).
- [x] Occlusion theo tỷ lệ bounding box.
- [x] Quét lưới thô trước, mịn sau; dừng sớm khi mAP gần 0.
- [x] Trang admin xem attack catalog.
- [x] Xếp hạng attack gây hại nhất (`auc_drop`).
- [x] Làm mờ mặt và biển số ở tầng hiển thị (với dataset chưa ẩn danh); chuyển từ Phase 10 (report ở Phase 8 cần ảnh failure case, `mission.md` nguyên tắc 9). Kiểm tra bằng mắt trên KITTI còn mở (manual check, cần dữ liệu KITTI đầy đủ).
- [ ] (Từ Phase 2) Lưới mịn ở eps nhỏ: trên KITTI, PGD L∞ eps 2/255 đã sụt 98%, PGD L2 eps 1 sụt 90% (vùng hữu ích dưới 2/255 và dưới 1).
- [ ] (Từ Phase 5) Đo sai số ước lượng: PGD eps 2/4/8/16 trên KITTI 300 ảnh qua wizard (tồn đọng Phase 5), làm cùng lúc với manual check hiệu chỉnh patch.
- [ ] (Từ Phase 5) CLI `advertest` in JSON ra stdout, nhưng Ultralytics lần đầu import in thông báo settings vào stdout (`scripts/e2e.sh` đang né bằng `YOLO_CONFIG_DIR` và import trước một lần).

**Demo:** một experiment quét toàn bộ catalog, ra bảng xếp hạng attack gây hại nhất; failure case hiển thị với ảnh đã làm mờ.

## Phase 7 — Tự tìm ngưỡng

**Mục tiêu:** tìm điểm gãy theo ngưỡng suy giảm.

- [ ] Thuật toán quét thô → chia đôi → xác nhận trên toàn slice.
- [ ] Tính trước số điểm tối đa để ước lượng chi phí tối đa.
- [ ] Khoảng tin cậy bootstrap.
- [ ] Các trạng thái kết quả tìm kiếm.
- [ ] Wizard: chế độ "Tự tìm ngưỡng".
- [ ] Biểu đồ điểm gãy và so sánh điểm gãy giữa các attack.
- [ ] (Từ Phase 2) Khoảng tìm kiếm mặc định cho PGD phải bắt đầu dưới 1/255; ngưỡng sụt 20% nằm dưới mức eps nhỏ nhất đã đo.

**Demo:** chọn ngưỡng sụt 20% cho PGD, hệ thống trả về điểm gãy kèm khoảng tin cậy.

## Phase 8 — Protocol, review và report

**Mục tiêu:** quy trình duyệt độc lập, chống gian lận.

- [ ] Reviewer tạo protocol (có version); experiment bắt buộc gắn protocol.
- [ ] Khóa experiment khi gửi duyệt.
- [ ] Hàng đợi review, loại experiment do chính reviewer tạo.
- [ ] Trang xem failure case: so sánh trước/sau, heatmap nhiễu, bật tắt lớp box, phím tắt, cử chỉ chạm.
- [ ] Verdict có version; kết luận tổng thể và mitigation.
- [ ] Kiểm tra điều kiện trước khi approve.
- [ ] Report PDF/JSON sinh ở server, lưu sha256; trang `/verify/:id`.
- [ ] Audit log cho toàn bộ vòng đời experiment.
- [ ] (Từ Phase 2) Report ghi rõ eps tính trên ảnh letterbox dạng float (không lượng tử hóa 8-bit); xem lại số failure case mỗi run (mặc định 20).

**Demo:** engineer gửi duyệt; reviewer khác review và approve; xuất report; trang xác minh báo khớp.

## Phase 9 — Máy thuê và ngân sách

**Mục tiêu:** chạy trên GPU thuê trong phạm vi kinh phí.

- [ ] `billing_mode = hourly` cho compute target.
- [ ] Ngân sách dự án, quota người dùng, trần experiment.
- [ ] Ledger giữ chỗ và quyết toán.
- [ ] Dừng khi chạm trần (`stopped_limit`, lý do `budget`).
- [ ] Theo dõi uptime và thời gian chạy không; cảnh báo.
- [ ] Worker từ xa qua Tailscale.
- [ ] Trang admin: compute targets, ngân sách và quota.
- [ ] (Từ Phase 3) User MinIO riêng cho api thay cho root (máy thuê làm lộ phạm vi của khóa rõ hơn); profile `gpu` và calibration trên GPU nếu chưa làm.

**Demo:** thuê máy vài giờ, chạy experiment có trần ngân sách thấp, xác nhận dừng đúng và quyết toán đúng.

## Phase 10 — Dataset riêng

**Mục tiêu:** người dùng kiểm thử trên dữ liệu của mình.

- [ ] Converter YOLO và COCO.
- [ ] Báo cáo kiểm tra khi import.
- [ ] Giao diện map class.
- [ ] Tạo slice theo bộ lọc.
- [x] ~~Làm mờ mặt và biển số ở tầng hiển thị~~: chuyển sang Phase 6. Dataset riêng dùng lại bước làm mờ của Phase 6.
- [ ] (Tùy chọn) Pseudo-label cho dữ liệu không có nhãn, gắn nhãn consistency metric.
- [ ] (Từ Phase 3) `DEFAULT_STORE_DIR` chỉ đúng khi cài editable; `LocalStore` ghi file quyền 0600 (`import-local` phải chạy bằng uid của máy).

**Demo:** upload một dataset YOLO, map class, chạy experiment trên đó.

## Phase 11 — Hoàn thiện

**Mục tiêu:** sẵn sàng demo và bảo vệ.

- [ ] Rà soát responsive trên cả 3 nhóm màn hình; E2E Playwright.
- [ ] Kiểm thử trên điện thoại Android và iPhone thật.
- [ ] Trang giới thiệu hoàn chỉnh.
- [ ] So sánh nhiều experiment.
- [ ] Rà soát bảo mật: quyền endpoint, token worker, cấu hình Tailscale.
- [ ] Tài liệu cài đặt và vận hành.
- [ ] (Từ Phase 4) `/docs`, `/redoc`, `/openapi.json` đang công khai; compose tin cả mạng Docker trong `TRUSTED_PROXIES` (chỉ hợp cho dev; bản triển khai đặt IP reverse proxy); ô chọn người thực hiện trên trang audit tối đa 100 người dùng.
- [ ] (Từ Phase 5) Box trên canvas của trình xem case chưa đọc được bằng trình đọc màn hình; nháp wizard có model/slice đã xóa chỉ được báo qua `422`.
- [ ] (Từ Phase 0) Pin image nền và GitHub Action theo digest/SHA; tài liệu cài đặt nhắc đổi mật khẩu `change-me-*` và việc `make check` cần mạng ở lần đầu.

**Demo:** trọn luồng từ yêu cầu truy cập đến report đã xác minh, trên desktop và điện thoại.

---

## Thứ tự cắt giảm khi thiếu thời gian

Cắt theo thứ tự sau:
1. Pseudo-label cho dữ liệu không nhãn.
2. So sánh nhiều experiment.
3. Trang giới thiệu làm đẹp.
4. Khoảng tin cậy bootstrap và giai đoạn tìm trên tập nhỏ của phase 7 (giữ lõi quét thô → chia đôi).
5. Trang admin chỉ để dạng bảng CRUD thô.

**Không cắt:** dataset riêng, attack white-box, giới hạn chi phí, trạng thái run, tái lập, tách quyền review.

## Backlog (sau phạm vi hiện tại)

- Tấn công black-box.
- Segmentation (SAM2) và 3D detection.
- Tìm kiếm nhiều tham số cùng lúc (ví dụ Optuna).
- Tự bật/tắt máy thuê qua API nhà cung cấp.
- PWA và push notification.
- Adversarial training và các biện pháp phòng thủ.
