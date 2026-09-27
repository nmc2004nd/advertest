/// <reference types="vitest/config" />
import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const mocksDir = path.resolve(import.meta.dirname, '../contracts/mocks')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    // Chế độ mock đọc JSON trong contracts/mocks (ngoài thư mục frontend).
    fs: { allow: [import.meta.dirname, mocksDir] },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
