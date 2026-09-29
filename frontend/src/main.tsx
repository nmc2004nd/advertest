import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'

import { createQueryClient } from './api/query-client'
import './index.css'
import { router } from './router'

const root = document.getElementById('root')
if (!root) throw new Error('Không tìm thấy phần tử #root')

// 401/403 từ API → chuyển trang toàn cục (router.navigate dùng được ngoài component).
const queryClient = createQueryClient(
  (to) => void router.navigate(to),
  () => `${window.location.pathname}${window.location.search}`,
)

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
