# Đề xuất contract 001: worker đọc prediction của run đã kết thúc

- Người đề xuất: agent worker, Phase 7, Group 3
- Trạng thái: đã duyệt và áp dụng (người duyệt, 2026-10-01; người dùng đã chọn hướng này ở kế hoạch Group 3)

## Vấn đề

Bootstrap của tự tìm ngưỡng (`requirements.md` Phase 7, mục "Khoảng tin cậy bootstrap") tính trên prediction theo ảnh của **mọi** điểm toàn slice (`RunResult.predictions_key`). Worker không đọc được prediction của:

1. **Run đã kết thúc ở phiên trước**: chạy tiếp sau gián đoạn, các điểm toàn slice đã xong trước đó không còn trong bộ nhớ. `POST /internal/worker/runs/{id}/artifact-url` chỉ cấp URL cho run đang `running` (`backend/app/services/runs.py::artifact_url`, Phase 3 `requirements.md` mục API nội bộ); run đã xong trả `409`, và client của worker coi mọi `409` là mất lease nên dừng cả experiment.
2. **Run trúng cache** (`skipped`, `cached`): prediction nằm ở `runs/<run gốc>/predictions.json`, ngoài thư mục `runs/<run_id>/` mà `artifact-url` cho phép; `BundleRun` không có `cached_from_run_id`, nên worker chạy tiếp cũng không biết run gốc.

Nếu bỏ các điểm này khỏi bootstrap, khoảng tin cậy phụ thuộc vào việc có gián đoạn hay không và điểm nào trúng cache (trái `mission.md` nguyên tắc 4).

## Thay đổi đề xuất

Không đổi kiểu dữ liệu, không đổi route; đổi mô tả trong contract và hành vi của API.

`contracts/python/advertest_contracts/models.py`:

```diff
 class ArtifactUrlRequest(_Model):
     lease_id: UUID
     key: ObjectKey = Field(
-        description="Khóa đầy đủ, phải nằm trong runs/<run_id>/, hoặc trong patches/<patch_key>/"
-        " với patch_key của run (Phase 6)"
+        description="Khóa đầy đủ, phải nằm trong runs/<run_id>/, hoặc trong patches/<patch_key>/"
+        " với patch_key của run (Phase 6). Run phải đang running, trừ GET"
+        " runs/<run_id>/predictions.json của run đã kết thúc thuộc experiment đang lease"
+        " (Phase 7, bootstrap)"
     )
```

```diff
 class _RunCommon(_Model):
     predictions_key: ObjectKey | None = Field(
         ...
-        description="Phase 7: khóa file prediction theo ảnh trong runs/<run_id>/ (bootstrap);"
-        " null khi chưa có metric hoặc run trước Phase 7",
+        description="Phase 7: khóa file prediction theo ảnh trong runs/<run_id>/ (bootstrap);"
+        " run trúng cache có bản sao của file của run gốc; null khi chưa có metric, run trước"
+        " Phase 7, hoặc run gốc không có file",
     )
```

Hành vi API (Group 4, ghi vào `requirements.md` Phase 7 mục API):

- `artifact-url`: run không `running` → chỉ chấp nhận `method = GET` và `key = runs/<run_id>/predictions.json`, với run thuộc experiment đang lease và lease đúng; mọi yêu cầu khác với run đã kết thúc giữ nguyên `409` như Phase 3. File không tồn tại: vẫn cấp URL (GET trả 404 từ MinIO, worker coi như điểm không có prediction).
- `start` trả `skip_cached`: nếu run gốc có `predictions_key`, API sao chép đối tượng sang `runs/<run_id>/predictions.json` (copy phía server trong MinIO) và ghi `predictions_key` của run mới bằng khóa đó. Prediction không chứa ảnh nên không liên quan làm mờ.

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt `contracts/` | Hai mô tả trên; `make contracts` (OpenAPI, type TypeScript đổi mô tả) |
| backend (Group 4) | `artifact_url` cho GET prediction của run đã kết thúc; `start` sao chép file khi `skip_cached`; test |
| worker (Group 3) | Đọc `runs/<run_id>/predictions.json` qua `artifact-url` của chính run đó cho mọi điểm toàn slice không có trong bộ nhớ; 404 → điểm bị bỏ khỏi bootstrap |
| frontend | Không |

- `schema_version`: không tăng (không đổi kiểu, chỉ mô tả và hành vi).
- Mock cần cập nhật: không.
- Test nghiệm thu cần cập nhật: Phase 3 nếu có test "run đã kết thúc không xin được URL" cho GET `predictions.json` (vẫn đúng với mọi khóa khác). Group 7 Phase 7 thêm test chạy tiếp sau gián đoạn và điểm trúng cache có trong bootstrap.

## Phương án thay thế (không đổi contract)

1. **Chỉ dùng prediction trong bộ nhớ của phiên**: điểm chạy ở phiên trước hoặc trúng cache bị bỏ khỏi bootstrap. Nhược điểm: khoảng tin cậy và `near_threshold` thay đổi theo việc có gián đoạn hay không; điểm cuối khoảng trùng run quét lưới (thường gặp khi dịch khoảng qua level thô) không có `drop_ci`.
2. **Worker chạy lại điểm trúng cache khi cần bootstrap**: tốn GPU, trái "Không tốn thêm GPU" của spec; vẫn không giải quyết điểm của phiên trước.

## Khuyến nghị

Áp dụng thay đổi đề xuất: không đổi kiểu dữ liệu, giữ tính bất biến (chỉ GET), và khoảng tin cậy tái lập được bất kể gián đoạn hay cache.
