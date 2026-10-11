import { BOX_COLORS, BOX_STROKE } from './boxes'

/** Ô màu của chú thích lớp: viền cùng màu và kiểu nét với box trên ảnh (design.md mục 3). */
export function BoxSwatch({ kind }: { kind: keyof typeof BOX_COLORS }) {
  const { width, dash } = BOX_STROKE[kind]
  return (
    <span
      aria-hidden="true"
      data-swatch={kind}
      className="inline-block size-3 shrink-0 rounded-[2px]"
      style={{
        borderColor: BOX_COLORS[kind],
        borderStyle: dash.length ? 'dashed' : 'solid',
        borderWidth: width,
      }}
    />
  )
}
