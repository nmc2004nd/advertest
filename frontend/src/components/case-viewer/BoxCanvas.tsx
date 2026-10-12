import { useEffect, useRef, useState } from 'react'

import { BOX_COLORS, BOX_STROKE, type BoxSet, boxesOf, LABELS_MEDIA_QUERY } from './boxes'
import { type Bbox, canvasSize, FULL_VIEW, fromCss, hitTest, toCss } from './geometry'

/**
 * Lớp canvas phủ lên ảnh: vẽ box từ JSON phía client, bộ đệm scale theo `devicePixelRatio`
 * (tech-stack.md mục 5.1). Màn hình nhỏ ẩn nhãn; chạm vào box để hiện nhãn của box đó.
 */
export function BoxCanvas({ set, view = FULL_VIEW }: { set: BoxSet; view?: Bbox }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [cssSize, setCssSize] = useState({ width: 0, height: 0 })
  const [selected, setSelected] = useState<number | null>(null)
  const [labelsShown, setLabelsShown] = useState(false)
  const boxes = boxesOf(set)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setCssSize({ width, height })
    })
    observer.observe(canvas)
    const media = window.matchMedia(LABELS_MEDIA_QUERY)
    const onMedia = () => setLabelsShown(media.matches)
    onMedia()
    media.addEventListener('change', onMedia)
    return () => {
      observer.disconnect()
      media.removeEventListener('change', onMedia)
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || cssSize.width === 0) return
    const { width, height, ratio } = canvasSize(
      cssSize.width,
      cssSize.height,
      window.devicePixelRatio,
    )
    canvas.width = width
    canvas.height = height
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    ctx.clearRect(0, 0, cssSize.width, cssSize.height)
    ctx.font = '12px sans-serif'
    for (const [index, box] of boxes.entries()) {
      const [x1, y1, x2, y2] = toCss(box.bbox, cssSize.width, view)
      ctx.strokeStyle = BOX_COLORS[box.kind]
      ctx.lineWidth = BOX_STROKE[box.kind].width
      ctx.setLineDash(BOX_STROKE[box.kind].dash)
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
      if (labelsShown || index === selected) {
        const text = box.label
        const w = ctx.measureText(text).width + 6
        ctx.fillStyle = BOX_COLORS[box.kind]
        ctx.setLineDash([])
        ctx.fillRect(x1, Math.max(0, y1 - 16), w, 16)
        ctx.fillStyle = '#000'
        ctx.fillText(text, x1 + 3, Math.max(12, y1 - 4))
      }
    }
  })

  const onClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    if (rect.width === 0) return
    const { x, y } = fromCss(event.clientX - rect.left, event.clientY - rect.top, rect.width, view)
    const hit = hitTest(
      boxes.map((box, index) => ({ ...box, index })),
      x,
      y,
    )
    setSelected(hit ? hit.index : null)
  }

  return (
    <canvas
      ref={canvasRef}
      onClick={onClick}
      className="absolute inset-0 size-full"
      aria-hidden="true"
      data-boxes={boxes.length}
    />
  )
}
