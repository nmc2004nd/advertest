/** Dữ liệu cho wizard: tài nguyên để chọn, ước lượng (debounce), tạo, nhân bản. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { apiGet, apiSend } from '@/api/client'
import type {
  AttackSpec,
  ClassMappingSummary,
  ComputeTargetPublic,
  DatasetSummary,
  EstimateResponse,
  ExperimentClone,
  ExperimentCreateInput,
  ExperimentDetail,
  ModelSummary,
  ProtocolSummary,
  SliceSummary,
} from '@/contracts/api'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'

/** Ước lượng gọi lại 500 ms sau lần thay đổi cấu hình cuối (requirements.md Phase 5). */
export const ESTIMATE_DEBOUNCE_MS = 500

const list =
  <T>(path: string) =>
  () =>
    apiGet<T[]>(path)

export const useProtocols = () =>
  useQuery({ queryKey: ['protocols'], queryFn: list<ProtocolSummary>('/protocols') })
export const useModels = () =>
  useQuery({ queryKey: ['models'], queryFn: list<ModelSummary>('/models') })
export const useDatasets = () =>
  useQuery({ queryKey: ['datasets'], queryFn: list<DatasetSummary>('/datasets') })
export const useAttackSpecs = () =>
  useQuery({ queryKey: ['attack-specs'], queryFn: list<AttackSpec>('/attack-specs') })
export const useComputeTargets = () =>
  useQuery({
    queryKey: ['compute-targets'],
    queryFn: list<ComputeTargetPublic>('/compute-targets'),
  })

/** Mọi slice (để tra dataset version của slice khi nhân bản) hoặc slice của một version. */
export function useSlices(datasetVersionId: string | null, all = false) {
  const path = all ? '/slices' : `/slices?dataset_version=${datasetVersionId ?? ''}`
  return useQuery({
    queryKey: ['slices', all ? 'all' : datasetVersionId],
    queryFn: list<SliceSummary>(path),
    enabled: all || datasetVersionId !== null,
  })
}

export function useClassMappings(datasetVersionId: string | null, modelId: string | null) {
  return useQuery({
    queryKey: ['class-mappings', datasetVersionId, modelId],
    queryFn: list<ClassMappingSummary>(
      `/class-mappings?dataset_version=${datasetVersionId ?? ''}&model=${modelId ?? ''}`,
    ),
    enabled: datasetVersionId !== null && modelId !== null,
  })
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

/** Ước lượng cho body hiện tại (null: chưa đủ cấu hình, không gọi). Giữ kết quả cũ khi đang
 * tính lại để giao diện không nhấp nháy. */
export function useEstimate(body: ExperimentCreateInput | null) {
  const key = body ? JSON.stringify(body) : null
  const debounced = useDebounced(key, ESTIMATE_DEBOUNCE_MS)
  return useQuery({
    queryKey: ['estimate', debounced],
    queryFn: () =>
      apiSend<EstimateResponse>('POST', '/experiments/estimate', JSON.parse(debounced ?? 'null')),
    enabled: debounced !== null,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useCreateExperiment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ExperimentCreateInput) =>
      apiSend<ExperimentDetail>('POST', '/experiments', body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY })
    },
  })
}

export function useClone(experimentId: string | null) {
  return useQuery({
    queryKey: ['experiments', experimentId, 'clone'],
    queryFn: () => apiGet<ExperimentClone>(`/experiments/${experimentId ?? ''}/clone`),
    enabled: experimentId !== null,
    staleTime: Infinity,
  })
}
