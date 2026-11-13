import { requestJson } from './client'

export type StepStatusValue = 'pending' | 'in_progress' | 'passed' | 'failed' | 'blocked' | 'skipped'

export interface ProgressResponse {
  experiment_id: string
  states: Record<string, StepStatusValue>
}

export interface SubmitStepResponse {
  run: {
    execution_id: string
    status: 'completed' | 'timeout'
    exit_code: number | null
    stdout: string
    stderr: string
    timed_out: boolean
    truncated: boolean
    duration_ms: number | null
  }
  verify: {
    outcome: 'passed' | 'failed' | 'uncertain'
    confidence: number
    feedback: string
    evidence: Record<string, unknown>
  }
  step_status: StepStatusValue
  states: Record<string, StepStatusValue>
  progressed: boolean
  note: string
  experiment_id: string
  step_id: string
}

export function fetchProgress(experimentId: string): Promise<ProgressResponse> {
  return requestJson<ProgressResponse>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/progress`,
  )
}

export function submitStep(
  experimentId: string,
  stepId: string,
  code: string,
  devToken: string,
  timeoutSeconds = 10,
): Promise<SubmitStepResponse> {
  return requestJson<SubmitStepResponse>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/steps/${encodeURIComponent(stepId)}/submit`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Dev-Token': devToken },
      body: JSON.stringify({ code, timeout_seconds: timeoutSeconds, task_id: `step-${stepId}` }),
    },
  )
}

export function resetProgress(experimentId: string, devToken: string): Promise<ProgressResponse> {
  return requestJson<ProgressResponse>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/progress/reset`,
    { method: 'POST', headers: { 'X-Dev-Token': devToken } },
  )
}
