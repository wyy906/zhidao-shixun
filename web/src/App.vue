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
import { fetchExecutorStatus, runCode, type ExecutorStatus, type RunResult } from './api/executions'

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

const code = ref("total = sum(range(1, 11))\nprint('hello from sandbox')\nprint('sum 1..10 =', total)")
const running = ref(false)
const runResult = ref<RunResult | null>(null)
const runError = ref<string | null>(null)

const canRun = computed(() =>
  Boolean(devToken.value && executorStatus.value?.docker_environment_ready && selected.value && !running.value),
)

const runBlockedReason = computed(() => {
  if (!selected.value) return '请先选择一个实验'
  if (!devToken.value) return '请先填写开发模式令牌（ZD_DEV_API_TOKEN）'
  if (executorStatus.value && !executorStatus.value.docker_environment_ready) {
    return '执行环境未就绪：Docker 未安装/未启动，或镜像 digest 未批准'
  }
  if (!executorStatus.value && executorStatusError.value) return `执行服务不可达：${executorStatusError.value}`
  return ''
})

async function refreshExecutorStatus() {
  executorStatus.value = null
  executorStatusError.value = null
  runResult.value = null
  runError.value = null
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

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.message}（${e.code}）`
  return e instanceof Error ? e.message : String(e)
}

async function selectExperiment(summary: ExperimentSummary) {
  detailError.value = null
  runResult.value = null
  runError.value = null
  try {
    const resp = await fetchExperiment(summary.experiment_id)
    selected.value = resp.experiment
  } catch (e) {
    selected.value = null
    detailError.value = describe(e)
  }
}

async function submitRun() {
  if (!selected.value || !canRun.value) return
  running.value = true
  runError.value = null
  runResult.value = null
  try {
    runResult.value = await runCode(
      selected.value.experiment_id,
      code.value,
      `web-${Date.now()}`,
      devToken.value,
    )
  } catch (e) {
    runError.value = describe(e)
  } finally {
    running.value = false
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
            <h2>{{ selected.title }}</h2>
            <p>{{ selected.description }}</p>
            <ol class="steps">
              <li v-for="step in selected.steps" :key="step.step_id">
                <strong>{{ step.title }}</strong> — {{ step.student_action }}
                <span class="meta">依赖：{{ step.depends_on.length ? step.depends_on.join(', ') : '无' }}</span>
              </li>
            </ol>
          </div>

          <div class="card">
            <h2>代码编辑器</h2>
            <textarea v-model="code" class="editor" spellcheck="false" />
            <div class="run-row">
              <button class="primary" :disabled="!canRun" @click="submitRun">
                {{ running ? '运行中…' : '运行代码' }}
              </button>
              <span v-if="!canRun && runBlockedReason" class="hint">{{ runBlockedReason }}</span>
            </div>
          </div>

          <div v-if="runResult" class="card" :class="runResult.status === 'completed' && runResult.exit_code === 0 ? 'ok' : 'warn'">
            <h2>运行结果</h2>
            <p class="meta">
              execution_id: {{ runResult.execution_id }} · status: {{ runResult.status }} ·
              exit_code: {{ runResult.exit_code }} · 耗时: {{ runResult.duration_ms }}ms
              <template v-if="runResult.truncated"> · 输出已截断</template>
            </p>
            <h3>stdout</h3>
            <pre class="output">{{ runResult.stdout || '（空）' }}</pre>
            <h3>stderr</h3>
            <pre class="output err-text">{{ runResult.stderr || '（空）' }}</pre>
          </div>
          <div v-if="runError" class="card err">
            <h2>运行请求失败</h2>
            <p>{{ runError }}</p>
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
  margin-left: auto;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: 0.15rem 0.7rem;
  font-size: 0.8rem;
}
.chip.ok { border-color: #16a34a; color: #166534; }
.chip.err { border-color: #dc2626; color: #991b1b; }
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
.token-row { display: flex; gap: 0.5rem; align-items: center; }
.token-row input { flex: 0 1 320px; padding: 0.4rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 6px; }
button {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #f8fafc;
  cursor: pointer;
}
button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
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
.steps { padding-left: 1.2rem; margin: 0.5rem 0 0; }
.editor {
  width: 100%;
  min-height: 180px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 0.85rem;
  padding: 0.6rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  resize: vertical;
  box-sizing: border-box;
}
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
