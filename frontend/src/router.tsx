import { createBrowserRouter, type RouteObject } from 'react-router'

import App from './App'
import { AppShell } from './layout/AppShell'
import { ForbiddenPage } from './pages/ForbiddenPage'

const routes: RouteObject[] = [
  { path: '/', element: <App /> },
  { path: '/forbidden', element: <ForbiddenPage /> },
  // Trang cần đăng nhập nằm trong khung ứng dụng (Group 5, 6 thêm trang con).
  { element: <AppShell />, children: [] },
]

// Chỉ có khi chạy dev: trong bản build production, nhánh này bị loại bỏ cùng module của trang.
if (import.meta.env.DEV) {
  routes.push({
    path: '/dev/contracts',
    lazy: async () => {
      const { ContractsPage } = await import('./dev/ContractsPage')
      return { Component: ContractsPage }
    },
  })
}

export const router = createBrowserRouter(routes)
