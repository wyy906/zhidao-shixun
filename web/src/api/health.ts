export interface HealthResponse {
  status: string
  app: string
  app_env: string
  api_version: string
  contract_version: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/health')
  if (!res.ok) {
    throw new Error(`健康检查失败：HTTP ${res.status}`)
  }
  return (await res.json()) as HealthResponse
}
