import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'

import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
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
    <div className="hidden overflow-x-auto rounded-xl border border-border xl:block">
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
            className="flex flex-col gap-2 rounded-xl border border-border p-4 hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
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
  const [filters, setFilters] = useState<ExperimentFilters>({
    owner: canCreate ? 'me' : 'all',
    status: '',
    model: '',
  })
  const list = useExperiments(filters)
  const models = useModels()
  const items = list.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Experiment</h1>
        {canCreate && (
          <Button asChild>
            <Link to="/experiments/new">Tạo experiment</Link>
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <div role="tablist" aria-label="Người tạo" className="flex gap-2">
          {OWNER_TABS.map(([value, label]) => (
            <Button
              key={value}
              role="tab"
              aria-selected={filters.owner === value}
              variant={filters.owner === value ? 'default' : 'outline'}
              onClick={() => setFilters({ ...filters, owner: value })}
            >
              {label}
            </Button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:w-[32rem]">
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
        <p className="text-muted-foreground">Chưa có experiment nào khớp bộ lọc.</p>
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
