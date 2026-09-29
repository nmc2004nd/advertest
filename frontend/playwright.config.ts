// E2E Playwright (tech-stack.md mục 7): 3 viewport theo breakpoint mục 5.1.
// Chạy trên bản build production (`vite preview`, proxy /api sang backend thật ở
// API_PROXY_TARGET, mặc định http://127.0.0.1:8000). Backend do người chạy tự khởi động.
import { defineConfig, devices } from '@playwright/test'

const PORT = 4173

export default defineConfig({
  testDir: './e2e',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'phone',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'tablet',
      use: { ...devices['Desktop Chrome'], viewport: { width: 820, height: 1180 } },
    },
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    // Gọi thẳng vite (không qua `pnpm preview`): tiến trình con của pnpm thoát khỏi process
    // group nên Playwright không tắt được server và bị treo sau khi chạy xong.
    command: `pnpm build && exec ./node_modules/.bin/vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    // Bản build gọi API qua proxy /api như compose và bản triển khai (tech-stack.md mục 6).
    env: { VITE_API_BASE_URL: '/api' },
    timeout: 120_000,
  },
})
