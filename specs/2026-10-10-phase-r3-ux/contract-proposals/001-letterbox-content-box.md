# Đề xuất contract 001: vùng ảnh thật trong letterbox (`content_box`) cho failure case và Thử nhanh

- Người đề xuất: agent frontend, Phase R3 (ngoài group; phát hiện khi dùng thử CaseViewer)
- Trạng thái: đã duyệt (2026-10-12)

## Vấn đề

Ảnh KITTI cỡ khoảng 1242×375 (tỉ lệ ~3.3:1). Sau letterbox 640×640 (`ml_core/preprocess/letterbox.py`, pad căn giữa bằng 114/255) phần ảnh thật chỉ là một dải cao ~193 px, khoảng 70% khung còn lại là viền xám.

`frontend/src/components/case-viewer/CaseViewer.tsx` (`Frame`) hiển thị cả khung vuông (`aspect-square`, `object-contain`), nên trên mọi màn hình dùng CaseViewer (FailureCasePage, ReviewCasePage, tab experiment, QuickTryPage) ảnh và box đều bé, khó nhìn. Khi review case, box nhỏ cỡ vài px càng khó thấy.

Frontend không cắt được viền vì không biết vùng ảnh thật nằm ở đâu:
- `CaseDetections` / `FailureCaseRecord` / `FailureCaseView` chỉ có box xyxy trong không gian letterbox.
- `QuickTryView` chỉ có URL ảnh và `QuickTryObject.bbox`.
- `LetterboxInfo` (`scale`, `pad`, `orig_size`) đã được tính ở `ml_core` (executor: `batch.infos`; worker quick try: `letterbox(source, ...)` trả `info`) nhưng không được đưa vào contract nào.

## Thay đổi đề xuất

Thêm **một trường tùy chọn** `content_box`: xyxy pixel trong không gian letterbox của vùng ảnh thật, tức `[pad_left, pad_top, pad_left + new_w, pad_top + new_h]`. Box vẫn ở không gian letterbox (tech-stack.md mục 2.1 không đổi); frontend chỉ đổi phép chiếu khi vẽ.

`contracts/python/advertest_contracts/models.py`:

```diff
+_CONTENT_BOX = (
+    "Vùng ảnh thật trong ảnh letterbox (xyxy pixel, không gian letterbox), phần còn lại là pad"
+    " 114. null với dữ liệu tạo trước Phase R3: giao diện hiển thị cả khung vuông"
+)
+
+
 class CaseDetections(_Model):
     ground_truth: list[CaseBox]
     clean: list[CaseBox]
     attacked: list[CaseBox]
     ignore_regions: list[CaseIgnoreRegion]
+    content_box: PixelBBox | None = Field(default=None, description=_CONTENT_BOX)
```

Đặt trong `CaseDetections` vì cột `failure_cases.detections` đã là JSONB (`backend/app/db/models.py:496`), nên **không cần migration**. `FailureCaseRecord`, `FailureCaseView` và payload của worker nhận trường này tự động.

```diff
 class QuickTryLevelReport(_Model):
     level: float
     objects: list[QuickTryObject]

 class QuickTryReport(_Model):
     kind: Literal[ToolJobKind.QUICK_TRY] = ToolJobKind.QUICK_TRY
     levels: list[QuickTryLevelReport] = Field(min_length=1)
+    content_box: PixelBBox | None = Field(default=None, description=_CONTENT_BOX)

 class QuickTryView(_Model):
     ...
     clean_image_url: ArtifactUrl | None = ...
+    content_box: PixelBBox | None = Field(
+        default=None, description=_CONTENT_BOX + "; chỉ có khi completed"
+    )
     levels: list[QuickTryLevel] = ...
```

Validator `QuickTryView._check`: thêm luật `content_box` không null thì `status = completed`. Quick try lưu kết quả ở đâu (bảng `quick_tries`, cột JSONB hay cột riêng) thì backend xác minh trước khi duyệt. Nếu là cột riêng thì cần một migration nhỏ (thêm cột nullable).

Sau đó chạy `make contracts` để sinh lại `contracts/schemas`, `contracts/openapi.json`, `frontend/src/contracts`.

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| contracts (người duyệt) | Diff ở trên, `make contracts`, mock `contracts/mocks` có failure case / quick try thêm `content_box` |
| ml-core (`ml_core/runner/executor.py`) | Lưu `info` của ảnh vào `case_inputs` rồi điền `content_box` khi tạo `CaseDetections` trong `_record`; thêm helper `content_box(info)` ở `ml_core/preprocess/letterbox.py` |
| worker (`backend/worker/advertest_worker/quick_try.py`) | Điền `content_box` từ `info` vào `QuickTryReport` |
| backend (`backend/app/services`, quick try) | Lưu/trả `content_box` của quick try; failure case không cần đổi (JSONB đi thẳng) |
| frontend (`components/case-viewer`) | `Frame` dùng `aspect-ratio` theo `content_box`; ảnh hiển thị bằng `object-view-box`/crop qua `transform`; `toCss`/`hitTest` trừ `pad` và scale theo chiều rộng vùng thật; `content_box` null thì giữ hành vi cũ. Thumbnail trong danh sách case cũng có thể crop theo cùng box (tỉ lệ 320/640) |

- `schema_version`: **không tăng**. Trường thêm vào là tùy chọn, mặc định `null`; record cũ vẫn hợp lệ, consumer cũ bỏ qua được.
- Fingerprint/golden: `content_box` không thuộc fingerprint của run (`ml_core/runner/fingerprint.py` chỉ dùng `LETTERBOX_CONFIG`). Không có golden JSON nào chứa `detections`, nhưng cần chạy lại golden R1 (`--extra cpu`) để xác nhận.
- Mock cần cập nhật: các mock failure case và quick try trong `contracts/mocks` (thêm một case có `content_box`, giữ một case `null` để kiểm tra nhánh cũ).
- Test nghiệm thu cần cập nhật: không bắt buộc. Có thể thêm vào `tests/acceptance/phase_r3`: (1) case mới có `content_box` khớp `letterbox_info(orig_w, orig_h)`; (2) E2E CaseViewer với ảnh KITTI có khung khác vuông.
- Dữ liệu cũ: case đã tạo trước thay đổi có `content_box = null` và vẫn hiển thị khung vuông. Có thể backfill bằng script đọc kích thước ảnh gốc của `image_id` trong slice rồi gọi `letterbox_info`, nhưng việc này không bắt buộc.

## Phương án thay thế (không đổi contract)

**A. Frontend tự dò viền:** sau khi `<img>` tải xong, vẽ lên canvas ẩn rồi quét các hàng/cột mép có toàn pixel (114, 114, 114) để suy ra vùng ảnh thật.
- Nhược điểm: `getImageData` cần ảnh cùng origin hoặc có CORS (ảnh MinIO presigned có thể khác origin, làm canvas bị "tainted"). Ảnh thật có mép trùng màu 114 (đường, trời xám) thì bị cắt lố. Ảnh bị ẩn (`hidden_unanonymized`) không có ảnh để dò, nhưng box vẫn phải vẽ. Mỗi lần mở case tốn thêm CPU.

**B. Suy từ box:** lấy hộp bao của mọi box và ignore region rồi nới thêm lề.
- Nhược điểm: không phản ánh đúng ảnh, case ít box thì cắt mất nội dung. Không dùng được.

**C. Chỉ cho phóng to mặc định:** đặt zoom ban đầu của `react-zoom-pan-pinch` khoảng 2× ở giữa ảnh.
- Nhược điểm: không biết tỉ lệ ảnh nên ảnh dọc hoặc vuông sẽ bị cắt mất; vẫn tốn khung.

## Khuyến nghị

Chọn **thay đổi contract**. Trường thêm vào là tùy chọn, không tăng `schema_version`, không cần migration cho failure case. Dữ liệu này máy đã tính sẵn (`LetterboxInfo`), chỉ cần đưa qua contract. Phương án A làm được ngay nhưng phụ thuộc CORS và có thể cắt sai, nên chỉ hợp làm tạm.
