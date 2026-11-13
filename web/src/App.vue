<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchHealth, type HealthResponse } from './api/health'
import { ApiError } from './api/client'
import {
  fetchExperiment,
  fetchExperiments,
  type ExperimentDetail,
  type ExperimentSummary,
} from './api/experiments'
import { fetchExecutorStatus, type ExecutorStatus } from './api/executions'
import {
  fetchProgress,
  resetProgress,
  submitStep,
  type StepStatusValue,
  type SubmitStepResponse,
} from './api/progress'
import CodeEditor from './components/CodeEditor.vue'

const DEV_TOKEN_KEY = 'zd_dev_token'

const health = ref<HealthResponse | null>(null)
const healthError = ref<string | null>(null)

const devToken = ref(localStorage.getItem(DEV_TOKEN_KEY) ?? '')
const devTokenSaved = ref(false)

const executorStatus = ref<ExecutorStatus | null>(null)
const executorStatusError = ref<string | null>(null)

const experiments = ref<ExperimentSummary[]>([])
const issuesCount = ref(0)
const listError = ref<string | null>(null)
const selected = ref<ExperimentDetail | null>(null)
const detailError = ref<string | null>(null)

const activeStepId = ref<string | null>(null)
const stepStates = ref<Record<string, StepStatusValue>>({})
const stepCodes = ref<Record<string, string>>({})
const code = ref('')
const submitting = ref(false)
const lastSubmit = ref<SubmitStepResponse | null>(null)
const submitError = ref<string | null>(null)

const STATUS_LABELS: Record<string, string> = {
  pending: '待开始',
  in_progress: '进行中',
  passed: '已通过',
  failed: '未通过',
  blocked: '被阻塞',
  skipped: '已跳过',
}

function statusClass(status: string): string {
  return `status-${status}`
}

const activeStep = computed(() =>
  selected.value?.steps.find((step) => step.step_id === activeStepId.value) ?? null,
)

const activeStepStatus = computed(() =>
  activeStepId.value ? stepStates.value[activeStepId.value] ?? 'pending' : null,
)

const canSubmit = computed(() =>
  Boolean(devToken.value && executorStatus.value?.docker_environment_ready && activeStep.value && !submitting.value),
)

const submitBlockedReason = computed(() => {
  if (!selected.value) return '请先选择一个实验'
  if (!devToken.value) return '请先填写开发模式令牌（ZD_DEV_API_TOKEN）'
  if (executorStatus.value && !executorStatus.value.docker_environment_ready) {
    return '执行环境未就绪：Docker 未安装/未启动，或镜像 digest 未批准'
  }
  if (!executorStatus.value && executorStatusError.value) return `执行服务不可达：${executorStatusError.value}`
  if (activeStepStatus.value === 'blocked') return '该步骤依赖未全部通过，暂不能运行'
  if (activeStepStatus.value === 'passed' || activeStepStatus.value === 'skipped') {
    return '该步骤已是终态'
  }
  return ''
})

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.message}（${e.code}）`
  return e instanceof Error ? e.message : String(e)
}

async function refreshExecutorStatus() {
  executorStatus.value = null
  executorStatusError.value = null
  lastSubmit.value = null
  submitError.value = null
  if (!devToken.value) return
  try {
    executorStatus.value = await fetchExecutorStatus(devToken.value)
  } catch (e) {
    executorStatusError.value = describe(e)
  }
}

function saveToken() {
  localStorage.setItem(DEV_TOKEN_KEY, devToken.value)
  devTokenSaved.value = true
  setTimeout(() => (devTokenSaved.value = false), 1500)
  void refreshExecutorStatus()
}

function selectStep(stepId: string) {
  activeStepId.value = stepId
  code.value = stepCodes.value[stepId] ?? ''
  lastSubmit.value = null
  submitError.value = null
}

async function refreshProgress(experimentId: string) {
  try {
    const resp = await fetchProgress(experimentId)
    stepStates.value = resp.states
  } catch {
    /* 进度读取失败不阻塞编辑，按钮原因会提示环境问题 */
  }
}

async function selectExperiment(summary: ExperimentSummary) {
  detailError.value = null
  lastSubmit.value = null
  submitError.value = null
  stepCodes.value = {}
  try {
    const resp = await fetchExperiment(summary.experiment_id)
    selected.value = resp.experiment
    await refreshProgress(resp.experiment.experiment_id)
    const firstOpen =
      resp.experiment.steps.find(
        (s) => {
          const st = stepStates.value[s.step_id] ?? 'pending'
          return st !== 'passed' && st !== 'skipped'
        },
      ) ?? resp.experiment.steps[0]
    selectStep(firstOpen.step_id)
  } catch (e) {
    selected.value = null
    detailError.value = describe(e)
  }
}

function onCodeInput(value: string) {
  code.value = value
  if (activeStepId.value) stepCodes.value[activeStepId.value] = value
}

async function runActiveStep() {
  if (!selected.value || !activeStep.value || !canSubmit.value) return
  submitting.value = true
  submitError.value = null
  lastSubmit.value = null
  try {
    lastSubmit.value = await submitStep(
      selected.value.experiment_id,
      activeStep.value.step_id,
      code.value,
      devToken.value,
    )
    stepStates.value = lastSubmit.value.states
  } catch (e) {
    submitError.value = describe(e)
  } finally {
    submitting.value = false
  }
}

async function resetExperimentProgress() {
  if (!selected.value || !devToken.value) return
  submitError.value = null
  try {
    const resp = await resetProgress(selected.value.experiment_id, devToken.value)
    stepStates.value = resp.states
    lastSubmit.value = null
    const firstOpen =
      selected.value.steps.find((s) => {
        const st = stepStates.value[s.step_id] ?? 'pending'
        return st !== 'passed' && st !== 'skipped'
      }) ?? selected.value.steps[0]
    selectStep(firstOpen.step_id)
  } catch (e) {
    submitError.value = describe(e)
  }
}

onMounted(async () => {
  try {
    health.value = await fetchHealth()
  } catch (e) {
    healthError.value = describe(e)
  }
  try {
    const resp = await fetchExperiments()
    experiments.value = resp.experiments
    issuesCount.value = resp.issues_count
    if (resp.experiments.length > 0) {
      await selectExperiment(resp.experiments[0])
    }
  } catch (e) {
    listError.value = describe(e)
  }
  await refreshExecutorStatus()
})
</script>

<template>
  <main class="page">
    <header class="header">
      <div>
        <h1>智导实训 V2</h1>
        <p class="subtitle">AI 视觉感知与实时操作引导平台 · Python 实验工作台</p>
      </div>
      <span v-if="health" class="chip ok">后端正常 · {{ health.app_env }}</span>
      <span v-else-if="healthError" class="chip err">后端未连接</span>
      <span v-else class="chip">连接中…</span>
    </header>

    <section class="card">
      <h2>开发模式令牌</h2>
      <p class="hint">
        运行接口当前为开发/受控测试模式：填入主 API 配置的 <code>ZD_DEV_API_TOKEN</code>（仅保存在本浏览器，
        仅限本机开发使用；正式用户体系上线后此栏将被替换）。
      </p>
      <div class="token-row">
        <input
          v-model="devToken"
          type="password"
          placeholder="ZD_DEV_API_TOKEN"
          @keyup.enter="saveToken"
        />
        <button @click="saveToken">保存并检测</button>
        <span v-if="devTokenSaved" class="hint">已保存</span>
      </div>
    </section>

    <section v-if="executorStatus" class="card" :class="executorStatus.docker_environment_ready ? 'ok' : 'warn'">
      <h2>执行环境</h2>
      <ul>
        <li>执行服务：{{ executorStatus.executor_service }}</li>
        <li>Docker 引擎：{{ executorStatus.engine_available ? '可用' : '不可用' }}</li>
        <li>镜像 digest：{{ executorStatus.image_digest_locked ? '已锁定' : '未锁定（pending）' }}</li>
        <li>真实 Docker 集成测试：{{ executorStatus.docker_integration_tests }}</li>
      </ul>
      <p v-if="!executorStatus.docker_environment_ready" class="hint">
        当前无法真实执行代码：请安装并启动 Docker Desktop，配置已批准镜像 digest 后重启执行服务。
      </p>
    </section>
    <section v-else-if="executorStatusError" class="card err">
      <h2>执行服务不可达</h2>
      <p>{{ executorStatusError }}</p>
      <p class="hint">请运行 scripts/start-executor-service.ps1 启动独立执行服务（需 ZD_EXECUTOR_TOKEN）。</p>
    </section>

    <div class="layout">
      <aside class="card">
        <h2>实验列表</h2>
        <p v-if="listError" class="hint">{{ listError }}</p>
        <p v-else-if="experiments.length === 0" class="hint">
          暂无实验：请将实验定义 JSON 放入仓库根目录 experiments/ 后刷新。
        </p>
        <ul class="exp-list">
          <li
            v-for="item in experiments"
            :key="item.experiment_id"
            :class="{ active: selected?.experiment_id === item.experiment_id }"
            @click="selectExperiment(item)"
          >
            <strong>{{ item.title }}</strong>
            <span class="meta">{{ item.environment }} · {{ item.step_count }} 步 · {{ item.estimated_minutes }} 分钟</span>
          </li>
        </ul>
        <p v-if="issuesCount > 0" class="hint">注意：{{ issuesCount }} 个实验文件未通过加载校验，已排除。</p>
      </aside>

      <section class="workspace">
        <div v-if="detailError" class="card err">{{ detailError }}</div>
        <template v-if="selected">
          <div class="card">
            <div class="title-row">
              <h2>{{ selected.title }}</h2>
              <button class="small" @click="resetExperimentProgress">重置进度</button>
            </div>
            <p>{{ selected.description }}</p>
            <ol class="steps">
              <li
                v-for="step in selected.steps"
                :key="step.step_id"
                :class="{ active: step.step_id === activeStepId }"
                @click="selectStep(step.step_id)"
              >
                <div class="step-line">
                  <strong>{{ step.title }}</strong>
                  <span class="chip" :class="statusClass(stepStates[step.step_id] ?? 'pending')">
                    {{ STATUS_LABELS[stepStates[step.step_id] ?? 'pending'] }}
                  </span>
                </div>
                <span class="meta">{{ step.student_action }}</span>
              </li>
            </ol>
            <p class="hint">进度为进程内存态，服务重启后重置（开发/受控测试模式）。</p>
          </div>

          <div class="card">
            <h2>
              代码编辑器
              <span v-if="activeStep" class="meta">（{{ activeStep.title }}）</span>
            </h2>
            <p v-if="activeStep" class="hint">本步学习目标：{{ activeStep.learning_goal }}</p>
            <CodeEditor v-model="code" @update:model-value="onCodeInput" />
            <div class="run-row">
              <button class="primary" :disabled="!canSubmit" @click="runActiveStep">
                {{ submitting ? '运行中…' : '运行并验证此步' }}
              </button>
              <span v-if="!canSubmit && submitBlockedReason" class="hint">{{ submitBlockedReason }}</span>
            </div>
          </div>

          <div v-if="lastSubmit" class="card" :class="lastSubmit.verify.outcome === 'passed' ? 'ok' : 'warn'">
            <h2>运行与验证结果</h2>
            <p class="meta">
              execution_id: {{ lastSubmit.run.execution_id }} · status: {{ lastSubmit.run.status }} ·
              exit_code: {{ lastSubmit.run.exit_code }} · 耗时: {{ lastSubmit.run.duration_ms }}ms
              <template v-if="lastSubmit.run.truncated"> · 输出已截断</template>
            </p>
            <p>
              验证判定：
              <strong :class="lastSubmit.verify.outcome === 'passed' ? 'pass-text' : 'fail-text'">
                {{ lastSubmit.verify.outcome }}
              </strong>
              — {{ lastSubmit.verify.feedback }}
              <span class="meta">
                （步骤状态：{{ STATUS_LABELS[lastSubmit.step_status] ?? lastSubmit.step_status }}）
              </span>
            </p>
            <h3>stdout</h3>
            <pre class="output">{{ lastSubmit.run.stdout || '（空）' }}</pre>
            <h3>stderr</h3>
            <pre class="output err-text">{{ lastSubmit.run.stderr || '（空）' }}</pre>
          </div>
          <div v-if="submitError" class="card err">
            <h2>提交失败</h2>
            <p>{{ submitError }}</p>
          </div>
        </template>
      </section>
    </div>
  </main>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
  font-family: system-ui, 'Microsoft YaHei', sans-serif;
  color: #0f172a;
}
.header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  flex-wrap: wrap;
}
.header h1 { margin: 0; font-size: 1.4rem; }
.subtitle { color: #64748b; margin: 0.2rem 0 0; }
.chip {
  display: inline-block;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 0.1rem 0.6rem;
  font-size: 0.75rem;
  white-space: nowrap;
}
.chip.ok, .chip.passed { border-color: #16a34a; color: #166534; }
.chip.err, .chip.failed { border-color: #dc2626; color: #991b1b; }
.chip.in_progress { border-color: #2563eb; color: #1e40af; }
.chip.blocked { border-color: #d97706; color: #92400e; }
.card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-top: 1.25rem;
  background: #fff;
}
.card.ok { border-color: #16a34a; }
.card.warn { border-color: #d97706; }
.card.err { border-color: #dc2626; }
.card h2 { margin: 0 0 0.5rem; font-size: 1.05rem; }
.card h3 { margin: 0.75rem 0 0.25rem; font-size: 0.9rem; color: #475569; }
.hint { color: #64748b; font-size: 0.85rem; margin: 0.35rem 0; }
.meta { color: #64748b; font-size: 0.8rem; }
.pass-text { color: #166534; }
.fail-text { color: #991b1b; }
.title-row { display: flex; justify-content: space-between; align-items: center; }
button {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #f8fafc;
  cursor: pointer;
}
button.small { font-size: 0.8rem; padding: 0.25rem 0.6rem; }
button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.token-row { display: flex; gap: 0.5rem; align-items: center; }
.token-row input { flex: 0 1 320px; padding: 0.4rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.layout { display: grid; grid-template-columns: 280px 1fr; gap: 1.25rem; align-items: start; }
.exp-list { list-style: none; margin: 0.5rem 0 0; padding: 0; }
.exp-list li {
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.exp-list li:hover { background: #f1f5f9; }
.exp-list li.active { background: #dbeafe; }
.steps { padding-left: 1.2rem; margin: 0.5rem 0 0; display: flex; flex-direction: column; gap: 0.4rem; }
.steps li { cursor: pointer; border-radius: 6px; padding: 0.35rem 0.5rem; display: flex; flex-direction: column; gap: 0.2rem; }
.steps li:hover { background: #f1f5f9; }
.steps li.active { background: #dbeafe; }
.step-line { display: flex; justify-content: space-between; gap: 0.5rem; align-items: center; }
.run-row { display: flex; align-items: center; gap: 0.75rem; margin-top: 0.6rem; }
.output {
  background: #0f172a;
  color: #e2e8f0;
  padding: 0.6rem 0.8rem;
  border-radius: 6px;
  font-size: 0.8rem;
  min-height: 1.2rem;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0.25rem 0 0;
}
.err-text { color: #fca5a5; }
</style>
