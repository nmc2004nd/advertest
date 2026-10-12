# Đề xuất contract 002: xóa / lưu trữ model, tạo class mapping qua web

- Người đề xuất: agent frontend + backend, Phase R3 (yêu cầu của người dùng 2026-10-12)
- Trạng thái: đã duyệt (2026-10-12)

## Vấn đề

- Model đăng ký qua web không gỡ được: `/models` chỉ có `GET`/`POST`, `/models/{id}` chỉ `GET`.
- Class mapping chỉ tạo được bằng admin CLI (`import-local`, `backend/app/services/registry.py`);
  `GET /class-mappings` là API duy nhất. Model tải lên qua web vì thế không có mapping và không
  dùng được trong wizard (wizard cần `class_mapping_id`).
- `mission.md` nguyên tắc 3: run và report phải truy vết được, nên model đã có experiment không
  được xóa cứng.

## Thay đổi

`contracts/python/advertest_contracts/models.py`:

- `ModelSummary.archived_at: UtcDatetime | None = None`.
- `ModelSummary.owner_id: UUID | None`, `owner_name: str | None` (bổ sung 2026-10-12): giao diện chỉ hiện nút xóa, lưu trữ, kiểm lại, thêm mapping cho người đăng ký model hoặc admin; người khác thấy dòng "Model do … đăng ký".
- Mới `ClassMappingCreate { dataset_version_id, model_version_id, classes, difficulty }`; ít nhất
  một class gốc phải map sang class của model. `preset` không gửi lên: backend suy ra khi nội dung
  trùng preset của `ml_core.data.mapping.PRESETS`.

Endpoint (permission `model.manage`, luật sở hữu ở service: người đăng ký model hoặc admin):

| Endpoint | Kết quả |
|---|---|
| `DELETE /models/{model_id}` | 204. 409 khi model có experiment hoặc lượt thử nhanh (dùng lưu trữ), hoặc đang `checking`. Xóa cả class mapping, cost profile, weights trên MinIO; xóa `models` khi không còn version |
| `POST /models/{model_id}/archive` | `ModelSummary` có `archived_at`; 409 khi đã lưu trữ |
| `POST /models/{model_id}/restore` | `ModelSummary`, `archived_at = null`; 409 khi chưa lưu trữ |
| `POST /class-mappings` | 201 `ClassMappingSummary`; 422 khi class không thuộc dataset/model; 409 khi trùng hash hoặc model đã lưu trữ |

Model lưu trữ: experiment mới (`experiment_config`) và thử nhanh từ chối như model chưa `ready`.

DB: migration `0014` thêm `model_versions.archived_at` (nullable). Không đổi quyền: các bảng bị xóa
(`models`, `model_versions`, `class_mappings`, `cost_profiles`) đã có `DELETE` cho `advertest_app`
từ migration 0001; `tool_jobs`, `quick_tries` vẫn không xóa (model có lượt thử nhanh chỉ lưu trữ).

## Ảnh hưởng

| Thư mục | Thay đổi |
|---|---|
| contracts | Model ở trên, registry `class_mapping_create`, mock `model_summary/old_archived`, `class_mapping_create/kitti_custom` |
| backend | Migration 0014, `services/model_admin.py`, endpoint, kiểm tra model lưu trữ ở `experiment_config` và `quick_tries` |
| frontend | Bước class mapping trong form đăng ký model (gợi ý theo preset kitti-coco hoặc trùng tên), mục Class mapping và nút Xóa / Lưu trữ / Khôi phục ở trang chi tiết model, lọc model lưu trữ khỏi wizard và thử nhanh |

- `schema_version`: không tăng (trường thêm là tùy chọn).

## Phương án thay thế

Chỉ lưu trữ, không xóa cứng: an toàn hơn nhưng weights rác nằm mãi trên MinIO. Người dùng chọn
"xóa nếu chưa dùng, lưu trữ nếu đã dùng".

## Bổ sung 2026-10-12: phạm vi thấy model

Không đổi schema. Admin, reviewer thấy mọi model; engineer thấy model mình đăng ký và model của người có vai trò admin (`catalog.model_visibility`). `GET /models` lọc theo người gọi; `GET /models/{id}` không thấy được → 404; `experiment_config.check` (tạo, ước lượng) và `quick_tries.create` coi model không thấy được là không tồn tại (422).
