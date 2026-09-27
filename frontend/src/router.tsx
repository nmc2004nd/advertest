import { createBrowserRouter, type RouteObject } from 'react-router'

import App from './App'

const routes: RouteObject[] = [{ path: '/', element: <App /> }]

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
