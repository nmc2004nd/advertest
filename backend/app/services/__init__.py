"""Service của backend (Phase 3): logic nghiệp vụ trên Postgres, không phụ thuộc HTTP.

Mỗi hàm nhận `Session` và không commit: người gọi (endpoint, CLI quản trị) quyết định transaction.
Lỗi nghiệp vụ là các lớp con của `ServiceError` (`errors.py`); tầng API đổi thành mã HTTP.
"""
