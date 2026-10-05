import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { RequirePermission } from './auth/RequirePermission'
import { ExperimentDetailPage } from './features/experiments/ExperimentDetailPage'
import { ExperimentsPage } from './features/experiments/ExperimentsPage'
import { FailureCasePage } from './features/experiments/FailureCasePage'
import { ProtocolsPage } from './features/protocols/ProtocolsPage'
import { ReportPage } from './features/reports/ReportPage'
import { ReportsPage } from './features/reports/ReportsPage'
import { VerifyPage } from './features/reports/VerifyPage'
import { ReviewCaseRoute } from './features/reviews/ReviewCasePage'
import { ReviewPage } from './features/reviews/ReviewPage'
import { ReviewsPage } from './features/reviews/ReviewsPage'
import { WizardPage } from './features/wizard/WizardPage'
import { AppShell } from './layout/AppShell'
import { AccountPage } from './pages/AccountPage'
import { AttacksPage } from './pages/admin/AttacksPage'
import { AuditPage } from './pages/admin/AuditPage'
import { UsersPage } from './pages/admin/UsersPage'
import { ForbiddenPage } from './pages/ForbiddenPage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { PendingPage } from './pages/PendingPage'
import { RequestAccessPage, RequestAccessSentPage } from './pages/RequestAccessPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'

const routes: RouteObject[] = [
  // Không có landing page: vào thẳng trang chủ; chưa đăng nhập thì khung ứng dụng chuyển sang
  // /login?next=/home.
  { path: '/', element: <Navigate to="/home" replace /> },
  { path: '/forbidden', element: <ForbiddenPage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/request-access', element: <RequestAccessPage /> },
  { path: '/request-access/sent', element: <RequestAccessSentPage /> },
  { path: '/pending', element: <PendingPage /> },
  { path: '/reset-password/:token', element: <ResetPasswordPage /> },
  // Phase 8: xác minh report công khai, không cần đăng nhập.
  { path: '/verify/:id', element: <VerifyPage /> },
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
        path: '/reviews',
        element: (
          <RequirePermission requirement="review.decide">
            <ReviewsPage />
          </RequirePermission>
        ),
      },
      {
        path: '/reviews/:id',
        element: (
          <RequirePermission requirement="review.decide">
            <ReviewPage />
          </RequirePermission>
        ),
      },
      {
        path: '/reviews/:id/cases/:caseId',
        element: (
          <RequirePermission requirement="review.decide">
            <ReviewCaseRoute />
          </RequirePermission>
        ),
      },
      {
        path: '/protocols',
        element: (
          <RequirePermission requirement="protocol.read">
            <ProtocolsPage />
          </RequirePermission>
        ),
      },
      {
        path: '/reports',
        element: (
          <RequirePermission requirement="report.read">
            <ReportsPage />
          </RequirePermission>
        ),
      },
      {
        path: '/reports/:id',
        element: (
          <RequirePermission requirement="report.read">
            <ReportPage />
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
        path: '/admin/attacks',
        element: (
          <RequirePermission requirement="attack_catalog.manage">
            <AttacksPage />
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
