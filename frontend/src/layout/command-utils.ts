import { useEffect } from 'react'

/** Bỏ dấu tiếng Việt để gõ "tao exp" vẫn ra "Tạo experiment". */
export function fold(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
}

export function matches(
  command: { label: string; hint: string; keywords?: string },
  query: string,
) {
  const hay = fold(`${command.label} ${command.hint} ${command.keywords ?? ''}`)
  return fold(query)
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => hay.includes(word))
}

/** Mở bằng Ctrl/⌘ K ở mọi trang trong khung ứng dụng. */
export function useCommandShortcut(onOpen: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpen()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onOpen])
}
