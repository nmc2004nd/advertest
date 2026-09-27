import type { ErrorResponse } from '@/contracts/api'

type ErrorCode = ErrorResponse['error']['code']

/** Lỗi từ API. `code` là `unknown` khi body không theo định dạng ErrorResponse. */
export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode | 'unknown'

  constructor(status: number, code: ErrorCode | 'unknown', message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false
  const error = (body as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

export function toApiError(status: number, body: unknown): ApiError {
  if (isErrorResponse(body)) {
    return new ApiError(status, body.error.code, body.error.message)
  }
  return new ApiError(status, 'unknown', `Lỗi HTTP ${status}`)
}
