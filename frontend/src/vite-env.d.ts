/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS?: string
  readonly VITE_API_BASE_URL?: string
  /** Chế độ mock: tên mock `contracts/mocks/me/<tên>.json` của người dùng đang đăng nhập. */
  readonly VITE_MOCK_ME?: string
  /** Bản deploy công khai: tài khoản demo hiện ở trang đăng nhập; thiếu một trong hai thì ẩn. */
  readonly VITE_DEMO_EMAIL?: string
  readonly VITE_DEMO_PASSWORD?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
