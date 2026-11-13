/** 统一 API 错误解析：后端错误结构为 {"error": {"code","message","details"}} */

export interface ApiErrorPayload {
  code: string
  message: string
  details: Record<string, unknown>
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message)
    this.name = 'ApiError'
    this.status = status
    this.code = payload.code
    this.details = payload.details ?? {}
  }
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch (e) {
    throw new Error(`无法连接后端：${e instanceof Error ? e.message : String(e)}`)
  }
  if (!res.ok) {
    let payload: { error?: ApiErrorPayload } | null = null
    try {
      payload = (await res.json()) as { error?: ApiErrorPayload }
    } catch {
      /* 非 JSON 错误体 */
    }
    if (payload?.error) {
      throw new ApiError(res.status, payload.error)
    }
    throw new Error(`请求失败：HTTP ${res.status}`)
  }
  return (await res.json()) as T
}
