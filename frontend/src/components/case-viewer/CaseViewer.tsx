import { ChevronLeft, ChevronRight, EyeOff, TriangleAlert } from 'lucide-react'
import { type ReactNode, useRef, useState } from 'react'
import {
  type ReactZoomPanPinchContentRef,
  TransformComponent,
  TransformWrapper,
} from 'react-zoom-pan-pinch'

import { Button } from '@/components/ui/button'
import type { FailureCaseView } from '@/contracts/api'
import { artifactSrc } from '@/features/experiments/api'

import { BoxCanvas } from './BoxCanvas'
import { BOX_COLORS, type BoxSet } from './boxes'
import { ALL_LAYERS, type Layer, LAYERS, lostObjects } from './geometry'

export const WATERMARK = 'BẢN NHÁP – CHƯA DUYỆT'
export const HIDDEN_TEXT = 'Ảnh bị ẩn: dataset chưa được làm mờ'
export const DEV_WARNING = 'Chưa làm mờ – chỉ dùng cho phát triển'
/** Vuốt ngang tối thiểu (px) để chuyển case trên điện thoại. */
export const SWIPE_MIN_PX = 60

export interface CaseViewerProps {
  caseView: FailureCaseView
  onPrev?: () => void
  onNext?: () => void
  /** Ảnh tải lỗi (thường do URL hết hạn): trang xin lại case (task 22). */
  onImageError?: () => void
  /** Phase 8: form verdict và phím tắt đặt ở đây, không phải viết lại trình xem. */
  aside?: ReactNode
}

function Watermark() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden select-none"
    >
      <span className="-rotate-30 text-center text-base font-bold whitespace-nowrap text-white/60 [text-shadow:0_0_3px_rgba(0,0,0,0.8)] sm:text-2xl">
        {WATERMARK}
      </span>
    </div>
  )
}

function Frame({
  src,
  alt,
  hidden,
  boxes,
  onImageError,
}: {
  src: string | null
  alt: string
  hidden: boolean
  boxes: BoxSet | null
  onImageError?: () => void
}) {
  return (
    <div className="relative aspect-square w-full overflow-hidden bg-muted">
      {hidden || !src ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm text-muted-foreground">
          <EyeOff aria-hidden="true" className="size-6" />
          {HIDDEN_TEXT}
        </div>
      ) : (
        <img
          src={src}
          alt={alt}
          draggable={false}
          onError={onImageError}
          className="absolute inset-0 size-full object-contain"
        />
      )}
      {boxes && <BoxCanvas set={boxes} />}
      <Watermark />
    </div>
  )
}

function LayerToggles({
  layers,
  onChange,
}: {
  layers: Record<Layer, boolean>
  onChange: (layers: Record<Layer, boolean>) => void
}) {
  return (
    <div role="group" aria-label="Lớp box" className="flex flex-wrap gap-2">
      {LAYERS.map(({ key, label }) => (
        <Button
          key={key}
          variant={layers[key] ? 'default' : 'outline'}
          aria-pressed={layers[key]}
          onClick={() => onChange({ ...layers, [key]: !layers[key] })}
        >
          <span
            aria-hidden="true"
            className="inline-block size-3 rounded-sm"
            style={{ backgroundColor: BOX_COLORS[key] }}
          />
          {label}
        </Button>
      ))}
      <span className="inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground">
        <span
          aria-hidden="true"
          className="inline-block size-3 rounded-sm"
          style={{ backgroundColor: BOX_COLORS.lost }}
        />
        Object bị mất
      </span>
    </div>
  )
}

/** Hai khung cạnh nhau, zoom và kéo đồng bộ (desktop, tablet). */
function SideBySide({
  clean,
  adversarial,
  hidden,
  onImageError,
  cleanBoxes,
  attackedBoxes,
}: {
  clean: string | null
  adversarial: string | null
  hidden: boolean
  onImageError?: () => void
  cleanBoxes: BoxSet
  attackedBoxes: BoxSet
}) {
  const refs = [
    useRef<ReactZoomPanPinchContentRef>(null),
    useRef<ReactZoomPanPinchContentRef>(null),
  ]
  const syncing = useRef(false)
  const panes = [
    { title: 'Ảnh sạch', src: clean, boxes: cleanBoxes },
    { title: 'Sau tấn công', src: adversarial, boxes: attackedBoxes },
  ]
  return (
    <div className="grid grid-cols-2 gap-3">
      {panes.map((pane, i) => (
        <figure key={pane.title} className="min-w-0 space-y-1">
          <figcaption className="text-sm font-medium">{pane.title}</figcaption>
          <TransformWrapper
            ref={refs[i]}
            minScale={1}
            maxScale={8}
            onTransform={(_, state) => {
              if (syncing.current) return
              syncing.current = true
              void refs[1 - i].current
                ?.setTransform(state.positionX, state.positionY, state.scale, 0)
                .finally(() => {
                  syncing.current = false
                })
            }}
          >
            <TransformComponent wrapperClass="!w-full" contentClass="!w-full">
              <Frame
                src={pane.src}
                alt={pane.title}
                hidden={hidden}
                boxes={pane.boxes}
                onImageError={onImageError}
              />
            </TransformComponent>
          </TransformWrapper>
        </figure>
      ))}
    </div>
  )
}

/** Điện thoại: slider kéo giữa ảnh sạch và sau tấn công, pinch-zoom, vuốt để chuyển case. */
function Slider({
  clean,
  adversarial,
  hidden,
  onImageError,
  cleanBoxes,
  attackedBoxes,
  onPrev,
  onNext,
}: {
  clean: string | null
  adversarial: string | null
  hidden: boolean
  onImageError?: () => void
  cleanBoxes: BoxSet
  attackedBoxes: BoxSet
  onPrev?: () => void
  onNext?: () => void
}) {
  const [position, setPosition] = useState(50)
  const [zoomed, setZoomed] = useState(false)
  const start = useRef<{ x: number; y: number } | null>(null)

  const onTouchStart = (event: React.TouchEvent) => {
    start.current =
      event.touches.length === 1 && !zoomed
        ? { x: event.touches[0].clientX, y: event.touches[0].clientY }
        : null
  }
  const onTouchEnd = (event: React.TouchEvent) => {
    const from = start.current
    start.current = null
    if (!from || event.changedTouches.length !== 1) return
    const dx = event.changedTouches[0].clientX - from.x
    const dy = event.changedTouches[0].clientY - from.y
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dy) > Math.abs(dx) / 2) return
    if (dx < 0) onNext?.()
    else onPrev?.()
  }

  return (
    <div className="space-y-2">
      <div onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} data-swipe="true">
        <TransformWrapper
          minScale={1}
          maxScale={8}
          panning={{ disabled: !zoomed }}
          onTransform={(_, state) => setZoomed(state.scale > 1.01)}
        >
          <TransformComponent wrapperClass="!w-full" contentClass="!w-full">
            <div className="relative w-full">
              <Frame
                src={adversarial}
                alt="Sau tấn công"
                hidden={hidden}
                boxes={attackedBoxes}
                onImageError={onImageError}
              />
              <div
                className="absolute inset-0"
                style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
              >
                <Frame
                  src={clean}
                  alt="Ảnh sạch"
                  hidden={hidden}
                  boxes={cleanBoxes}
                  onImageError={onImageError}
                />
              </div>
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow"
                style={{ left: `${position}%` }}
              />
            </div>
          </TransformComponent>
        </TransformWrapper>
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Sạch</span>
        <input
          type="range"
          min={0}
          max={100}
          value={position}
          onChange={(event) => setPosition(Number(event.target.value))}
          aria-label="Kéo để so sánh ảnh sạch và ảnh sau tấn công"
          className="h-11 flex-1"
        />
        <span>Sau tấn công</span>
      </div>
    </div>
  )
}

/**
 * Trình xem failure case (requirements.md Phase 5): chỉ xem, luôn có watermark. Dùng lại ở
 * Phase 8 (form verdict và phím tắt qua `aside`).
 */
export function CaseViewer({ caseView, onPrev, onNext, onImageError, aside }: CaseViewerProps) {
  const [layers, setLayers] = useState(ALL_LAYERS)
  const hidden = caseView.display_mode === 'hidden_unanonymized'
  const { detections, urls } = caseView
  const lost = layers.ground_truth ? lostObjects(detections) : []
  const common = {
    groundTruth: layers.ground_truth ? detections.ground_truth : [],
    ignoreRegions: layers.ignore_regions ? detections.ignore_regions : [],
    lost,
  }
  // Object bị mất chỉ tô đỏ trên ảnh sau tấn công (trên ảnh sạch chúng vẫn được phát hiện).
  const cleanBoxes: BoxSet = {
    ...common,
    lost: [],
    predictions: layers.clean ? detections.clean : [],
    predictionKind: 'clean',
  }
  const attackedBoxes: BoxSet = {
    ...common,
    predictions: layers.attacked ? detections.attacked : [],
    predictionKind: 'attacked',
  }
  const images = {
    clean: artifactSrc(urls.clean),
    adversarial: artifactSrc(urls.adversarial),
    hidden,
    onImageError,
    cleanBoxes,
    attackedBoxes,
  }

  return (
    <div
      className={aside ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]' : 'grid gap-4'}
      data-display-mode={caseView.display_mode}
    >
      <div className="min-w-0 space-y-3">
        {caseView.display_mode === 'dev_unblurred' && (
          <p
            role="alert"
            className="flex items-center gap-2 rounded-md bg-amber-100 px-3 py-2 text-sm font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
          >
            <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
            {DEV_WARNING}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          Ảnh {caseView.image_id} · mất {caseView.lost_objects} object · thêm{' '}
          {caseView.new_false_positives} phát hiện sai · mức nghiêm trọng {caseView.severity_score}
          <span className="sr-only"> · {WATERMARK}</span>
        </p>
        <LayerToggles layers={layers} onChange={setLayers} />
        <div className="hidden md:block">
          <SideBySide {...images} />
        </div>
        <div className="md:hidden">
          <Slider {...images} onPrev={onPrev} onNext={onNext} />
        </div>
        <figure className="max-w-xs space-y-1">
          <figcaption className="text-sm font-medium">Nhiễu khuếch đại</figcaption>
          <Frame
            src={artifactSrc(urls.perturbation)}
            alt="Nhiễu khuếch đại"
            hidden={hidden}
            boxes={null}
            onImageError={onImageError}
          />
        </figure>
        {(onPrev || onNext) && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={onPrev} disabled={!onPrev}>
              <ChevronLeft aria-hidden="true" />
              Case trước
            </Button>
            <Button variant="outline" onClick={onNext} disabled={!onNext}>
              Case sau
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
      {aside && <aside className="min-w-0">{aside}</aside>}
    </div>
  )
}
