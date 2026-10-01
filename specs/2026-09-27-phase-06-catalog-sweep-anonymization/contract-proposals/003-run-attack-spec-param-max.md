# Đề xuất contract 003: `RunAttackSpec` có giá trị lớn nhất của tham số chính

- Người đề xuất: agent frontend, Phase 6, Group 6
- Trạng thái: đã duyệt và áp dụng (người dùng duyệt, 2026-10-01; áp dụng ở nhánh `phase06-reviewer-p003`).

## Vấn đề

- `requirements.md` Phase 6, mục Frontend: tab Kết quả có "tùy chọn trục hoành chuẩn hóa (% dải cho phép) để so sánh các attack khác đơn vị". `validation.md` mục Frontend: "Chuyển trục hoành chuẩn hóa → mọi attack hiển thị trên dải 0–100%". Người dùng chốt ở kế hoạch Group 6: công tắc áp cho biểu đồ của từng attack, chuẩn hóa `x = level / max` như bảng xếp hạng (`requirements.md` mục Decisions).
- Biểu đồ vẽ từ `RunView`, nhưng `RunView.attack_spec` (`RunAttackSpec`, `contracts/python/advertest_contracts/models.py`) chỉ có `name`, `version`, `param_name`, `param_unit`, không có dải của tham số chính. `AttackRankingEntry` cũng không có.
- Nguồn khác mà engineer đọc được là `GET /attack-specs`, nhưng nó chỉ trả spec **đang bật**. Experiment chạy với spec version đã bị tắt (ví dụ `adv_patch` v1 sau khi có v2, đề xuất 001) không còn tra được `max`. `GET /admin/attack-specs` có mọi version nhưng chỉ admin đọc được.

## Thay đổi đề xuất

### `contracts/python/advertest_contracts/models.py`

```diff
 class RunAttackSpec(_Model):
     name: str
     version: PositiveInt
     param_name: str = Field(description="Tên tham số chính (primary_param.name)")
     param_unit: str = Field(description="Đơn vị tham số chính (primary_param.unit)")
+    param_max: PositiveFloat = Field(
+        description="primary_param.max; trục hoành chuẩn hóa level / param_max (Phase 6)"
+    )
```

### Backend

`backend/app/services/experiment_views.py` (`_run_view`): `param_max=spec.primary_param.max`.

### Mock

Mọi mock `run_view/*.json` (43 file) thêm `attack_spec.param_max` theo spec tương ứng (sinh lại bằng script mock như các lần trước).

Không đổi DB, OpenAPI route hay hash (view, không lưu).

## Ảnh hưởng

| Agent / thư mục | Cần thay đổi gì |
|---|---|
| Người duyệt | Sửa model, mock `run_view`, `make contracts`, test contract (`param_max` khớp `primary_param.max` của spec trong mock), CHANGELOG. |
| backend | Một dòng trong `_run_view`, cập nhật test nếu so sánh nguyên `RunView`. |
| frontend (Group 6) | Biểu đồ dùng `attack_spec.param_max` khi bật trục chuẩn hóa. |

- `schema_version`: không tăng; `RunView` là response, trường mới bắt buộc nhưng backend luôn điền được.
- Mock cần cập nhật: `run_view/*`.
- Test nghiệm thu cần cập nhật: không có test hiện tại so sánh nguyên `RunView`; Group 7 có thể kiểm `param_max`.

## Phương án thay thế (không đổi contract)

1. **Tra `max` từ `GET /attack-specs` theo `attack_spec_id`.** Chạy được với spec đang bật (mọi spec hiện có trong seed). Nhược điểm: spec version đã tắt không có trong danh sách; attack đó không chuẩn hóa được. Biểu đồ của nó phải giữ đơn vị gốc kèm ghi chú, trái với validation "mọi attack 0–100%".
2. **Suy `max` từ `coverage` của bảng xếp hạng** (`max = level lớn nhất được tính / coverage`). Nhược điểm: phải lặp lại luật chọn level của `ml_core/metrics/ranking.py` ở frontend; sai số dấu phẩy động; không có khi attack chưa có level nào có kết quả.

## Khuyến nghị

Áp dụng thay đổi đề xuất: một trường view, backend có sẵn dữ liệu, frontend không phải đoán hay gọi thêm API, và luôn đúng với spec version mà run đã dùng.
