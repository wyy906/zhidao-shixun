import { requestJson } from './client'

export interface ExperimentSummary {
  experiment_id: string
  title: string
  category: string
  version: string
  environment: string
  step_count: number
  estimated_minutes: number
  difficulty: string
}

export interface StepView {
  step_id: string
  title: string
  learning_goal: string
  student_action: string
  depends_on: string[]
  guide_hint: number
}

export interface ExperimentDetail {
  experiment_id: string
  title: string
  description: string
  category: string
  version: string
  environment: string
  prerequisites: string[]
  steps: StepView[]
}

export interface ExperimentListResponse {
  experiments: ExperimentSummary[]
  issues_count: number
}

export function fetchExperiments(): Promise<ExperimentListResponse> {
  return requestJson<ExperimentListResponse>('/api/v1/experiments')
}

export function fetchExperiment(experimentId: string): Promise<{ experiment: ExperimentDetail }> {
  return requestJson<{ experiment: ExperimentDetail }>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}`,
  )
}
