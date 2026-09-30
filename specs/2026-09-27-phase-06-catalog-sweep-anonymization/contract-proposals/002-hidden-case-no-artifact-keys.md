# Đề xuất contract 002: failure case bị ẩn không trả khóa MinIO

- Người đề xuất: agent backend, Phase 6, Group 5
- Trạng thái: chờ duyệt

## Vấn đề

- `validation.md` Phase 6, mục Làm mờ (bổ sung lúc kickoff): "`FailureCaseView` có `display_mode = hidden_unanonymized` không chứa khóa MinIO". `requirements.md` mục Context (Phase 5) cũng ghi `FailureCaseView` phải bỏ khóa MinIO khi ảnh bị ẩn.
- Nhưng `FailureCaseView` kế thừa `FailureCaseRecord.artifacts: CaseArtifacts`, và `CaseArtifacts.clean_png`, `adversarial_png`, `perturbation_png` là chuỗi bắt buộc, không rỗng (`contracts/python/advertest_contracts/models.py`, lớp `CaseArtifacts`). Backend không thể trả view hợp lệ mà không có khóa.
- Khóa MinIO một mình không cho đọc ảnh (cần token ký ở `/artifacts/<token>`), nhưng lộ bố cục lưu trữ và `run_id` của case bị ẩn; validation yêu cầu không trả.

## Thay đổi đề xuất

### `contracts/python/advertest_contracts/models.py`

```diff
 class FailureCaseView(FailureCaseRecord):
+    artifacts: CaseArtifacts | None = Field(  # type: ignore[assignment]  (thu hẹp lại ở validator)
+        description="Khóa lưu trữ của ảnh; null khi và chỉ khi display_mode = hidden_unanonymized"
+        " (không lộ khóa MinIO của ảnh bị ẩn, Phase 6)"
+    )
     urls: FailureCaseUrls
     urls_expire_at: UtcDatetime | None = Field(
         description="null khi display_mode = hidden_unanonymized"
     )
     display_mode: DisplayMode

     @model_validator(mode="after")
     def _check_display(self) -> FailureCaseView:
         hidden = self.display_mode == DisplayMode.HIDDEN_UNANONYMIZED
+        if hidden != (self.artifacts is None):
+            raise ValueError("artifacts là null khi và chỉ khi display_mode = hidden_unanonymized")
         ...
```

Cách viết cụ thể (có cần chú thích cho mypy khi thu hẹp kiểu ở lớp con hay tách lớp chung) do người duyệt chọn khi áp dụng; ràng buộc chỉ là: view bị ẩn thì `artifacts = null`, view khác thì bắt buộc có.

### Mock

- `contracts/mocks/failure_case_view/hidden_unanonymized.json`: `artifacts: null`.
- Các mock view khác giữ nguyên.

Không đổi OpenAPI route, DB hay `FailureCaseRecord` (worker vẫn gửi đủ khóa; DB vẫn lưu).

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt (Group 0 bổ sung) | Sửa model, mock, `make contracts`; test contract cho luật mới; CHANGELOG. |
| backend (Group 5) | `artifacts._view` trả `artifacts = None` khi `hidden_unanonymized`. |
| frontend (Group 6) | Type `FailureCaseView.artifacts` thành nullable; giao diện hiện không đọc `artifacts` (chỉ dùng `urls`), nên không cần sửa logic. |
| Người duyệt (Group 7) | Test nghiệm thu mục "không chứa khóa MinIO" kiểm `artifacts is None`. |

- `schema_version`: không tăng; chỉ nới một trường của view (response) cho trường hợp ẩn, dữ liệu lưu không đổi.
- Test nghiệm thu hiện có cần cập nhật: kiểm lại Phase 5 (`tests/acceptance/phase_05/`) nếu có test đọc `artifacts` của case bị ẩn.

## Phương án thay thế (không đổi contract)

1. **Giá trị giữ chỗ:** trả `"hidden"` cho mọi khóa khi ảnh bị ẩn. Nhược điểm: dữ liệu giả hợp lệ theo schema, dễ bị hiểu nhầm là khóa thật về sau (ví dụ report Phase 8 đọc nhầm).
2. **Bỏ mục validation:** giữ như Phase 5 (khóa trả về nhưng không có token nên không đọc được ảnh). Nhược điểm: đi ngược ghi chú ở Context và mục validation đã chốt lúc kickoff; lộ bố cục lưu trữ.

## Khuyến nghị

Áp dụng thay đổi đề xuất: đúng nghĩa (không có khóa thì là null), luật "null khi và chỉ khi bị ẩn" được schema kiểm tra, không ảnh hưởng dữ liệu lưu và frontend hiện tại.
