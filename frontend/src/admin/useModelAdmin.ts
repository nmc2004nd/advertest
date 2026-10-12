import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import { POLL_INTERVAL_MS } from '@/api/queries'
import type {
  ClassMappingCreate,
  ClassMappingSummary,
  ModelConversionView,
  ModelRegister,
  ModelSummary,
  ModelUpload,
} from '@/contracts/api'

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

/** Lưu trữ hoặc khôi phục model (đề xuất contract 002, Phase R3). */
export function useArchiveModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      apiSend<ModelSummary>('POST', `/models/${id}/${archived ? 'archive' : 'restore'}`),
    onSuccess: async (model) => {
      queryClient.setQueryData([...MODELS_KEY, model.id], model)
      await queryClient.invalidateQueries({ queryKey: MODELS_KEY })
    },
  })
}

/** Xóa model chưa dùng; model đã có experiment hoặc thử nhanh thì backend trả 409. */
export function useDeleteModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiSend<undefined>('DELETE', `/models/${id}`),
    onSuccess: async (_, id) => {
      queryClient.removeQueries({ queryKey: [...MODELS_KEY, id], exact: true })
      await queryClient.invalidateQueries({ queryKey: MODELS_KEY })
      await queryClient.invalidateQueries({ queryKey: ['class-mappings'] })
    },
  })
}

/** Class mapping của một model (mọi dataset version). */
export function useModelMappings(modelId: string) {
  return useQuery({
    queryKey: ['class-mappings', 'model', modelId],
    queryFn: () => apiGet<ClassMappingSummary[]>(`/class-mappings?model=${modelId}`),
  })
}

export function useCreateMapping() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ClassMappingCreate) =>
      apiSend<ClassMappingSummary>('POST', '/class-mappings', body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['class-mappings'] })
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

/** Xin presigned URL rồi tải file lên (có tiến độ); trả `upload_id`. */
async function uploadFile(file: File, onProgress: (fraction: number) => void): Promise<string> {
  onProgress(0)
  const upload = await apiSend<ModelUpload>('POST', '/models/uploads', {
    filename: file.name,
    size_bytes: file.size,
  })
  await putWithProgress(upload.url, file, onProgress)
  return upload.upload_id
}

/** `file`: tải lên rồi đăng ký; `upload_id`: file đã có trên máy chủ (kết quả chuyển đổi `.pt`). */
export type RegisterInput = Omit<ModelRegister, 'upload_id'> &
  ({ file: File; upload_id?: undefined } | { file?: undefined; upload_id: string })

/** Đăng ký: tải file lên (nếu cần) → `POST /models` (model `checking`). */
export function useRegisterModel(onProgress: (fraction: number) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, upload_id, ...body }: RegisterInput) => {
      const uploadId = file ? await uploadFile(file, onProgress) : upload_id
      return apiSend<ModelSummary>('POST', '/models', { ...body, upload_id: uploadId })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MODELS_KEY })
    },
  })
}

/** Tải `.pt`/`.pth` lên rồi xin chuyển sang safetensors trong sandbox (đề xuất contract 003). */
export function useStartConversion(onProgress: (fraction: number) => void) {
  return useMutation({
    mutationFn: async ({
      file,
      framework,
    }: {
      file: File
      framework: 'ultralytics' | 'torchvision'
    }) => {
      const uploadId = await uploadFile(file, onProgress)
      return apiSend<ModelConversionView>('POST', '/models/conversions', {
        upload_id: uploadId,
        framework,
      })
    },
  })
}

/** Lượt chuyển đổi; tự cập nhật mỗi 2 giây cho tới khi xong hoặc lỗi. */
export function useConversion(id: string | null) {
  return useQuery({
    queryKey: ['model-conversions', id],
    queryFn: () => apiGet<ModelConversionView>(`/models/conversions/${id ?? ''}`),
    enabled: id !== null,
    refetchInterval: (q) =>
      q.state.data && ['completed', 'failed'].includes(q.state.data.status)
        ? false
        : POLL_INTERVAL_MS,
  })
}
