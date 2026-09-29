import { createBrowserRouter, type RouteObject } from 'react-router'

import { AppShell } from './layout/AppShell'
import { ForbiddenPage } from './pages/ForbiddenPage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { PendingPage } from './pages/PendingPage'
import { RequestAccessPage, RequestAccessSentPage } from './pages/RequestAccessPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'

const routes: RouteObject[] = [
  { path: '/', element: <LandingPage /> },
  { path: '/forbidden', element: <ForbiddenPage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/request-access', element: <RequestAccessPage /> },
  { path: '/request-access/sent', element: <RequestAccessSentPage /> },
  { path: '/pending', element: <PendingPage /> },
  { path: '/reset-password/:token', element: <ResetPasswordPage /> },
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
