/**
 * Xác minh file report (requirements.md Phase 8, Frontend công khai; plan task 33): SHA-256 tính
 * trong trình duyệt bằng Web Crypto; nội dung file không rời máy người dùng. Web Crypto chỉ có
 * trong secure context (HTTPS hoặc localhost): không có thì trang báo cần HTTPS (chốt ở kế hoạch
 * Group 6).
 */
import type { VerifyInfo } from '@/contracts/api'

export function hasWebCrypto(): boolean {
  return typeof globalThis.crypto?.subtle?.digest === 'function'
}

export async function sha256Hex(data: ArrayBuffer | Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', data)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export type VerifyResult = { match: true; format: 'pdf' | 'json' } | { match: false }

/** So hash vừa tính với hai hash đã phát hành (không phân biệt hoa thường). */
export function compareHash(hash: string, info: VerifyInfo): VerifyResult {
  const value = hash.toLowerCase()
  if (value === info.pdf_sha256.toLowerCase()) return { match: true, format: 'pdf' }
  if (value === info.json_sha256.toLowerCase()) return { match: true, format: 'json' }
  return { match: false }
}

/** Tính hash của file người dùng chọn và so với report: không request nào mang nội dung file. */
export async function verifyFile(
  file: Blob,
  info: VerifyInfo,
): Promise<{ hash: string; result: VerifyResult }> {
  const hash = await sha256Hex(await file.arrayBuffer())
  return { hash, result: compareHash(hash, info) }
}
