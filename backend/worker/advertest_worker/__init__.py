"""Worker chạy experiment trên compute target (Phase 3, agent worker).

Gọi API nội bộ `/internal/worker` bằng token của compute target; không có thông tin đăng nhập
Postgres hay MinIO. Lệnh: `advertest-worker run|calibrate` (Group 4 cài đặt `cli.py`).
"""
