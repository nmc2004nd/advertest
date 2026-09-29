import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { authRedirect } from './auth-redirect'

/**
 * QueryClient có xử lý lỗi xác thực toàn cục: `401 unauthenticated` → `/login?next=...`,
 * `403 forbidden` → `/forbidden` (requirements.md Phase 4, Hành vi chung).
 */
export function createQueryClient(navigate: (to: string) => void, currentPath: () => string) {
  const onError = (error: unknown) => {
    const target = authRedirect(error, currentPath())
    if (target) navigate(target)
  }
  return new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
  })
}
