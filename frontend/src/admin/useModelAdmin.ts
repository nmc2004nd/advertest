import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import { POLL_INTERVAL_MS } from '@/api/queries'
import type { ModelRegister, ModelSummary, ModelUpload } from '@/contracts/api'

const MODELS_KEY = ['models'] as const

export function useModelList() {
  return useQuery({ queryKey: MODELS_KEY, queryFn: () => apiGet<ModelSummary[]>('/models') })
}

/** Một model; đang `checking` thì tự cập nhật mỗi 2 giây (tech-stack.md mục 5). */
export function useModel(id: string) {
  return useQuery({
    queryKey: [...MODELS_KEY, id],
    queryFn: () => apiGet<ModelSummary>(`/models/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'checking' ? POLL_INTERVAL_MS : false),
  })
}

export function useRecheckModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiSend<ModelSummary>('POST', `/models/${id}/check`),
    onSuccess: async (model) => {
      queryClient.setQueryData([...MODELS_KEY, model.id], model)
      await queryClient.invalidateQueries({ queryKey: MODELS_KEY })
    },
  })
}

/** PUT file lên presigned URL; dùng XMLHttpRequest vì `fetch` không báo tiến độ upload. */
export function putWithProgress(
  url: string,
  file: Blob,
  onProgress: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1)
        resolve()
      } else reject(new Error(`Tải file lên không thành công (HTTP ${xhr.status}).`))
    }
    xhr.onerror = () => reject(new Error('Mất kết nối khi tải file lên. Vui lòng thử lại.'))
    xhr.send(file)
  })
}

export type RegisterInput = Omit<ModelRegister, 'upload_id'> & { file: File }

/** Đăng ký: xin presigned URL → tải file lên (có tiến độ) → `POST /models` (model `checking`). */
export function useRegisterModel(onProgress: (fraction: number) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, ...body }: RegisterInput) => {
      onProgress(0)
      const upload = await apiSend<ModelUpload>('POST', '/models/uploads', {
        filename: file.name,
        size_bytes: file.size,
      })
      await putWithProgress(upload.url, file, onProgress)
      return apiSend<ModelSummary>('POST', '/models', { ...body, upload_id: upload.upload_id })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MODELS_KEY })
    },
  })
}
