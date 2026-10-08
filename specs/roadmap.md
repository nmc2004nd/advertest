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
| 6 ✅ | Đủ catalog, quét lưới, làm mờ ảnh | attack, ml-core, backend, frontend | 3, 5 | — |
| 7 ✅ | Tự tìm ngưỡng | attack, frontend | 5, 6 | 8 |
| 8 ✅ | Protocol, review, report | backend, frontend | 5 | 7 |
| 11a | Landing page | frontend-landing | 8 | R1, R4a |
| R1 | Refactor lớp chạy giữ hành vi (runner, attack registry, model adapter) | ml-core, attack, worker | 8 | R4a |
| R4a | Insight, template, Khám phá/Chính thức (backend) | backend | 8 | R1 |
| 10 | Dataset riêng | ml-core, frontend | R1 | R3 |
| R2 | Attack và model đăng ký qua web, tự kiểm tra spec | attack, backend, worker, frontend | R1, 10 | — |
| R3 | Thử nhanh | worker, backend, frontend | R1 | 10, R2 |
| R4b | UX ứng dụng (gộp 11b) | frontend | R4a, R2, 11a | — |
| 9 | Máy thuê và ngân sách | backend | 3, 5 | — |
| 11c | Hoàn thiện: so sánh, bảo mật, tài liệu | frontend, backend | 9, 10, R4b | — |

Thứ tự sau review mentor (2026-10-06): R1 ∥ R4a → 10 → R2 → R3 → R4b → 9 → 11c. Bảng xếp theo thứ tự này.

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

## Phase 6 — Đủ attack catalog, quét lưới và làm mờ ảnh ✅ Hoàn thành (2026-10-01), còn tồn đọng

**Mục tiêu:** bộ attack và biến đổi đầy đủ cho MVP; ảnh failure case được làm mờ để report ở Phase 8 có ảnh.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): manual check đã làm và đạt (người dùng xác nhận), nhưng số liệu chưa ghi vào `CHANGELOG.md`: thời gian train patch, thời gian mỗi attack và bảng xếp hạng trên KITTI 300 ảnh; `learning_rate` và `max_iter` sau hiệu chỉnh (câu hỏi mở 1 của Phase 6, nếu khác seed thì cần đề xuất contract nâng `version` của `adv_patch`). Ba mục "(Từ Phase 2/5)" bên dưới chưa làm. CI xanh trên `main` (người dùng xác nhận, 2026-10-01).

- [x] Patch attack: train một lần, lưu MinIO, quét theo kích thước.
- [x] Corruption: fog, snow, frost, motion blur, contrast (severity 1–5).
- [x] Occlusion theo tỷ lệ bounding box.
- [x] Quét lưới thô trước, mịn sau; dừng sớm khi mAP gần 0.
- [x] Trang admin xem attack catalog.
- [x] Xếp hạng attack gây hại nhất (`auc_drop`).
- [x] Làm mờ mặt và biển số ở tầng hiển thị (với dataset chưa ẩn danh); chuyển từ Phase 10 (report ở Phase 8 cần ảnh failure case, `mission.md` nguyên tắc 9). Đã kiểm tra bằng mắt ≥ 20 case trên KITTI: `rule_v1` đủ (người dùng xác nhận).
- [ ] (Từ Phase 2) Lưới mịn ở eps nhỏ: trên KITTI, PGD L∞ eps 2/255 đã sụt 98%, PGD L2 eps 1 sụt 90% (vùng hữu ích dưới 2/255 và dưới 1). Chưa làm, chuyển sang Phase 7 (replan sau Phase 6).
- [ ] (Từ Phase 5) Đo sai số ước lượng: PGD eps 2/4/8/16 trên KITTI 300 ảnh qua wizard (tồn đọng Phase 5), làm cùng lúc với manual check hiệu chỉnh patch.
- [ ] (Từ Phase 5) CLI `advertest` in JSON ra stdout, nhưng Ultralytics lần đầu import in thông báo settings vào stdout (`scripts/e2e.sh` đang né bằng `YOLO_CONFIG_DIR` và import trước một lần). Chưa làm, chuyển sang Phase 11 (replan sau Phase 6).

**Demo:** một experiment quét toàn bộ catalog, ra bảng xếp hạng attack gây hại nhất; failure case hiển thị với ảnh đã làm mờ.

## Phase 7 — Tự tìm ngưỡng ✅ Hoàn thành (2026-10-02), còn tồn đọng

**Mục tiêu:** tìm điểm gãy theo ngưỡng suy giảm.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): manual check đã làm và đạt (người dùng xác nhận), nhưng số liệu chưa ghi vào `CHANGELOG.md` (danh sách ở mục Tổng kết Phase 7); hai câu hỏi mở (`subset_size` 100, số mẫu bootstrap 200) chờ số liệu đó; mục "(Từ Phase 2, 6)" bên dưới kiểm cùng số liệu đó. Migration 0006 không downgrade được khi có `cost_profiles` của spec Phase 6 (cần agent backend sửa). CI xanh (người dùng xác nhận, 2026-10-02).

- [x] Thuật toán quét thô → chia đôi → xác nhận trên toàn slice.
- [x] Tính trước số điểm tối đa để ước lượng chi phí tối đa.
- [x] Khoảng tin cậy bootstrap.
- [x] Các trạng thái kết quả tìm kiếm.
- [x] Wizard: chế độ "Tự tìm ngưỡng".
- [x] Biểu đồ điểm gãy và so sánh điểm gãy giữa các attack.
- [ ] (Từ Phase 2, 6) Khoảng tìm kiếm mặc định cho PGD phải bắt đầu dưới 1/255; ngưỡng sụt 20% nằm dưới mức eps nhỏ nhất đã đo. Thay cho mục "lưới mịn ở eps nhỏ" chưa làm ở Phase 6.

**Demo:** chọn ngưỡng sụt 20% cho PGD, hệ thống trả về điểm gãy kèm khoảng tin cậy.

## Phase 8 — Protocol, review và report ✅ Hoàn thành (2026-10-02), còn tồn đọng CI

**Mục tiêu:** quy trình duyệt độc lập, chống gian lận.

> Tồn đọng (người dùng cho phép đóng phase, cập nhật sau): mục Automated Tests pass trên CI vẫn để trống. Run 59 tại commit đóng Phase 8 fail job DB/nghiệm thu; run 62 trên `main` fail `ruff format --check` ở `scripts/export_demo_data.py` (thay đổi sau Phase 8). Cần chạy lại CI và ghi kết quả vào `CHANGELOG.md` cùng `validation.md`.

- [x] Reviewer tạo protocol (có version); experiment bắt buộc gắn protocol.
- [x] Khóa experiment khi gửi duyệt.
- [x] Hàng đợi review, loại experiment do chính reviewer tạo.
- [x] Trang xem failure case: so sánh trước/sau, ảnh thứ ba theo loại biến đổi (Phase 6), bật tắt lớp box, phím tắt, cử chỉ chạm.
- [x] Verdict có version; kết luận tổng thể và mitigation.
- [x] Kiểm tra điều kiện trước khi approve.
- [x] Report PDF/JSON sinh ở server, lưu sha256; trang `/verify/:id`.
- [x] Audit log cho toàn bộ vòng đời experiment.
- [x] (Từ Phase 2) Report ghi rõ eps tính trên ảnh letterbox dạng float (không lượng tử hóa 8-bit); số failure case mỗi run giữ 20 (Group 7).
- [x] (Từ Phase 7) Migration 0006 `downgrade` xóa `cost_profiles` của spec `not_applicable` trước (Group 1); test email Phase 5 hết phụ thuộc ngày (Group 7). `DROP OWNED BY` giữ lại làm cách dựng DB test chính thức cho Phase 7, 8: run Phase 6 vẫn chặn `downgrade base`, và migration không xóa dữ liệu thật (người dùng chốt ở Group 7).
- [x] Manual check: luồng thật trên KITTI với hai tài khoản, đọc PDF, PDF và `/verify` trên điện thoại thật, đọc email (người dùng xác nhận 2026-10-02); thử gian lận bằng test tự động gọi API thật (người dùng chấp nhận).
- [ ] Automated Tests pass trên CI (để trống theo quyết định phase-close ngày 2026-10-02; test lại và cập nhật sau).

**Demo:** engineer gửi duyệt; reviewer khác review và approve; xuất report; trang xác minh báo khớp.

## Phase R1 — Refactor lớp chạy giữ hành vi

**Mục tiêu:** tách `JobRunner` (worker) và `Runner` (CLI) thành thành phần trách nhiệm đơn lẻ; attack và model cắm qua registry; không đổi kết quả.

- [x] Golden (người duyệt ghi trước khi đụng code, `6861ca8`): 9 spec × 2 level trên fixture, CPU, cả CLI lẫn worker; worker thêm patch × 2 level và một lần tìm ngưỡng; so theo luật 8 của `tech-stack.md` mục 9.
- [x] `FingerprintService` (gồm provenance) và `ManifestBuilder` dùng chung CLI và worker.
- [x] `ModelAdapter` (Protocol, khai báo năng lực) và adapter Ultralytics; `ModelProvider` nạp lười.
- [x] `PerturbationRegistry`: builder đăng ký theo tên adapter; spec cũ suy ra adapter từ `kind` và `art_class` (`spec_sha256` không đổi); patch đi qua registry; bỏ `isinstance` theo loại cụ thể.
- [x] Chính sách lỗi tập trung (phân loại lỗi → `failed`/`skipped`, OOM).
- [x] `JobRunner` và `Runner` chỉ còn phần điều phối; thứ tự run và dừng sớm dùng chung khi có thể (không bắt buộc; tìm ngưỡng vẫn chỉ ở worker).

**Demo:** chạy lại experiment fixture, golden khớp; thêm một builder giả mà không sửa factory.

## Phase R4a — Insight và luồng (backend)

**Mục tiêu:** có dữ liệu cho trang kết quả mở đầu bằng kết luận, template và tách Khám phá/Chính thức.

- [ ] View insight: điểm yếu chính (attack, level, class, mức sụt), ma trận độ bền attack × khoảng cường độ, câu kết luận sinh có quy tắc từ dữ liệu.
- [ ] Template protocol (Kiểm tra nhanh, Tiêu chuẩn camera trước, Thời tiết, Đầy đủ) và preset experiment (Nhanh, Tiêu chuẩn, Chuyên sâu); gợi ý tiêu chí tự động.
- [ ] Khám phá = protocol `dev-open`, trường `mode` trong view; "Nâng lên chính thức" tạo experiment mới theo protocol (nguyên tắc 11 của `mission.md`).

**Demo:** experiment fixture có danh sách điểm yếu và ma trận; nâng một experiment Khám phá thành experiment Chính thức mới.

## Phase R2 — Mở rộng attack và model qua cấu hình

**Mục tiêu:** thêm attack và model không cần sửa code, vẫn có kiểm soát.

- [ ] Attack spec trỏ tới adapter tổng quát (`adapter`, `adapter_params`); metadata hiển thị ngoài hash.
- [ ] Catalog trong DB; vòng đời spec: admin tạo → tự kiểm tra trên fixture → reviewer duyệt kích hoạt; spec bất biến, sửa là tạo version mới.
- [ ] Tự kiểm tra spec: chạy được, ảnh trong [0, 1], vùng pad không đổi, level "không biến đổi" cho ảnh y hệt, không phụ thuộc batch size, chuẩn nhiễu đúng khai báo.
- [ ] Adapter model `torchvision_detection` và `onnx` (chỉ inference); đăng ký model qua web chỉ nhận ONNX hoặc safetensors (nguyên tắc 10 của `mission.md`).
- [ ] Worker: lỗi `ModelProvider.get` khi kiểm gradient chỉ làm run `failed`, không dừng experiment (tồn đọng R1 Group 5); xét giới hạn cache `ModelProvider`.

**Demo:** admin tạo một biến thể corruption, reviewer duyệt, engineer chọn được trong wizard; đăng ký một model ONNX và chạy corruption trên nó.

## Phase R3 — Thử nhanh

**Mục tiêu:** minh họa trực quan một attack trên một ảnh trong vài giây.

- [ ] Chọn model, một ảnh, attack; tính sẵn mọi level một lần; ảnh sạch và ảnh bị tấn công cạnh nhau kèm box và bảng theo object.
- [ ] Không tạo experiment, không vào report, luôn có nhãn "không phải kết quả kiểm thử"; ảnh upload giữ 24 giờ và vẫn làm mờ.

**Demo:** kéo thanh trượt level và thấy object biến mất.

## Phase R4b — UX ứng dụng

**Mục tiêu:** giải quyết nhận xét M1–M8 của mentor; gộp các mục của Phase 11b.

- [ ] Trang experiment là trung tâm: Tổng quan, Kết quả, Failure case, Review, Report; thanh vòng đời Tạo → Chạy → Phân tích → Gửi duyệt → Review → Report.
- [ ] Wizard 3 bước; chip, thanh trượt, danh sách chọn thay ô gõ; mô tả attack, nhãn level, tên dataset/slice dễ đọc.
- [ ] Mỗi biểu đồ có câu kết luận và "Cách đọc"; ma trận độ bền có chú thích thang màu; tooltip thuật ngữ.
- [ ] Bảng ý nghĩa của từng quyết định ở hộp gửi duyệt, màn hình review, report.
- [ ] Trang chủ "việc cần làm" theo vai trò.
- [ ] Các mục của Phase 11b.

**Demo:** người mới tạo experiment Khám phá trong 3 bước và đọc được điểm yếu chính mà không cần giải thích.

## Phase 9 — Máy thuê và ngân sách

**Mục tiêu:** chạy trên GPU thuê trong phạm vi kinh phí.

- [ ] `billing_mode = hourly` cho compute target.
- [ ] Ngân sách dự án, quota người dùng, trần experiment.
- [ ] Ledger giữ chỗ và quyết toán.
- [ ] Dừng khi chạm trần (`stopped_limit`, lý do `budget`).
- [ ] Theo dõi uptime và thời gian chạy không; cảnh báo.
- [ ] Worker từ xa qua Tailscale.
- [ ] Trang admin: compute targets, ngân sách và quota.
- [ ] (Từ Phase 7) Giữ chỗ ngân sách theo chi phí tối đa (`max_total_seconds`) khi có attack tìm ngưỡng; quyết toán theo thời gian thực.
- [ ] (Từ Phase 8) Trang report định dạng giới hạn ngân sách (đang hiện chuỗi số thô; review Group 6).
- [ ] (Từ Phase 8) Mục "Tài nguyên" của report ghi chi phí đã quyết toán so với ngân sách (snapshot hiện chỉ có thời gian xử lý và giới hạn).
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
- [ ] (Từ Phase 8) Dataset riêng phải qua làm mờ trước khi chạy experiment gửi duyệt: case bắt buộc ở `hidden_unanonymized` chặn gửi duyệt (409).
- [ ] (Từ Phase 3) `DEFAULT_STORE_DIR` chỉ đúng khi cài editable; `LocalStore` ghi file quyền 0600 (`import-local` phải chạy bằng uid của máy).

**Demo:** upload một dataset YOLO, map class, chạy experiment trên đó.

## Phase 11a — Landing page

**Mục tiêu:** trang giới thiệu công khai tại `/` với demo "điểm gãy" tương tác, theo vùng B của `design.md`. Không đổi giao diện các trang khác.

- [ ] Token và font cô lập trong landing; module `layers.ts`.
- [ ] Demo điểm gãy dựa trên số liệu thật (`demo-data.json`).
- [ ] Trang landing 9 section, ô xác minh report, responsive, sáng/tối theo hệ thống.

**Demo:** người chưa biết dự án xem landing 30 giây và giải thích được "điểm gãy" là gì.

## Phase 11b — Giao diện ứng dụng

> Gộp vào Phase R4b (2026-10-06); danh sách dưới đây là các mục R4b phải bao gồm.

**Mục tiêu:** áp dụng `design.md` cho toàn bộ ứng dụng, không đổi hành vi.

- [ ] Token toàn cục, nút chuyển sáng/tối; bỏ phạm vi cô lập của landing.
- [ ] Khung ứng dụng, bảng, wizard, danh sách, hàng đợi review, protocol, admin theo vùng C.
- [ ] Chi tiết experiment: dải kết luận, lưới biểu đồ nhỏ.
- [ ] Trình xem case theo vùng A; không gian review hai cột.
- [ ] Gom và viết lại câu chữ vào `copy/vi.ts` (trước đó: chuyển test E2E sang tìm phần tử theo role, nhãn hoặc `data-testid`).
- [ ] Đăng nhập, yêu cầu truy cập, chờ duyệt, xác minh theo vùng B.
- [ ] Font và màu của report PDF (không đổi nội dung và hash).

**Demo:** toàn bộ luồng ở hai chế độ sáng và tối, trên desktop và điện thoại.

## Phase 11c — Hoàn thiện

**Mục tiêu:** sẵn sàng demo và bảo vệ.

- [ ] So sánh nhiều experiment.
- [ ] Rà soát bảo mật: quyền endpoint, token worker, cấu hình mạng.
- [ ] Tài liệu cài đặt và vận hành.
- [ ] Kiểm thử toàn ứng dụng trên điện thoại Android và iPhone thật.

**Demo:** trọn luồng từ yêu cầu truy cập đến report đã xác minh, trên desktop và điện thoại.

---

## Thứ tự cắt giảm khi thiếu thời gian

Cắt theo thứ tự sau:
1. Pseudo-label cho dữ liệu không nhãn.
2. So sánh nhiều experiment.
3. Phần áp dụng `design.md` của Phase R4b (gộp từ 11b); giữ phần M1–M8.
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
