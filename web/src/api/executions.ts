import { requestJson } from './client'

export interface ExecutorStatus {
  executor_service: string
  engine_available: boolean
  image_digest_locked: boolean
  docker_integration_tests: string
  docker_environment_ready: boolean
}

export interface RunResult {
  execution_id: string
  status: 'completed' | 'timeout'
  exit_code: number | null
  stdout: string
  stderr: string
  timed_out: boolean
  truncated: boolean
  duration_ms: number | null
  experiment_id: string
  task_id: string
}

export function fetchExecutorStatus(devToken: string): Promise<ExecutorStatus> {
  return requestJson<ExecutorStatus>('/api/v1/executor/status', {
    headers: { 'X-Dev-Token': devToken },
  })
}

export function runCode(
  experimentId: string,
  code: string,
  taskId: string,
  devToken: string,
  timeoutSeconds = 10,
): Promise<RunResult> {
  return requestJson<RunResult>(`/api/v1/experiments/${encodeURIComponent(experimentId)}/runs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Dev-Token': devToken,
    },
    body: JSON.stringify({ code, timeout_seconds: timeoutSeconds, task_id: taskId }),
  })
}
