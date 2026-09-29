# Đề xuất contract 001: `RunView.fingerprint` null cho run chưa bắt đầu

- Người đề xuất: agent backend, Phase 5, Group 2
- Trạng thái: đã duyệt (người dùng, 2026-09-30); áp dụng bằng lớp cơ sở chung `_RunCommon` cho `RunResult` và `RunView` (mypy không cho lớp con đổi kiểu trường), không dùng `# type: ignore`

## Vấn đề
- `RunView` (`contracts/python/advertest_contracts/models.py`, mục Phase 5) kế thừa `RunResult`, nơi `fingerprint: Sha256Hex` là bắt buộc.
- Fingerprint do worker tính và gửi ở `POST /internal/worker/runs/{id}/start` (requirements.md Phase 3; cột `runs.fingerprint` "null trước đó"). Các run chưa từng bắt đầu không có fingerprint:
  - `queued` (mọi run của experiment mới tạo);
  - `cancelled` khi experiment bị hủy trước khi run chạy;
  - `stopped_limit` khi chạm trần thời gian trước khi run bắt đầu (`runs._after_run`, `images_done = 0`).
- Hệ quả: `GET /experiments/{id}/runs` và `GET /runs/{id}` (requirements.md Phase 5, bảng API experiment) không trả được các run này. Bảng run ở tab Tổng quan cần hiển thị đủ run và trạng thái (mission.md nguyên tắc 6).

## Thay đổi đề xuất
```diff
 class RunView(RunResult):
+    """Run hiển thị cho người dùng. `fingerprint` null khi và chỉ khi run chưa bắt đầu (worker
+    tính fingerprint ở `start`)."""
+
+    fingerprint: Sha256Hex | None = Field(
+        description="null khi run chưa bắt đầu (queued, hoặc bị hủy/dừng trước khi chạy)"
+    )
     attack_spec: RunAttackSpec
+
+    @model_validator(mode="after")
+    def _check_not_started(self) -> RunView:
+        if self.fingerprint is None and (
+            self.status not in (RunStatus.QUEUED, RunStatus.CANCELLED, RunStatus.STOPPED_LIMIT)
+            or self.progress.images_done != 0
+            or self.metrics is not None
+            or self.manifest_uri is not None
+            or self.failure_case_ids
+        ):
+            raise ValueError(
+                "fingerprint chỉ null khi run chưa bắt đầu (queued/cancelled/stopped_limit,"
+                " chưa xử lý ảnh nào, không có metric, manifest, failure case)"
+            )
+        return self
```
(Ghi chú: ghi đè kiểu trường trong lớp con là hợp lệ với Pydantic v2; nếu mypy báo lỗi ghi đè thì tách `RunView` thành model riêng có cùng trường thay vì kế thừa, không dùng `# type: ignore`.)

- `RunResult` (worker gửi ở `complete`) **giữ nguyên**: fingerprint vẫn bắt buộc.
- Mock `run_view`: `running_pgd_4_queued.json` và `completed_pgd_l2_1_not_started.json` đổi `fingerprint` thành `null`. Thêm test contract: fingerprint null được chấp nhận cho run chưa bắt đầu, bị từ chối cho `completed`/`running`/run có `images_done > 0`.
- `make contracts` (JSON Schema `run_view.json`, `api.ts`, `schemas.ts`).

## Ảnh hưởng
| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt (`contracts/`) | Sửa `RunView`, 2 mock, thêm test; `make contracts` |
| backend (Group 2) | `GET /experiments/{id}/runs`, `GET /runs/{id}` dựng `RunView` cả khi `runs.fingerprint` null |
| frontend (Group 4, 6) | Tab Tái lập: run chưa bắt đầu không có fingerprint, hiển thị "Chưa chạy"; type sinh lại tự báo lỗi `tsc` nếu code giả định chuỗi |
| worker | Không đổi |

- `schema_version`: không tăng. `RunView` mới thêm ở Phase 5, chưa có dữ liệu lưu trữ hay client nào dùng; thay đổi chỉ nới trường cho một trường hợp đã có trong thực tế.
- Test nghiệm thu cần cập nhật: không (chưa có test Phase 5).

## Phương án thay thế (không đổi contract)
1. **Chỉ trả run đã bắt đầu** trong `GET /experiments/{id}/runs`. Nhược điểm: experiment mới tạo có danh sách run rỗng; run bị hủy hoặc dừng trước khi chạy biến mất khỏi giao diện, vi phạm mission.md nguyên tắc 6 (trạng thái luôn rõ, không ẩn run nào).
2. **API tự tính fingerprint trước khi worker start.** Nhược điểm: fingerprint gồm git commit, phiên bản thư viện và digest Docker của **worker**; API không biết giá trị đó, và worker có thể khác phiên bản API. Giá trị API tính có thể khác giá trị thật, làm sai tái lập (nguyên tắc 4).

## Khuyến nghị
Áp dụng thay đổi đề xuất: phản ánh đúng thực tế (run chưa chạy thì chưa có fingerprint), giữ nguyên `RunResult` của worker, ràng buộc chặt để null không lọt vào run đã chạy.
