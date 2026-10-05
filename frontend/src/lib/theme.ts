import { useCallback, useState } from 'react'

export type Theme = 'dark' | 'light'

const KEY = 'advertest-theme'

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/** Theme sáng (mặc định) / tối; class `dark` trên <html> do index.html đặt trước khi vẽ. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    typeof document === 'undefined' ? 'light' : current(),
  )
  const toggle = useCallback(() => {
    const next: Theme = current() === 'dark' ? 'light' : 'dark'
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // Trình duyệt chặn bộ nhớ: theme vẫn đổi trong phiên này.
    }
    setTheme(next)
  }, [])
  return { theme, toggle }
}
