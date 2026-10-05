# Chạy AdverTest bằng Docker

Một lệnh dựng toàn bộ hệ thống trên máy của bạn: Postgres, MinIO, Mailpit, API, frontend và worker
CPU. Lệnh này cũng nạp sẵn tài khoản admin, model YOLOv8n và 5 ảnh KITTI mẫu.

## Cần có

- Docker Desktop (Windows, macOS) hoặc Docker Engine có Compose v2 (Linux), **đang chạy**.
- Windows: chạy lệnh trong **Git Bash** (cài cùng Git) hoặc WSL.
- Mạng ở lần chạy đầu (tải image, PyTorch CPU, gói Node). Lần đầu mất khoảng 5–15 phút.

## Chạy

Từ thư mục gốc của repo:

```bash
bash deploy/start.sh
```

Khi xong, script in ra địa chỉ web (http://localhost:5173) cùng email và mật khẩu admin. Mật khẩu
được sinh ngẫu nhiên và lưu trong `.env`; không commit file này.

## Dừng

```bash
bash deploy/stop.sh          # dừng, giữ dữ liệu
bash deploy/stop.sh --xoa    # dừng và xóa sạch dữ liệu
```

## Sự cố thường gặp

- **Cổng đã bị dùng** (5173, 8000, 9000, 9001, 8025): tắt ứng dụng đang dùng cổng đó, hoặc đặt
  `FRONTEND_PORT=5174` (hoặc `API_PORT`, `MINIO_PORT`...) trong `.env` rồi chạy lại.
- **Đã có `.env` cũ**: script không ghi đè. Cần có `MINIO_PUBLIC_ENDPOINT=http://minio:9000` để
  worker trong Docker tải được ảnh; giá trị có dấu cách hoặc `<`, `>` phải đặt trong nháy kép.
  Muốn làm lại từ đầu: `bash deploy/stop.sh --xoa`, xóa `.env`, rồi chạy lại `start.sh`.
- **Experiment đứng ở "Đang chờ"**: xem log worker bằng lệnh mà `start.sh` in ra ở cuối. Lần chạy
  đầu, worker tự đo chi phí (calibration) nên chậm hơn.
