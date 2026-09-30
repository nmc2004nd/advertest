import { createBrowserRouter, type RouteObject } from 'react-router'

import { RequirePermission } from './auth/RequirePermission'
import { ExperimentDetailPage } from './features/experiments/ExperimentDetailPage'
import { ExperimentsPage } from './features/experiments/ExperimentsPage'
import { FailureCasePage } from './features/experiments/FailureCasePage'
import { WizardPage } from './features/wizard/WizardPage'
import { AppShell } from './layout/AppShell'
import { AccountPage } from './pages/AccountPage'
import { AuditPage } from './pages/admin/AuditPage'
import { UsersPage } from './pages/admin/UsersPage'
import { ForbiddenPage } from './pages/ForbiddenPage'
import { HomePage } from './pages/HomePage'
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
  // Trang cần đăng nhập nằm trong khung ứng dụng; trang admin chặn thêm theo permission.
  {
    element: <AppShell />,
    children: [
      { path: '/home', element: <HomePage /> },
      { path: '/account', element: <AccountPage /> },
      {
        path: '/experiments',
        element: (
          <RequirePermission requirement="experiment.read">
            <ExperimentsPage />
          </RequirePermission>
        ),
      },
      {
        path: '/experiments/:id',
        element: (
          <RequirePermission requirement="experiment.read">
            <ExperimentDetailPage />
          </RequirePermission>
        ),
      },
      {
        path: '/failure-cases/:id',
        element: (
          <RequirePermission requirement="experiment.read">
            <FailureCasePage />
          </RequirePermission>
        ),
      },
      {
        path: '/experiments/new',
        element: (
          <RequirePermission requirement="experiment.create">
            <WizardPage />
          </RequirePermission>
        ),
      },
      {
        path: '/admin/users',
        element: (
          <RequirePermission requirement="user.manage">
            <UsersPage />
          </RequirePermission>
        ),
      },
      {
        path: '/admin/audit',
        element: (
          <RequirePermission requirement="audit.read">
            <AuditPage />
          </RequirePermission>
        ),
      },
    ],
  },
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
