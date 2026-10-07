# Validation: Phase R1 — Refactor lớp chạy giữ hành vi

> Test trong `tests/acceptance/phase_r1/` do người duyệt viết hoặc duyệt. Agent chỉ được đọc, không được sửa hay nới lỏng. Golden do người duyệt ghi lại, và chỉ khi lockfile đổi (`ADVERTEST_RECORD_GOLDEN=1`); agent không được ghi lại golden.

## Automated Tests

> Test R1 được thêm theo group (xem `plan.md` bước 7); ở mỗi thời điểm, mọi test đã có đều phải pass.

### Chung
- [ ] `make check` pass, bao gồm test nghiệm thu Phase 0–8.
- [ ] `make test-db` pass.
- [ ] `make contracts` không tạo thay đổi (R1 không đổi contract).

### Golden — `test_golden_cli.py`, `test_golden_worker.py` (`db`)
- [x] Ghi trên code trước refactor (Group 0, `6861ca8`).
- [ ] Pass ở cuối mỗi group của agent: tập run, trạng thái, `fingerprint_inputs` và `fingerprint` giống từng byte; metric trong sai số; failure case giống hệt.

### Checkpoint — `test_checkpoint_compat.py` (`db`)
- [ ] Checkpoint do code trước R1 ghi (fixture Group 2): worker sau R1 chạy tiếp từ batch kế tiếp, kết quả cuối khớp với run không gián đoạn (metric trong sai số).
  > Giới hạn: fixture chỉ thay JSON checkpoint; artifact ứng viên của batch 0 do code hiện tại ghi (chấp nhận vì R1 không đổi layout artifact).

### Kiến trúc — `test_architecture_r1.py` (AST, không cần DB)
- [ ] `ml_core/runner/**` và `backend/worker/advertest_worker/**` không import `attacks.art_adapter`, `attacks.corruptions.adapter`, `attacks.occlusion.adapter`, `attacks.patch.adapter`; không có `isinstance` với các lớp perturbation cụ thể.
- [ ] `attacks/` không còn tên `AnyPerturbation`.
- [ ] `backend/worker/advertest_worker/job.py` không import `build_fingerprint_inputs`, `Manifest`, `ml_core.models.estimator`, hay module `attacks` nào ngoài `attacks.builders` và `attacks.registry`.
- [ ] Không còn test nghiệm thu nào patch `build_perturbation`, `git_state` hay `predict_slice` ở cấp module.

### Registry — `test_registry.py`
- [ ] Mọi spec của catalog có `effective_adapter` thuộc 4 adapter mặc định; `spec_sha256` không đổi so với `contracts/seeds/attack_specs.json`.
- [ ] Builder giả (adapter `test.identity`, nhân ảnh với 1) đăng ký vào registry của test, có resolver riêng, truyền vào runner CLI qua `perturbation_factory`: run `completed`, ảnh sau biến đổi y hệt ảnh gốc; không sửa file nào ngoài test.
- [ ] Đăng ký trùng tên adapter → lỗi.
- [ ] Spec white-box với model không hỗ trợ gradient (qua `ModelProvider` giả) → `skipped` (`incompatible`), thông điệp như Phase 2; corruption trên cùng model → `completed`.

### Chính sách lỗi — qua seam, worker thật (`db`)
- [x] Builder ném lỗi ở run thứ hai → run đó `failed` (`error`), các run khác `completed` (tương đương `phase_07/test_search_e2e_backend.py`, `phase_08` sau khi chuyển sang seam).
- [x] Provenance giả có `dirty = true` → `git_dirty` trong manifest đúng (như `phase_08`).

## Manual Checks

- [ ] Chạy một experiment toàn catalog trên KITTI (laptop, CPU) bằng worker sau R1; so metric với baseline ở `plan.md` bước 7b (lệch trong sai số).
- [ ] Đo thời gian chạy experiment toàn catalog trước và sau R1; chênh lệch dưới 5%.
- [ ] Đọc `job.py` sau R1: ghi số dòng và danh sách trách nhiệm còn lại vào `CHANGELOG.md`.

## Definition of Done

- [ ] Toàn bộ Automated Tests pass trên CI.
- [ ] Toàn bộ Manual Checks đã thực hiện; kết quả ghi vào `CHANGELOG.md`.
- [ ] Không có thay đổi trong `contracts/`.
- [ ] Open Question về số luồng torch đã chuyển sang spec R2 hoặc backlog.
- [ ] `CHANGELOG.md` và `roadmap.md` đã cập nhật; Phase R1 được đánh dấu hoàn thành.
