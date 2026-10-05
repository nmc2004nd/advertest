import { useEffect, useState } from 'react'

function reducedMotion(): boolean {
  return (
    typeof window === 'undefined' || window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** Số đếm dần từ 0 tới `target` (≈0.7 s); đứng yên khi người dùng bật giảm chuyển động. */
export function useCountUp(target: number, duration = 700): number {
  const [value, setValue] = useState(target)
  useEffect(() => {
    if (reducedMotion() || target === 0) return
    let frame = 0
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      setValue(Math.round(target * (1 - Math.pow(1 - t, 3))))
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])
  return reducedMotion() || target === 0 ? target : value
}
