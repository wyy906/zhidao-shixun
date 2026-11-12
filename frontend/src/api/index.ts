import { get, post, put, del } from '@/utils/request'

// ===== 实验任务 =====
export interface Experiment {
  id: number
  title: string
  description: string
  type: string
  software: string
  // 后端可能返回教师侧状态（draft/published/archived）或学生学习状态
  status: string
  progress: number
  total_steps: number
  completed_steps: number
  created_at: string
  deadline?: string
  prerequisites?: string[]
  criteria?: string[]
}

export interface ExperimentStep {
  id: number
  order_index: number
  title: string
  instruction?: string
  expected_result?: string
  common_errors?: string[]
  // 桌面助手定位提示：{ target_app, window_title, keywords, type_hint }
  adapter_hint?: Record<string, any>
}

export interface ExperimentImportPayload {
  version?: number
  overwrite?: boolean
  experiment: Partial<Experiment>
  steps: Array<{
    title: string
    instruction?: string
    expected_result?: string
    common_errors?: string[]
    adapter?: Record<string, any>
  }>
}

export const experimentApi = {
  list: () => get<Experiment[]>('/v1/experiments'),
  detail: (id: number) => get<Experiment>(`/v1/experiments/${id}`),
  steps: (id: number) => get<ExperimentStep[]>(`/v1/experiments/${id}/steps`),
  create: (data: Partial<Experiment>) => post<Experiment>('/v1/experiments', data),
  update: (id: number, data: Partial<Experiment>) => put<Experiment>(`/v1/experiments/${id}`, data),
  delete: (id: number) => del(`/v1/experiments/${id}`),
  start: (id: number) => post(`/v1/experiments/${id}/start`),
  submit: (id: number) => post(`/v1/experiments/${id}/submit`),
  importExperiment: (payload: ExperimentImportPayload) =>
    post<Experiment>('/v1/experiments/import', payload)
}

// ===== 实验进度 =====
export interface ExperimentProgress {
  id?: number
  experiment_id: number
  current_step: number
  completed_steps: number
  status: string
  started_at?: string
  last_active_at?: string
  completed_at?: string
}

export const progressApi = {
  // 未开始实验时后端返回 404，静默处理
  get: (experimentId: number) =>
    get<ExperimentProgress>(`/v1/progress/${experimentId}`, { skipErrorMessage: true }),
  update: (experimentId: number, data: Partial<ExperimentProgress>) =>
    put<ExperimentProgress>(`/v1/progress/${experimentId}`, data)
}

// ===== 实验报告 =====
export interface ExperimentReport {
  id?: number
  purpose: string
  environment: string
  process: string
  result: string
  problems: string
  summary: string
  submitted?: boolean
  updated_at?: string
}

export const reportApi = {
  // 还没有报告时后端返回 404，静默处理
  get: (experimentId: number) =>
    get<ExperimentReport | null>(`/v1/experiments/${experimentId}/report`, {
      skipErrorMessage: true
    }),
  save: (experimentId: number, data: Omit<ExperimentReport, 'id' | 'submitted' | 'updated_at'>) =>
    put<ExperimentReport>(`/v1/experiments/${experimentId}/report`, data),
  submit: (experimentId: number) =>
    post<{ ok: boolean; submitted: boolean }>(`/v1/experiments/${experimentId}/report/submit`)
}

// ===== AI 指导引擎 =====
export interface AIGuideRequest {
  experiment_id: number
  current_step: number
  context?: Record<string, any>
  screen_state?: Record<string, any>
}

export interface AIGuideResponse {
  level: 'brief' | 'annotate' | 'detailed' | 'demo'
  instruction: string
  target?: { x: number; y: number; width: number; height: number; label: string }
  expected_result: string
  common_errors?: string[]
  next_action?: string
}

export const aiApi = {
  requestGuide: (data: AIGuideRequest) =>
    post<AIGuideResponse>('/v1/ai/guide', data),
  verifyResult: (experimentId: number, stepId: number, data: any) =>
    post<{ passed: boolean; feedback: string }>(
      `/v1/ai/verify/${experimentId}/${stepId}`,
      data
    ),
  diagnoseError: (experimentId: number, data: any) =>
    post<{ error_type: string; suggestion: string }>(
      `/v1/ai/diagnose/${experimentId}`,
      data
    )
}

// ===== 网页端代码运行 =====
export interface CodeRunResult {
  stdout: string
  stderr: string
  exit_code: number
  duration_ms: number
  timed_out: boolean
}

export const codeApi = {
  run: (code: string, timeout = 15) =>
    post<CodeRunResult>('/v1/code/run', { code, timeout })
}

// ===== 教师分析 =====
export interface ClassAnalytics {
  total_students: number
  total_experiments: number
  completed_count: number
  in_progress_count: number
  completion_rate: number
}

export interface StudentAnalytics {
  id: number
  name: string
  class_name?: string
  total_progresses: number
  completed_count: number
  in_progress_count: number
}

export const analyticsApi = {
  overview: () => get<ClassAnalytics>('/v1/analytics/overview'),
  studentList: () => get<StudentAnalytics[]>('/v1/analytics/students'),
  experimentStats: (experimentId: number) =>
    get<any>(`/v1/analytics/experiments/${experimentId}`)
}
