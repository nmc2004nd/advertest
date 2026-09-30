# Đề xuất contract 001: batch size cố định khi train patch

- Người đề xuất: agent attack-patch, Phase 6, Group 2
- Trạng thái: chờ duyệt

## Vấn đề

Review Group 2 (phát hiện #1, người dùng chọn "cố định batch size khi train"): patch train ra phụ thuộc batch size.

- `ultralytics/utils/loss.py:486`: `v8DetectionLoss` trả `loss * batch_size`, trong đó loss được chuẩn hóa theo tổng `target_scores` của **cả batch**. Gradient của mỗi ảnh vì vậy đổi theo cách chia batch, và `RobustDPatch` cộng gradient các batch rồi lấy dấu, nên cách chia batch đổi patch.
- `attacks/patch/training.py` (`PatchTrainer(batch_size=…)`) hiện nhận batch size từ nơi gọi; theo `tech-stack.md` mục 4.2, batch size lấy từ cost profile **riêng cho từng compute target**.
- Khóa patch (`compute_patch_key`: `spec_sha256`, `weights_sha256`, `training_slice_sha256`, `area_ratio`, `seed`) và `FingerprintInputs.patch_key` không chứa batch size hay `patch_sha256`. Cùng một khóa train trên hai máy có cost profile khác nhau cho hai patch khác nhau, mà fingerprint của run đánh giá vẫn trùng. Điều này đi ngược `mission.md` nguyên tắc 4 (tái lập) và `requirements.md` mục Patch attack ("Mỗi khóa chỉ train một lần").

## Thay đổi đề xuất

### `contracts/python/advertest_contracts/models.py`

```diff
 class TrainingParams(_Model):
     """Tham số huấn luyện của spec cần train trước khi đánh giá (patch, Phase 6)."""

     max_iter: PositiveInt = Field(
         description="Số vòng lặp; mỗi vòng đi qua toàn bộ slice huấn luyện"
     )
     learning_rate: PositiveFloat = Field(description="Trong thang ảnh [0, 1]")
     sample_size: PositiveInt = Field(description="Số biến đổi ngẫu nhiên mỗi ảnh mỗi vòng (EOT)")
     checkpoint_every: PositiveInt = Field(description="Lưu checkpoint sau mỗi số vòng lặp này")
     max_training_images: PositiveInt = Field(description="Kích thước tối đa của slice huấn luyện")
+    batch_size: PositiveInt = Field(
+        description="Batch size khi train và khi tính giá trị mục tiêu; cố định trong spec (không"
+        " lấy từ cost profile) vì patch phụ thuộc cách chia batch"
+    )
```

Trường bắt buộc (không có giá trị mặc định): `TrainingParams` mới có từ Phase 6, dữ liệu duy nhất đang dùng là seed `adv_patch`.

### `contracts/seeds/attack_specs.json`

```diff
   {
-    "id": "<content_id cũ>",
+    "id": "<content_id(spec_sha256 mới)>",
     "name": "adv_patch",
-    "version": 1,
+    "version": 2,
     ...
     "training": {
       "max_iter": 200,
       "learning_rate": 0.02,
       "sample_size": 1,
       "checkpoint_every": 50,
-      "max_training_images": 50
+      "max_training_images": 50,
+      "batch_size": 8
     },
-    "spec_sha256": "a515b489…"
+    "spec_sha256": "<tính lại>"
   }
```

- **Version 2 thay thế version 1** trong file seed (theo luật "đổi bất kỳ trường nào phải tăng `version`"). Không giữ version 1: version 1 chưa có run nào, và nếu giữ thì wizard liệt kê hai spec `adv_patch` cùng hoạt động. DB dev đã seed version 1 trước khi đề xuất này được áp dụng vẫn còn dòng version 1 (`is_active = true`); người duyệt tắt tay hoặc dựng lại DB. DB của test và CI dựng mới nên không bị ảnh hưởng.
- **`batch_size = 8`:** slice huấn luyện tối đa 50 ảnh nên có 7 batch mỗi vòng. Gradient của YOLOv8n ở 640×640 với batch 8 vừa bộ nhớ GPU laptop 4 GB theo ước tính (cần xác nhận ở manual check trên GPU); trên CPU không giới hạn.

Không đổi OpenAPI, migration hay schema DB.

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt (Group 0 bổ sung) | `models.py` (`TrainingParams.batch_size`), seed `adv_patch` version 2, `make contracts`; sinh lại các mock có spec `adv_patch` (16 file: `experiment_detail/full_catalog`, `patch_training`, `run_view/catalog_adv_patch_*`, `patch_training_*`, `patch_evaluating_running`, `patch_artifact`, `patch_registration`, `manifest/patch_run`, `worker_job_bundle/patch_resume_early_stop`, `estimate_response/patch_training`, `cost_profile/cpu_adv_patch`, `attack_spec/adv_patch`, `attack_spec_admin_*`, `attack_config/patch_no_early_stop`, `experiment_create/full_catalog`) vì `spec_sha256`, `id` và khóa patch đổi; `contracts/python/tests/test_seeds.py` kiểm tra `batch_size`. `CHANGELOG.md`. |
| attack-patch (`attacks/patch/`) | `PatchTrainer` bỏ tham số `batch_size`, dùng `spec.training.batch_size` cho `RobustDPatch` và cho giá trị mục tiêu; `measure_sec_per_image_iteration` tương tự; test cập nhật (spec giả trong test đổi `batch_size` thay vì truyền tham số). |
| ml-core, worker (Group 3) | Khi train patch không truyền batch size từ cost profile; chỉ giai đoạn đánh giá dùng batch size của cost profile. |
| backend (Group 5) | Không đổi (calibration đo `sec_per_image_iteration` bằng hàm của attack-patch). |
| frontend (Group 6) | Không đổi logic; type sinh lại có thêm `batch_size` (trang `/admin/attacks` hiển thị trong tham số cố định nếu muốn). |
| Người duyệt (Group 7) | `scripts/e2e.sh` nạp `adv_patch` với `max_iter = 4` (task 36a) phải kèm `batch_size`. |

- `schema_version`: **không tăng**. `AttackSpec.schema_version = 1` mô tả cấu trúc chung của spec; `TrainingParams` mới thêm trong Phase 6 và chưa có dữ liệu nào khác ngoài seed, nên thêm trường bắt buộc không làm hỏng dữ liệu đã lưu.
- Hash cũ: `spec_sha256` của `fgsm`, `pgd_linf`, `pgd_l2` và 5 corruption, occlusion không đổi (chỉ `adv_patch` đổi).
- Test nghiệm thu cần cập nhật: không có (Phase 6 chưa có test nghiệm thu; `tests/acceptance/phase_00` validate seed tự động).

## Phương án thay thế (không đổi contract)

1. **Chấp nhận phụ thuộc, ghi vào spec.** Patch đã đăng ký được lưu trong MinIO và dùng lại theo khóa, nên kết quả đánh giá vẫn tái lập khi patch còn. Nhược điểm: nếu patch mất (xóa bucket, dựng lại môi trường) thì train lại trên máy khác cho patch khác mà fingerprint không đổi; phải thêm luật "patch đã đăng ký không được xóa" vào `tech-stack.md` mục 4.4.
2. **Cố định batch size bằng hằng số trong `attacks/patch/`** (không đưa vào spec). Nhược điểm: đổi hằng số là đổi patch mà `spec_sha256` và khóa patch không đổi, nên lỗi tái lập quay lại một cách khó thấy; tham số ảnh hưởng tới kết quả phải nằm trong spec đã hash.

## Khuyến nghị

Áp dụng thay đổi đề xuất: `batch_size` thuộc spec nên đi vào `spec_sha256`, khóa patch và fingerprint; patch tái lập được giữa các máy, đúng lựa chọn của người dùng ở review Group 2. Chi phí là sinh lại mock và một lần tăng version của `adv_patch` khi chưa có run nào dùng spec này.
