# Đề xuất contract 001: ErrorResponse và HealthResponse

- Người đề xuất: agent backend, Phase 00, Group 4
- Trạng thái: chờ duyệt

## Vấn đề

Group 4 dựng khung API. Người duyệt đã chọn **khung tối thiểu**: mỗi nhóm endpoint một endpoint đại diện, model lấy từ các schema đã có trong `contracts/`. Hai hình dạng dữ liệu mà Phase 0 bắt buộc lại chưa có trong contract:

- `plan.md` Phase 0 task 21: mọi endpoint (trừ `/health`) trả `501` với body `{"error": {"code": "not_implemented", "message": ...}}`. Body này cần một schema để khai báo trong OpenAPI và để frontend sinh type.
- `requirements.md` Phase 0, mục Behaviour: `GET /health` trả phiên bản API, git commit và trạng thái kết nối Postgres, MinIO. Cần một schema để khai báo response và để Group 7 dùng cho healthcheck.

Nếu backend tự định nghĩa hai schema này, contract không còn là nguồn sự thật duy nhất (quyết định "Nguồn sự thật của contract là Pydantic" trong `requirements.md` Phase 0).

## Thay đổi đề xuất

`contracts/python/advertest_contracts/enums.py`:

```diff
+class ErrorCode(StrEnum):
+    # Phase 4 thêm: unauthenticated, forbidden, invalid_credentials, account_pending, ...
+    NOT_IMPLEMENTED = "not_implemented"
```

`contracts/python/advertest_contracts/models.py`:

```diff
+# ---------------------------------------------------------------- API chung
+
+
+class ErrorBody(_Model):
+    code: ErrorCode
+    message: str = Field(min_length=1)
+
+
+class ErrorResponse(_Model):
+    """Body lỗi thống nhất của mọi endpoint: {"error": {"code", "message"}}."""
+
+    schema_version: Literal[1] = 1
+    error: ErrorBody
+
+
+class DependencyStatus(_Model):
+    ok: bool
+    detail: str | None = Field(default=None, description="Lý do khi ok = false")
+
+
+class HealthResponse(_Model):
+    schema_version: Literal[1] = 1
+    status: Literal["ok", "degraded"] = Field(description="degraded khi có dependency không ok")
+    version: str = Field(min_length=1)
+    git_commit: str = Field(pattern=r"^([0-9a-f]{40}|unknown)$")
+    postgres: DependencyStatus
+    minio: DependencyStatus
+
+    @model_validator(mode="after")
+    def _status_matches_dependencies(self) -> HealthResponse:
+        all_ok = self.postgres.ok and self.minio.ok
+        if (self.status == "ok") != all_ok:
+            raise ValueError("status = ok khi và chỉ khi mọi dependency ok")
+        return self
```

`contracts/python/advertest_contracts/registry.py`: thêm `"error_response": ErrorResponse`, `"health_response": HealthResponse`.

`contracts/mocks/`: `error_response/not_implemented.json`, `health_response/ok.json`, `health_response/degraded.json`.

`requirements.md` Phase 0: thêm `ErrorCode` (`not_implemented`) vào bảng enum; thêm `ErrorResponse`, `HealthResponse` vào mục "Schema contract"; ghi rõ `GET /health` luôn trả `200`, trạng thái nằm ở trường `status`.

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt, `contracts/` | Thêm enum, 4 model, 3 mock, cập nhật registry; chạy `make contracts` |
| backend, `backend/app/` (Group 4) | Dùng `ErrorResponse` cho handler 501, `HealthResponse` cho `/health` |
| frontend (Group 5) | Có type `ErrorResponse` để xử lý lỗi chung |
| backend, `docker/` (Group 7) | Healthcheck của `api` đọc `status` |
| Phase 4 | Thêm các giá trị còn lại vào `ErrorCode` (đã có trong requirements Phase 4) |

- `schema_version`: không tăng schema nào đang có; hai schema mới bắt đầu từ `1`.
- Mock cần cập nhật: thêm 3 mock mới; mock cũ không đổi.
- Test nghiệm thu cần cập nhật: `test_contracts.py` (Group 10) phải kiểm tập giá trị của `ErrorCode`.

## Phương án thay thế (không đổi contract)

1. **Backend tự định nghĩa hai schema trong `backend/app/schemas/`.** OpenAPI vẫn có chúng và frontend vẫn sinh được type từ `contracts/openapi.json`. Nhược điểm: có hai nguồn định nghĩa định dạng lỗi (backend và Phase 4 spec); test contract không kiểm được; trái quyết định "contract là nguồn sự thật".
2. **Không khai báo model cho 501 và `/health`.** Nhược điểm: OpenAPI không mô tả được body lỗi và health; frontend phải đoán; vi phạm yêu cầu OpenAPI đầy đủ response model.

## Khuyến nghị

Chấp nhận đề xuất. Hai schema nhỏ, hình dạng đã được `plan.md` Phase 0 và `requirements.md` Phase 4 chốt, và giữ contract là nguồn sự thật duy nhất.
