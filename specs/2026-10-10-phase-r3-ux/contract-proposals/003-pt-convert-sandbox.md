# Đề xuất contract 003: chuyển `.pt` sang `.safetensors` trên server, trong sandbox

- Người đề xuất: agent backend + worker + frontend, Phase R3 (yêu cầu của người dùng 2026-10-12)
- Trạng thái: đã duyệt (2026-10-12), kể cả sửa `mission.md` nguyên tắc 10

## Vấn đề

Người chỉ dùng web và có weights `.pt` (Ultralytics hoặc torchvision) không đăng ký được model:
web chỉ nhận `.onnx`/`.safetensors`, còn lệnh `advertest model export-safetensors` cần cài repo.
`mission.md` nguyên tắc 10 cấm nạp `.pt` từ upload web, vì mở pickle là chạy code tùy ý.

## Sửa `mission.md` nguyên tắc 10

```diff
-10. **Không nạp code từ web.** Không nạp file chạy được code (pickle, `.pt`) từ upload qua web. Web chỉ nhận weights dạng ONNX hoặc safetensors; `.pt` chỉ đăng ký qua CLI sau khi có review. Thuật toán attack mới chỉ thêm qua repo và review, không upload qua web.
+10. **Không nạp code từ web ngoài sandbox.** File chạy được code (pickle, `.pt`) upload qua web không bao giờ được mở trong API, worker chạy experiment hay worker công cụ. Nó chỉ được mở trong sandbox chuyển đổi (container riêng: không mạng ra ngoài, không bí mật, không truy cập DB hay MinIO, giới hạn CPU, RAM, thời gian), và sandbox chỉ trả về `.safetensors` cùng metadata; model đăng ký từ kết quả này vẫn qua `model_check` như mọi model web. Thuật toán attack mới chỉ thêm qua repo và review, không upload qua web.
```

## Thiết kế (đã làm)

```
trình duyệt ──PUT .pt──▶ MinIO uploads/<id>/x.pt
API: POST /models/conversions ─▶ tool_job `model_convert` (payload chỉ có presigned URL)
worker-tools: tải .pt ─▶ ghi <spool>/<job>/input.pt + request.json (volume convert_spool)
converter (network_mode: none): tiến trình con nạp .pt ─▶ output.safetensors + status.json
worker-tools: đọc metadata từ header JSON ─▶ PUT uploads/<id2>/x.safetensors ─▶ report
API: xóa .pt gốc; form tự điền, đăng ký bằng result_upload_id, vẫn qua model_check
```

- `worker-tools` chạy `network_mode: host` nên không có mạng nội bộ riêng với converter; thay vào
  đó converter **không có mạng nào** và chỉ trao đổi file qua volume `convert_spool`
  (`backend/worker/advertest_worker/converter.py`).
- Container converter: `read_only`, `tmpfs /tmp`, `cap_drop: [ALL]`, `no-new-privileges`,
  `pids_limit 128`, `mem_limit 4g`, `cpus 2`, không `env_file`. Mỗi file chạy trong tiến trình con
  với môi trường tối thiểu, timeout 120 s, rlimit CPU 180 s, file ≤ 1 GB, không core dump.
- torchvision: `torch.load(weights_only=True)` (pickle chứa lệnh bị từ chối, có test). Ultralytics:
  nạp đầy đủ bằng `export_safetensors` của `ml_core`, chỉ trong sandbox.
- Worker công cụ không mở pickle; lỗi hoặc quá 300 s thì job `failed`. Xong (thành công hay lỗi)
  thì API xóa file `.pt` gốc. Lượt mất lease 3 lần thì file `.pt` còn lại trong `uploads/`.

## Thay đổi contract

- `ModelUploadCreate.filename`: nhận thêm `.pt`, `.pth` (≤ 500 MB). `POST /models` vẫn từ chối `.pt`.
- `ToolJobKind.MODEL_CONVERT`, `ModelConvertPayload { conversion_id, source_url, framework,
  result_upload_url }`, `ModelConvertReport { metadata: { architecture, class_names, input_size } }`.
- `POST /models/conversions { upload_id, framework: ultralytics | torchvision }` → 202
  `ModelConversionView { id, status, upload_id (kết quả), metadata, error }`;
  `GET /models/conversions/{id}`. Permission `model.manage`; mỗi người một lượt đang chạy (429).
- DB: migration thêm giá trị enum `tool_job_kind = model_convert` và bảng `model_conversions`
  (hoặc lưu trong `tool_jobs.payload/result`, không cần bảng mới).

## Ảnh hưởng

| Thư mục | Thay đổi |
|---|---|
| contracts | Enum, payload, report, view, endpoint ở trên; mock |
| backend | Endpoint chuyển đổi, dispatch job `model_convert`, dọn `.pt` sau khi xong hoặc hết hạn |
| worker | Xử lý job `model_convert` (chỉ chuyển tiếp sang converter); package converter |
| docker | Image + service `converter`, mạng `internal` riêng với `worker-tools` |
| frontend | Chọn file `.pt` thì thay lỗi bằng nút "Chuyển sang safetensors", hiện tiến độ, xong thì tự điền form như với file safetensors |
| specs | `mission.md` nguyên tắc 10 (diff ở trên), requirements R3 |

## Rủi ro còn lại

Sandbox giảm nhưng không loại hẳn rủi ro:
- lỗ hổng thoát container của kernel/Docker vẫn có thể bị khai thác bằng pickle độc;
- converter là service chạy lâu: pickle độc có thể để lại tiến trình nền (trong giới hạn
  `pids_limit`) và đọc hoặc sửa file `.pt`/kết quả của lượt sau trong spool. Kết quả vẫn phải qua
  `model_check`, nhưng weights có thể bị thay.

Môi trường triển khai thật nên chạy converter bằng gVisor (`runtime: runsc`), hoặc dựng một container
mới cho mỗi lượt (cần quyền điều khiển Docker ở một service điều phối riêng), hoặc chạy trên máy riêng.

## Phương án thay thế

Script chuyển đổi tải từ web, chạy trên máy người dùng: không đổi nguyên tắc 10, không có rủi ro trên
server, nhưng người dùng phải chạy một lệnh Python.
