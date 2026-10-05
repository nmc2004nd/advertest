import { useQuery } from '@tanstack/react-query'
import { CornerDownLeft, FlaskConical, Search, type LucideIcon } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { apiGet } from '@/api/client'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import type { ExperimentPage } from '@/contracts/api'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'
import { cn } from '@/lib/utils'
import { visibleNav } from '@/nav/config'

import { matches } from './command-utils'

interface Command {
  id: string
  label: string
  hint: string
  icon: LucideIcon
  to: string
  keywords?: string
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLUListElement>(null)
  const experiments = useQuery({
    queryKey: [...EXPERIMENTS_KEY, 'flow'],
    queryFn: () => apiGet<ExperimentPage>('/experiments?owner=all&limit=50'),
    enabled: open && can(me, 'experiment.read'),
  })

  const commands = useMemo<Command[]>(() => {
    const actions: Command[] = []
    if (can(me, 'experiment.create'))
      actions.push({
        id: 'a-new',
        label: 'Tạo experiment',
        hint: 'Hành động',
        icon: FlaskConical,
        to: '/experiments/new',
        keywords: 'moi chay attack wizard',
      })
    if (can(me, 'protocol.manage'))
      actions.push({
        id: 'a-protocol',
        label: 'Tạo protocol',
        hint: 'Hành động',
        icon: FlaskConical,
        to: '/protocols?new=1',
        keywords: 'tieu chi nguong',
      })
    const pages = visibleNav(me).map((item) => ({
      id: `p-${item.path}`,
      label: item.label,
      hint: 'Trang',
      icon: item.icon,
      to: item.path,
    }))
    const exps = (experiments.data?.items ?? []).map((e) => ({
      id: `e-${e.id}`,
      label: e.name,
      hint: 'Experiment',
      icon: FlaskConical,
      to: `/experiments/${e.id}`,
      keywords: e.status,
    }))
    return [...actions, ...pages, ...exps]
  }, [me, experiments.data])

  const results = useMemo(
    () => (query ? commands.filter((c) => matches(c, query)) : commands).slice(0, 12),
    [commands, query],
  )

  const run = (command: Command | undefined) => {
    if (!command) return
    onOpenChange(false)
    setQuery('')
    void navigate(command.to)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) setQuery('')
      }}
    >
      <DialogContent className="gap-0 p-0 md:top-[20%] md:max-w-xl md:translate-y-0">
        <DialogTitle className="sr-only">Tìm nhanh</DialogTitle>
        <DialogDescription className="sr-only">
          Gõ để tìm trang, hành động hoặc experiment; Enter để mở.
        </DialogDescription>
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActive((i) => Math.min(i + 1, results.length - 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((i) => Math.max(i - 1, 0))
              } else if (event.key === 'Enter') {
                event.preventDefault()
                run(results[active])
              }
            }}
            placeholder="Gõ tên trang, hành động hoặc experiment, ví dụ: tạo exp"
            aria-label="Tìm nhanh"
            aria-controls="ket-qua-tim-nhanh"
            aria-activedescendant={results[active] ? `lenh-${results[active].id}` : undefined}
            className="min-h-14 flex-1 bg-transparent pr-10 text-base outline-none"
          />
        </div>
        <ul
          id="ket-qua-tim-nhanh"
          role="listbox"
          ref={listRef}
          className="max-h-[50dvh] overflow-y-auto p-2"
        >
          {results.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              Không có kết quả cho “{query}”. Thử từ khóa ngắn hơn.
            </li>
          )}
          {results.map((command, i) => (
            <li
              key={command.id}
              id={`lenh-${command.id}`}
              role="option"
              aria-selected={i === active}
              onMouseMove={() => setActive(i)}
              onClick={() => run(command)}
              className={cn(
                'flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-sm',
                i === active && 'bg-accent text-accent-foreground',
              )}
            >
              <command.icon className="size-4 shrink-0 opacity-70" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{command.label}</span>
              <span className="text-xs text-muted-foreground">{command.hint}</span>
              {i === active && <CornerDownLeft className="size-3.5 opacity-60" aria-hidden />}
            </li>
          ))}
        </ul>
        <p className="hidden border-t border-border px-4 py-2 text-xs text-muted-foreground md:block">
          ↑ ↓ để chọn, Enter để mở, Esc để đóng
        </p>
      </DialogContent>
    </Dialog>
  )
}
