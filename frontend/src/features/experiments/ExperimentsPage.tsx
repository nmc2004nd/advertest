import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import { FlaskConical, Plus } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { EmptyState } from '@/components/EmptyState'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { SelectField } from '@/components/form/TextField'
import { EXPERIMENT_STATUS } from '@/components/status/status-config'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ExperimentStatus, ExperimentSummary } from '@/contracts/api'
import { experimentStatusValues } from '@/contracts/schemas'
import { useModels } from '@/features/wizard/api'

import { type ExperimentFilters, useExperiments } from './api'
import { timeText } from './format'
import { ProgressBar } from './ProgressBar'
import { PageHero } from '@/layout/PageHero'
import { ExperimentArt } from '@/layout/hero-art'

const OWNER_TABS: [ExperimentFilters['owner'], string][] = [
  ['me', 'Của tôi'],
  ['all', 'Tất cả'],
]

const features = tableFeatures({})
const column = createColumnHelper<typeof features, ExperimentSummary>()

function ExperimentTable({ items }: { items: ExperimentSummary[] }) {
  const columns = useMemo(
    () =>
      column.columns([
        column.accessor('name', {
          header: 'Experiment',
          cell: ({ row }) => (
            <div className="flex flex-col">
              <Link
                to={`/experiments/${row.original.id}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {row.original.name}
              </Link>
              <span className="text-muted-foreground">{row.original.owner.full_name}</span>
            </div>
          ),
        }),
        column.accessor('status', {
          header: 'Trạng thái',
          cell: ({ getValue }) => <StatusBadge kind="experiment" status={getValue()} />,
        }),
        column.display({
          id: 'model',
          header: 'Model · slice',
          cell: ({ row }) => `${row.original.model.name} · ${row.original.slice.name}`,
        }),
        column.display({
          id: 'progress',
          header: 'Tiến độ',
          cell: ({ row }) => <ProgressBar progress={row.original.progress} />,
        }),
        column.display({
          id: 'time',
          header: 'Thời gian',
          cell: ({ row }) => timeText(row.original),
        }),
      ]),
    [],
  )
  const table = useTable({ features, columns, data: items, getRowId: (e) => e.id })
  return (
    <div className="panel hidden overflow-x-auto xl:block">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted/50">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} scope="col" className="px-3 py-2 font-medium">
                  <table.FlexRender header={header} />
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-t border-border align-top">
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className="px-3 py-3">
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ExperimentCards({ items }: { items: ExperimentSummary[] }) {
  return (
    <ul className="flex flex-col gap-3 xl:hidden">
      {items.map((e) => (
        <li key={e.id}>
          <Link
            to={`/experiments/${e.id}`}
            className="panel flex flex-col gap-2 p-4 hover:bg-surface-raised/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0 font-medium break-all">{e.name}</span>
              <StatusBadge kind="experiment" status={e.status} />
            </div>
            <ProgressBar progress={e.progress} />
            <span className="text-sm text-muted-foreground">
              {e.owner.full_name} · {timeText(e)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Danh sách experiment (requirements.md Phase 5, Frontend: danh sách và chi tiết). */
export function ExperimentsPage() {
  const { data: me } = useMe()
  const canCreate = can(me, 'experiment.create')
  // `?status=` (link từ thẻ chỉ số ở trang chủ) chọn sẵn bộ lọc trạng thái, xem mọi người tạo.
  const [params] = useSearchParams()
  const fromUrl = params.get('status')
  const initialStatus = experimentStatusValues.includes(fromUrl as ExperimentStatus)
    ? (fromUrl as ExperimentStatus)
    : ''
  const [filters, setFilters] = useState<ExperimentFilters>({
    owner: canCreate && !initialStatus ? 'me' : 'all',
    status: initialStatus,
    model: '',
  })
  const list = useExperiments(filters)
  const models = useModels()
  const items = list.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 md:p-8">
      <PageHero
        art={<ExperimentArt />}
        title="Experiment"
        description="Mỗi experiment chạy một nhóm attack trên một model và một slice ảnh. Bấm vào một dòng để xem tiến độ, kết quả và các ảnh bị đánh lừa."
        actions={
          canCreate ? (
            <Button asChild size="lg">
              <Link to="/experiments/new">
                <Plus aria-hidden />
                Tạo experiment
              </Link>
            </Button>
          ) : undefined
        }
      />
      <div className="flex flex-col gap-4 md:flex-row md:items-end">
        <div role="tablist" aria-label="Người tạo" className="seg self-start md:mb-0.5">
          {OWNER_TABS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={filters.owner === value}
              onClick={() => setFilters({ ...filters, owner: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:ml-auto md:w-[34rem]">
          <SelectField
            label="Trạng thái"
            value={filters.status}
            onChange={(event) =>
              setFilters({ ...filters, status: event.target.value as ExperimentStatus | '' })
            }
          >
            <option value="">Mọi trạng thái</option>
            {experimentStatusValues.map((status) => (
              <option key={status} value={status}>
                {EXPERIMENT_STATUS[status].label}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Model"
            value={filters.model}
            onChange={(event) => setFilters({ ...filters, model: event.target.value })}
          >
            <option value="">Mọi model</option>
            {models.data?.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </SelectField>
        </div>
      </div>
      {list.isPending ? (
        <PageLoading />
      ) : list.isError ? (
        <LoadError onRetry={() => void list.refetch()} retrying={list.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title={
            filters.status || filters.model
              ? 'Không có experiment nào khớp bộ lọc'
              : 'Chưa có experiment nào'
          }
          action={
            filters.status || filters.model ? (
              <Button
                variant="outline"
                onClick={() => setFilters({ ...filters, status: '', model: '' })}
              >
                Xóa bộ lọc
              </Button>
            ) : canCreate ? (
              <Button asChild>
                <Link to="/experiments/new">
                  <Plus aria-hidden />
                  Tạo experiment đầu tiên
                </Link>
              </Button>
            ) : undefined
          }
        >
          {filters.status || filters.model
            ? 'Thử chọn "Mọi trạng thái" hoặc "Mọi model", hoặc chuyển sang tab "Tất cả".'
            : 'Experiment đầu tiên chỉ mất 6 bước: chọn protocol, model, slice ảnh, attack và mức tấn công, rồi xác nhận.'}
        </EmptyState>
      ) : (
        <>
          <ExperimentTable items={items} />
          <ExperimentCards items={items} />
          {list.hasNextPage && (
            <Button
              variant="outline"
              className="self-center"
              onClick={() => void list.fetchNextPage()}
              disabled={list.isFetchingNextPage}
            >
              {list.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}
            </Button>
          )}
        </>
      )}
    </div>
  )
}
