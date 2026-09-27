# Ví dụ dùng skill cho từng phase (Phase 0 → 8)

Tài liệu này đi qua từng phase: chuẩn bị worktree nào, gõ prompt gì theo thứ tự nào, cần chú ý gì khi review, bạn phải tự làm gì, và mang gì sang phase sau. Đọc cùng `docs/huong-dan-agent-workflow.md`.

## Khung chung (áp dụng cho mọi phase)

Mỗi phase lặp lại cùng một khung. Các mục bên dưới chỉ ghi phần **riêng** của từng phase.

```text
[main]      Dùng skill phase-kickoff cho phase N.
            → trả lời câu hỏi → "Đề xuất diff cập nhật spec theo các câu trả lời trên."
            → duyệt, áp dụng, commit spec

[main]      Group 0: bạn tự sửa contracts/, mock, test nghiệm thu → make contracts → make check → commit

[worktree]  Dùng skill phase-implement. Bạn là agent <tên>, làm Group G của Phase N.
            → đọc kế hoạch → "Kế hoạch đã duyệt, làm đi."

[phiên mới] Dùng skill phase-review cho nhánh phaseNN-<agent>, Phase N, Group G.
            → CẦN SỬA: dán phát hiện vào phiên implement → review lại
            → SẴN SÀNG MERGE: tự làm manual check reviewer nêu → merge

[main]      Dùng skill phase-close, chế độ đóng group, cho nhánh phaseNN-<agent>. Mình đã review và đồng ý merge.

[main]      (khi mọi group xong) Dùng skill phase-close, đóng Phase N.
            → xác nhận từng manual check kèm số liệu → duyệt diff replan
```

Lệnh tạo worktree dùng chung:

```bash
git switch main && git pull
git worktree add ../adv-<tên> -b phaseNN-<tên>
cd ../adv-<tên> && claude
```

**Khi bạn cần agent viết nháp thứ thuộc vùng cấm** (contract, test nghiệm thu, spec), mở phiên riêng và nói rõ ngoại lệ, vì `CLAUDE.md` cấm mặc định:

```text
Phiên này bạn là trợ lý của người duyệt, không phải agent implement.
Được phép soạn nháp cho <contracts/... | tests/acceptance/phase_NN/...>
nhưng chỉ xuất ra dạng diff, không ghi file. Mình sẽ duyệt từng dòng rồi tự áp dụng.
```

Đừng dùng cùng một phiên vừa viết test nghiệm thu vừa implement: agent sẽ viết test dễ cho chính code của nó.

---

## Phase 0 — Contract và khung dự án

**Đặc thù:** phần lớn do bạn làm. Agent chỉ vào việc sau khi contract (Group 2) đã merge.

**Thứ tự:**

| Bước | Group | Ai | Nhánh |
|---|---|---|---|
| 1 | Kickoff | agent | `main` |
| 2 | G1 repo và công cụ | bạn (agent hỗ trợ) | `main` |
| 3 | G2 contract | bạn (agent soạn nháp) | `main` |
| 4 | G3 → G4 → G7 (DB → API → compose) | agent `backend`, tuần tự | `phase00-backend` |
| 4 | G5 frontend khung | agent `frontend`, song song | `phase00-frontend` |
| 4 | G6 fixture | agent `ml-core`, song song | `phase00-fixtures` |
| 5 | G8 CI, G9 cài bộ skill, G10 test nghiệm thu | bạn | `main` |

**Prompt riêng:**

Bước 2, nhờ agent dựng khung repo (ngoại lệ có chủ ý):

```text
Phase 0, Group 1. Phiên này bạn là trợ lý của người duyệt và được phép tạo
khung repo theo tech-stack.md mục 8 và plan.md task 1–5: thư mục, pyproject
(uv workspace), frontend Vite + TS strict, Makefile. Chưa pin phiên bản thư viện:
liệt kê phiên bản mới nhất ổn định của torch, adversarial-robustness-toolbox,
ultralytics, torchmetrics, numpy để mình chọn. Commit từng bước.
```

Bước 3, contract:

```text
Soạn nháp Group 2 của Phase 0 (task 7–13) dưới dạng diff, không ghi file.
Ưu tiên: enum đúng bảng trong requirements.md; canonical_json xử lý float
nhất quán (nêu rõ cách bạn chọn); compute_fingerprint không đọc environment.
Liệt kê mọi chỗ bạn phải tự quyết định.
```

Bước 4, ba agent song song:

```text
Dùng skill phase-implement. Bạn là agent backend, làm Group 3, rồi Group 4, rồi Group 7 của Phase 0, lập kế hoạch cho cả ba.
Dùng skill phase-implement. Bạn là agent frontend, làm Group 5 của Phase 0.
Dùng skill phase-implement. Bạn là agent ml-core, làm Group 6 của Phase 0.
```

**Chú ý khi review:**
- Migration: quyền `REVOKE` trên `audit_log`, `reviews`... có đúng cho role `advertest_app` không; trigger tự review có thật sự chặn.
- API: endpoint phải trả `501`, không được "tiện tay" viết logic.
- Frontend: type trong `frontend/src/contracts/` phải được **sinh ra**, không viết tay.
- Fixture: có file `checksums.json`, không commit ảnh hay weights vào repo.

**Bạn tự làm:** `make up`, mở MinIO console và `/docs`, mở `/dev/contracts` ở 375px; đọc lại toàn bộ `contracts/` một lượt.

**Mang sang phase sau:** ghi phiên bản đã pin vào `tech-stack.md`; câu trả lời về nguồn ảnh fixture và đơn vị tiền tệ.

---

## Phase 1 — Inference và metric

**Chuẩn bị:** tải KITTI vào `data/raw/kitti/` trước khi làm Group 6 (KITTI cần đăng ký tài khoản để tải).

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (thêm `ModelCard`, `CleanEvalResult`) | bạn | `main` |
| 2 | G1 store, letterbox, khung CLI | `ml-core` | `phase01-ml-core` |
| 3 | G2 dữ liệu / G3 model / G4 metric (song song) | `ml-data` / `ml-model` / `ml-metric` | 3 worktree |
| 4 | G5 eval, cache, viz | `ml-core` | `phase01-ml-core-2` |
| 5 | G6 test nghiệm thu, manual trên KITTI | bạn | `main` |

**Câu hỏi kickoff nhiều khả năng gặp:** chọn YOLOv8 hay YOLOv11; ảnh fixture có nhãn đủ class `car/truck/person` chưa; `PyTorchYolo` của phiên bản ART đã pin có nhận wrapper Ultralytics không.

**Prompt riêng cho Group 3** (rủi ro lớn nhất của phase):

```text
Dùng skill phase-implement. Bạn là agent ml-model, làm Group 3 của Phase 1.
Trong kế hoạch, nêu rõ bạn sẽ đảm bảo model ở eval mode khi tính loss bằng cách nào,
và cách bạn so khớp prediction của wrapper với predict gốc của Ultralytics.
```

**Chú ý khi review:**
- Có chỗ nào gọi `model.train()` trong đường tính loss (làm đổi running stats của BatchNorm).
- Letterbox: tọa độ ground truth có được chuyển cùng phép biến đổi với ảnh không.
- Lọc ignore region dùng **IoA** (theo prediction), không phải IoU.
- Khóa cache có gồm phiên bản `torch` và `ultralytics`.

**Bạn tự làm:** chạy `advertest eval` trên slice 300 ảnh; mở 8 ảnh từ `advertest viz`; ghi baseline mAP, giây/ảnh, batch size lớn nhất.

**Khi đóng phase, cung cấp cho `phase-close`:**

```text
Dùng skill phase-close, đóng Phase 1. Số liệu: mAP@0.5 = ..., mAP@0.5:0.95 = ...,
sec/ảnh = ... ở batch ..., VRAM đỉnh ... MB. Model chọn: yolov8n.
```

Replan nên xem: baseline thấp (< 0.4) có buộc đổi kế hoạch Phase 2 không; batch size đo được có ảnh hưởng thời gian dự kiến của PGD không.

---

## Phase 2 — Attack white-box đầu tiên

**Song song:** trong lúc làm Phase 2, có thể bắt đầu Phase 4 (chỉ phụ thuộc Phase 0) ở các worktree khác.

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (`mask`, `git_dirty`, `FailureCaseRecord`, rà seed) | bạn | `main` |
| 2 | G1 attack / G2 metric sau tấn công (song song) | `attack` / `ml-metric` | 2 worktree |
| 3 | G3 runner, manifest, CLI | `ml-core` | `phase02-ml-core` |
| 4 | G4 nghiệm thu, golden, sweep KITTI | bạn | `main` |

**Chú ý khi review:**
- Nhiễu ở vùng pad phải bằng **đúng 0**; kiểm tra `mask` thật sự được truyền vào `generate`.
- Nhãn đưa vào attack là **ground truth**, không phải prediction.
- Đơn vị eps: `level / 255` với L∞, nhưng **không chia** với L2.
- `batch_size` và `device` không được lọt vào `fingerprint_inputs`.
- `--force` ghi vào `reruns/`, không ghi đè `result.json` cũ.

**Bạn tự làm:** chạy `pgd_sweep.yaml` trên KITTI; kiểm tra PGD làm mAP giảm nhiều hơn FGSM ở cùng eps; mở 5 failure case xem ảnh nhiễu chỉ nằm trong vùng ảnh thật.

**Mang sang phase sau:** dải eps của `pgd_l2` sau hiệu chỉnh; thời gian mỗi ảnh của PGD (Phase 3 dùng để đặt giới hạn thời gian mặc định).

---

## Phase 3 — Worker và máy local

**Câu hỏi kickoff cần chốt trước:** worker chạy trong Docker (cần `nvidia-container-toolkit`) hay chạy trực tiếp trên laptop; giới hạn thời gian mặc định.

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (schema API nội bộ) | bạn | `main` |
| 2 | G1 executor và store / G2 backend dữ liệu (song song) | `ml-core` / `backend` | 2 worktree |
| 3 | G3 API nội bộ (có thể bắt đầu với executor giả) | `backend` | `phase03-backend-api` |
| 4 | G4 worker | `worker` | `phase03-worker` |
| 5 | G5 CLI quản trị, compose | `backend` | `phase03-backend-ops` |
| 6 | G6 nghiệm thu, kịch bản `kill -9` | bạn | `main` |

**Prompt riêng cho Group 3 khi G1 chưa merge:**

```text
Dùng skill phase-implement. Bạn là agent backend, làm Group 3 của Phase 3.
Group 1 (RunExecutor) chưa merge: dùng một executor giả trong test của bạn,
không tạo code giả trong ml_core/.
```

**Chú ý khi review:**
- Package worker không được import `backend.app`, SQLAlchemy hay client MinIO có thông tin đăng nhập.
- Presigned PUT chỉ cho khóa trong `runs/<run_id>/`.
- DB chỉ lưu sha256 của token.
- Thời gian máy bị treo không được cộng vào thời gian đã dùng.
- Sau khi chạy tiếp, không ảnh nào bị tính hai lần.

**Bạn tự làm:** chạy experiment PGD thật, `kill -9` worker giữa chừng, khởi động lại, so kết quả; gửi lại cùng cấu hình để thấy cache.

---

## Phase 4 — Xác thực và phân quyền

**Song song:** backend và frontend cùng lúc; frontend làm với mock (`VITE_USE_MOCKS=true`) cho đến khi backend merge.

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (sửa `tech-stack.md` sang phiên phía server, ma trận quyền, schema) | bạn | `main` |
| 2 | G1 → G2 → G3 | `backend` | `phase04-backend` |
| 2 | G4 → G5 → G6 | `frontend` | `phase04-frontend` |
| 3 | Chuyển frontend sang API thật, chạy E2E | `frontend` | `phase04-frontend` (rebase lên `main`) |
| 4 | G7 nghiệm thu, điện thoại thật | bạn | `main` |

**Prompt bước 3:**

```text
Backend Phase 4 đã merge vào main. Rebase nhánh này lên main, tắt mock,
chạy E2E Playwright của Phase 4 trên 3 viewport và báo cáo theo mẫu của phase-implement.
```

**Chú ý khi review:**
- Role hoặc trạng thái **không** được đọc từ cookie; phải đọc từ DB mỗi request.
- Có route nào thiếu `require_permission` (ứng dụng phải từ chối khởi động).
- Middleware CSRF có bị bỏ qua cho route nào không.
- Thông điệp lỗi của "sai mật khẩu" và "email không tồn tại" phải giống hệt nhau.
- Frontend chỉ ẩn nút; không có chỗ nào coi đó là bảo mật.

**Bạn tự làm:** hai trình duyệt, vô hiệu hóa người dùng ở một bên và xem bên kia bị đăng xuất; thử trên iPhone (ô nhập không tự zoom, thanh tab không bị che).

---

## Phase 5 — Wizard và theo dõi tiến độ

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 | bạn | `main` |
| 2 | G1 → G2 → G3 | `backend` | `phase05-backend` |
| 2 | G4 component dùng chung, rồi G6 danh sách/chi tiết | `frontend-detail` | `phase05-fe-detail` |
| 2 | G5 wizard (sau khi G4 merge) | `frontend-wizard` | `phase05-fe-wizard` |
| 3 | G7 nghiệm thu, điện thoại thật, Mailpit | bạn | `main` |

**Prompt riêng:** hai agent frontend cùng sửa `frontend/`, nên phải thu hẹp thư mục:

```text
Dùng skill phase-implement. Bạn là agent frontend-wizard, làm Group 5 của Phase 5.
Chỉ sửa frontend/src/features/wizard/. Component dùng chung ở frontend/src/components/
đã có từ Group 4: chỉ dùng, không sửa; cần sửa thì dừng và báo.
```

**Chú ý khi review:**
- Ước lượng và tạo experiment phải dùng **cùng** hàm kiểm tra.
- Dataset chưa làm mờ: API không được cấp URL ảnh khi cờ dev tắt.
- Polling phải dừng ở trạng thái cuối và khi tab ẩn.
- Email được thêm vào outbox trong cùng transaction với việc đổi trạng thái.

**Bạn tự làm:** tạo experiment KITTI bằng wizard, theo dõi trên điện thoại đến khi xong; ghi sai số giữa thời gian ước lượng và thực tế; kiểm tra email trong Mailpit.

---

## Phase 6 — Đủ catalog, quét lưới và làm mờ

**Đây là phase có nhiều agent song song nhất.**

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (sửa `roadmap.md`, contract, 7 spec mới) | bạn | `main` |
| 2 | G1 corruption + occlusion | `attack-transform` | `phase06-transform` |
| 2 | G2 patch | `attack-patch` | `phase06-patch` |
| 2 | G4 làm mờ | `ml-privacy` | `phase06-privacy` |
| 2 | G6 frontend (dùng mock) | `frontend` | `phase06-frontend` |
| 3 | G3 runner, dừng sớm, xếp hạng | `ml-core` | `phase06-ml-core` |
| 4 | G5 backend | `backend` | `phase06-backend` |
| 5 | G7 nghiệm thu, hiệu chỉnh patch, kiểm tra làm mờ | bạn | `main` |

**Prompt riêng cho `attack-transform`:**

```text
Dùng skill phase-implement. Bạn là agent attack-transform, làm Group 1 của Phase 6.
Bước đầu tiên của kế hoạch: chạy thử cả 5 corruption ở 5 severity trên một ảnh
letterbox của KITTI và báo lỗi tương thích (nếu có) trước khi viết adapter.
```

**Chú ý khi review:**
- Không có ảnh hiển thị **chưa làm mờ** nào được upload (kiểm tra kỹ đường tạo thumbnail).
- Patch không bao giờ train trên slice đánh giá.
- Seed theo ảnh: kết quả không đổi khi đổi batch size.
- Dừng sớm chỉ bỏ level **lớn hơn**, và chỉ trong cùng attack.
- Corruption không làm thay đổi vùng pad.

**Bạn tự làm:** xem ít nhất 20 failure case có người và xe để chắc không nhận ra mặt hay biển số; hiệu chỉnh `learning_rate` và `max_iter` của patch trên laptop.

---

## Phase 7 — Tự tìm ngưỡng

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 | bạn | `main` |
| 2 | G1 thuật toán / G2 ngưỡng và bootstrap (song song) | `ml-search` / `ml-metric` | 2 worktree |
| 2 | G4 backend, G5–G6 frontend (dùng mock) | `backend` / `frontend` | 2 worktree |
| 3 | G3 worker | `worker` | `phase07-worker` |
| 4 | G7 nghiệm thu, so với quét lưới | bạn | `main` |

**Prompt riêng cho Group 1:**

```text
Dùng skill phase-implement. Bạn là agent ml-search, làm Group 1 của Phase 7.
Thuật toán phải là máy trạng thái thuần: không import torch, ART hay estimator.
Trong kế hoạch, liệt kê các trạng thái, các chuyển trạng thái, và công thức
giới hạn số điểm cho cả tham số liên tục và rời rạc.
```

**Chú ý khi review:**
- `ml_core/search/` không gọi GPU hay model.
- Worker không thể tạo vượt `max_points` run (API phải chặn, không chỉ worker tự giác).
- Run tập con và run toàn slice ở cùng level phải có fingerprint khác nhau.
- Bootstrap không gọi model.

**Bạn tự làm:** tìm ngưỡng PGD 20% trên KITTI và đối chiếu với đường cong quét lưới của Phase 5–6; ghi mức lệch giữa tập con và toàn slice.

---

## Phase 8 — Protocol, review và report

**Chuẩn bị:** hai tài khoản người thật (hoặc ít nhất hai tài khoản khác nhau): một engineer, một reviewer. Luồng tách quyền chỉ được kiểm chứng thật khi hai vai khác nhau.

**Thứ tự:**

| Bước | Group | Agent | Nhánh |
|---|---|---|---|
| 1 | Kickoff, G0 (định nghĩa lại `ProtocolBody`, ma trận quyền, `tech-stack.md`) | bạn | `main` |
| 2 | G1 → G2 protocol, gửi duyệt, review | `backend-review` | `phase08-be-review` |
| 2 | G3 report | `backend-report` | `phase08-be-report` |
| 2 | G5 giao diện reviewer | `frontend-review` | `phase08-fe-review` |
| 2 | G4 + G6 phía engineer, report, xác minh | `frontend-report` | `phase08-fe-report` |
| 3 | G7 nghiệm thu, đọc PDF, thử gian lận | bạn | `main` |

**Prompt riêng cho `backend-report`:**

```text
Dùng skill phase-implement. Bạn là agent backend-report, làm Group 3 của Phase 8.
Report phải dựng hoàn toàn từ DB và MinIO, không nhận dữ liệu nội dung từ request.
Trong kế hoạch, nêu cách bạn lấy "experiment liên quan" cho mục Lịch sử
và cách đảm bảo mọi run (kể cả failed, skipped, cancelled) có trong snapshot.
```

**Chú ý khi review** (phase quan trọng nhất về an toàn, nên review kỹ nhất):
- Có đường nào để người tạo experiment nhận review hoặc ra quyết định (kể cả khi có cả hai role)?
- Có endpoint nào sửa được experiment sau khi gửi duyệt mà không đi qua kiểm tra khóa chung?
- Report có lấy dữ liệu từ nơi nào ngoài DB và MinIO không?
- Trang xác minh có gửi nội dung file lên server không (phải tính hash trong trình duyệt)?
- Snapshot có thiếu run `failed`, `cancelled` hay experiment liên quan không?

**Bạn tự làm:** chạy trọn luồng với hai tài khoản; đọc toàn bộ PDF; đóng vai engineer và thử 6 cách gian lận trong `validation.md`, ghi kết quả vào `CHANGELOG.md`.

Nên chạy thêm một lượt review cho cả phase trên `main` sau khi mọi nhánh đã merge, vì lỗ hổng tách quyền thường nằm ở chỗ nối giữa các nhánh:

```text
Dùng skill phase-review cho toàn bộ thay đổi của Phase 8 trên main
(từ commit <commit trước Phase 8> đến HEAD). Tập trung vào mục 5:
nguyên tắc tách quyền, tiêu chí chốt trước, và tính bất biến.
```

---

## Sau Phase 8

Theo gợi ý trước đó: làm Phase 8b (triển khai lên cloud theo cách "VM CPU nhỏ + laptop làm worker"), test MVP với người dùng thật, rồi Phase 10 → Phase 9 → Phase 11. Mỗi phase mới vẫn đi theo đúng khung chung ở đầu tài liệu.
