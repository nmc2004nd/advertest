/** Chữ cái đầu cho avatar: tên Việt lấy họ + tên gọi (từ cuối). */
export function initials(name?: string | null): string {
  const parts = (name ?? '?').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  // Tên Việt: chữ cái đầu của tên gọi (từ cuối) là quan trọng nhất.
  const last = parts[parts.length - 1][0]
  return (parts.length > 1 ? parts[0][0] + last : parts[0].slice(0, 2)).toUpperCase()
}
