<template>
  <div class="workbench" v-loading="loading">
    <!-- 顶部实验信息栏 -->
    <div class="wb-header">
      <div class="wb-title">
        <el-icon :size="20"><VideoPlay /></el-icon>
        <span>{{ experiment?.title }}</span>
      </div>
      <div class="wb-info">
        <el-tag size="small" type="warning">进行中</el-tag>
        <span>步骤 {{ Math.min(currentStep + 1, steps.length) }} / {{ steps.length }}</span>
        <el-tag size="small" type="primary">AI 助手：{{ guideLevelLabel }}</el-tag>
        <el-button size="small" @click="showAssistant = !showAssistant">
          {{ showAssistant ? '隐藏助手' : '显示助手' }}
        </el-button>
      </div>
    </div>

    <div class="wb-body">
      <!-- 左侧：步骤进度 -->
      <div class="wb-sidebar">
        <h4 class="sidebar-title">实验步骤</h4>
        <div class="step-list">
          <div
            v-for="(step, idx) in steps"
            :key="step.id"
            class="step-item"
            :class="{ active: idx === currentStep, done: idx < currentStep }"
            @click="goStep(idx)"
          >
            <div class="step-num">{{ idx + 1 }}</div>
            <div class="step-content">
              <div class="step-title">{{ step.title }}</div>
              <div class="step-status">
                <el-icon v-if="idx < currentStep" color="#22c55e"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="idx === currentStep" color="#f59e0b"><Loading /></el-icon>
                <span v-else>待执行</span>
              </div>
            </div>
          </div>
        </div>

        <div class="wb-actions">
          <el-button size="small" :disabled="currentStep === 0" @click="prevStep">
            <el-icon><ArrowLeft /></el-icon>上一步
          </el-button>
          <el-button size="small" type="primary" @click="nextStep">
            下一步<el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 中间：网页实验环境 -->
      <div class="wb-center">
        <!-- AI 指导卡片 -->
        <div class="ai-guide-card" v-if="currentGuide">
          <div class="guide-header">
            <div class="guide-level-badge" :class="'level-' + currentGuide.level">
              {{ guideLevelLabel }}
            </div>
            <span class="guide-step">当前步骤 {{ currentStep + 1 }}</span>
          </div>
          <div class="guide-body">
            <el-icon :size="20" color="#4f6ef7"><MagicStick /></el-icon>
            <p>{{ currentGuide.instruction }}</p>
          </div>
          <div class="guide-target" v-if="currentGuide.target">
            <div class="target-label">🎯 操作目标</div>
            <code>{{ currentGuide.target.label }}</code>
          </div>
          <div class="guide-tip">
            <strong>预期结果：</strong>{{ currentGuide.expected_result }}
          </div>
          <div class="guide-promo">
            <el-icon><InfoFilled /></el-icon>
            请按照以上指导在对应软件中完成操作，AI 助手会自动识别你的操作状态。
            <el-button type="primary" link size="small" @click="requestGuide">重新获取指导</el-button>
          </div>
        </div>

        <!-- 代码编辑器 (Python 实验时显示) -->
        <div class="code-editor-area" v-if="experiment?.type === 'python'">
          <div class="editor-header">
            <span>
              main.py
              <em class="editor-hint">Python · 可直接运行</em>
            </span>
            <div>
              <el-button size="small" :loading="running" @click="runCode">
                <el-icon><VideoPlay /></el-icon>运行
              </el-button>
              <el-button size="small" :disabled="running" @click="resetCode">重置</el-button>
            </div>
          </div>
          <div ref="editorEl" class="editor-host"></div>
          <div class="run-output">
            <div class="output-title">
              运行结果
              <span v-if="runMs">· 耗时 {{ runMs }} ms</span>
            </div>
            <pre v-if="runOutput" :class="{ err: runIsError }">{{ runOutput }}</pre>
            <pre v-else class="output-empty">（点击「运行」查看结果）</pre>
          </div>
        </div>

        <!-- 外部软件实验提示 -->
        <div class="external-hint" v-else>
          <el-icon :size="56" color="#4f6ef7"><Monitor /></el-icon>
          <h3>请打开 {{ experiment?.software }}</h3>
          <p>AI 桌面助手会在你的软件界面上实时标注操作目标。</p>
          <el-button type="primary" @click="openDesktopHelper">
            <el-icon><Promotion /></el-icon>启动桌面助手
          </el-button>
          <div class="helper-tip">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                电脑端助手需要单独启动。请运行 desktop/src/main.py，它会自动连接后端并开始观察你的操作屏幕。
              </template>
            </el-alert>
          </div>
        </div>
      </div>

      <!-- 右侧：AI 助手面板 -->
      <div class="wb-right" v-if="showAssistant">
        <div class="right-header">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 助手</span>
        </div>
        <div class="chat-area">
          <div class="msg ai">
            <div class="avatar">AI</div>
            <div class="bubble">
              桌面助手连接后，会识别你当前窗口的控件并标注下一步操作位置；在线对话功能尚未开放。
            </div>
          </div>
          <div class="msg user" v-for="(m, i) in messages" :key="i">
            <div class="bubble">{{ m }}</div>
          </div>
        </div>
        <div class="chat-input">
          <el-input
            v-model="chatInput"
            placeholder="向 AI 提问..."
            @keyup.enter="sendChat"
          />
          <el-button type="primary" @click="sendChat">
            <el-icon><Promotion /></el-icon>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import {
  experimentApi, aiApi, codeApi,
  type Experiment, type ExperimentStep, type AIGuideResponse
} from '@/api'

// Monaco 只用到编辑器基础 worker（Python 语法高亮不需要额外语言服务）
;(self as any).MonacoEnvironment = {
  getWorker: () => new EditorWorker()
}

const route = useRoute()
const loading = ref(false)
const showAssistant = ref(true)
const chatInput = ref('')
const messages = ref<string[]>([])
const runOutput = ref('')
const runMs = ref(0)
const runIsError = ref(false)
const running = ref(false)
const editorEl = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null

const DEFAULT_CODE = `# 在这里编写 Python 代码
# 写好之后点右上角「运行」，输出会显示在下方
print("Hello, 智导实训")
`

const experiment = ref<Experiment | null>(null)
const steps = ref<ExperimentStep[]>([])
const currentStep = ref(0)
const currentGuide = ref<AIGuideResponse | null>(null)

const guideLevelLabel = computed(() => {
  const map: Record<string, string> = {
    brief: '简洁提示', annotate: '屏幕标注', detailed: '详细解释', demo: '局部示范'
  }
  return map[currentGuide.value?.level || 'brief'] || '简洁提示'
})

async function loadData() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    experiment.value = await experimentApi.detail(id)
    steps.value = await experimentApi.steps(id)
    currentStep.value = 0
  } catch {
    // 加载失败保持空数据
    experiment.value = null
    steps.value = []
    currentStep.value = 0
  } finally {
    loading.value = false
  }
  if (experiment.value?.type === 'python') {
    await nextTick()
    initEditor()
  }
  await requestGuide()
}

async function requestGuide() {
  if (!experiment.value) return
  try {
    currentGuide.value = await aiApi.requestGuide({
      experiment_id: experiment.value.id,
      current_step: currentStep.value
    })
  } catch {
    // 获取指导失败时不伪造内容
    currentGuide.value = null
  }
}

function goStep(idx: number) { currentStep.value = idx; requestGuide() }
function prevStep() { if (currentStep.value > 0) { currentStep.value--; requestGuide() } }
function nextStep() {
  if (currentStep.value < steps.value.length - 1) {
    currentStep.value++; requestGuide()
  }
}
function extractStarterCode(): string {
  // 优先从步骤说明里提取示例代码（例如「把下面的代码输入记事本」那段）
  for (const s of steps.value) {
    const lines = (s.instruction || '').split('\n')
    const start = lines.findIndex((l) => /^\s*(import|from|def|class)\s/.test(l))
    if (start < 0) continue
    const code: string[] = []
    for (let i = start; i < lines.length; i++) {
      const line = lines[i]
      if (/^\s*(说明|注意|提示|期望)/.test(line)) break
      code.push(line)
    }
    const text = code.join('\n').trim()
    if (text) return text + '\n'
  }
  return DEFAULT_CODE
}

function initEditor() {
  if (!editorEl.value || editor) return
  editor = monaco.editor.create(editorEl.value, {
    value: extractStarterCode(),
    language: 'python',
    theme: 'vs-dark',
    fontSize: 14,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false,
    tabSize: 4,
    wordWrap: 'on'
  })
}

async function runCode() {
  if (!editor || running.value) return
  const code = editor.getValue()
  if (!code.trim()) {
    ElMessage.warning('请先写一点代码再运行')
    return
  }
  running.value = true
  runOutput.value = ''
  runIsError.value = false
  try {
    const res = await codeApi.run(code, 20)
    runMs.value = res.duration_ms
    const parts: string[] = []
    if (res.stdout) parts.push(res.stdout.trimEnd())
    if (res.stderr) parts.push(res.stderr.trimEnd())
    runOutput.value = parts.join('\n') || '（无输出）'
    runIsError.value = res.exit_code !== 0 || res.timed_out
  } catch {
    runOutput.value = '运行失败：请检查后端服务是否可用'
    runIsError.value = true
  } finally {
    running.value = false
  }
}

function resetCode() {
  if (!editor) return
  editor.setValue(extractStarterCode())
  runOutput.value = ''
  runMs.value = 0
  runIsError.value = false
}
function openDesktopHelper() {
  ElMessage.info('请在命令行运行：python desktop/src/main.py')
}
function sendChat() {
  if (!chatInput.value.trim()) return
  messages.value.push(chatInput.value)
  chatInput.value = ''
  // 在线 AI 对话尚未接入，不做伪造回复
  ElMessage.info('AI 对话服务尚未接入，请使用桌面助手获取实时指导')
}

onBeforeUnmount(() => {
  editor?.dispose()
  editor = null
})

onMounted(loadData)
</script>

<style scoped>
.workbench {
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
}
.wb-header {
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.wb-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
}
.wb-info {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: #6b7280;
}
.wb-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.wb-sidebar {
  width: 260px;
  background: #fff;
  border-right: 1px solid #e5e7eb;
  padding: 16px;
  display: flex;
  flex-direction: column;
}
.sidebar-title {
  margin: 0 0 12px;
  font-size: 14px;
  color: #374151;
}
.step-list {
  flex: 1;
  overflow-y: auto;
}
.step-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s;
}
.step-item:hover { background: #f3f4f6; }
.step-item.active { background: #eef1fe; border: 1px solid #c7d2fe; }
.step-item.done .step-title { color: #22c55e; }
.step-num {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.step-item.active .step-num { background: var(--zd-primary); color: #fff; }
.step-item.done .step-num { background: #22c55e; color: #fff; }
.step-content { flex: 1; min-width: 0; }
.step-title {
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-status { font-size: 11px; color: #6b7280; margin-top: 2px; }
.wb-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}
.wb-actions .el-button { flex: 1; }

.wb-center {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}
.ai-guide-card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 16px;
  border-left: 4px solid var(--zd-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.guide-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.guide-level-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.guide-level-badge.level-brief { background: #eef1fe; color: #4f6ef7; }
.guide-level-badge.level-annotate { background: #fffbeb; color: #f59e0b; }
.guide-level-badge.level-detailed { background: #f5f3ff; color: #7c3aed; }
.guide-level-badge.level-demo { background: #fef2f2; color: #ef4444; }
.guide-step { color: #6b7280; font-size: 13px; }
.guide-body {
  display: flex;
  gap: 10px;
  font-size: 15px;
  line-height: 1.6;
  color: #1f2937;
  margin-bottom: 12px;
}
.guide-body p { margin: 0; }
.guide-target {
  background: #f0fdf4;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.target-label { font-size: 12px; color: #16a34a; margin-bottom: 4px; }
.guide-target code {
  background: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
}
.guide-tip {
  font-size: 13px;
  color: #4b5563;
  margin-bottom: 12px;
}
.guide-promo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  background: #f9fafb;
  padding: 10px 12px;
  border-radius: 8px;
}

.code-editor-area {
  background: #1e1e1e;
  border-radius: 12px;
  overflow: hidden;
  color: #d4d4d4;
}
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: #2d2d2d;
  border-bottom: 1px solid #3c3c3c;
}
.editor-header span { font-size: 13px; color: #9ca3af; }
.editor-hint {
  font-style: normal;
  font-size: 11px;
  color: #6b7280;
  margin-left: 10px;
}
.editor-host { height: 340px; }
.run-output {
  background: #0d1117;
  padding: 12px 16px;
  border-top: 1px solid #3c3c3c;
}
.output-title {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 6px;
}
.run-output pre {
  margin: 0;
  font-family: 'Consolas', monospace;
  font-size: 13px;
  color: #58a6ff;
  white-space: pre-wrap;
}
.run-output pre.err { color: #f87171; }
.run-output pre.output-empty { color: #8b949e; }

.external-hint {
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
}
.external-hint h3 { margin: 12px 0 6px; font-size: 18px; }
.external-hint p { margin: 0 0 20px; color: #6b7280; }
.helper-tip { margin-top: 20px; }

.wb-right {
  width: 320px;
  background: #fff;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}
.right-header {
  padding: 14px 16px;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg { display: flex; gap: 8px; }
.msg.ai { justify-content: flex-start; }
.msg.user { justify-content: flex-end; }
.msg.ai .avatar {
  width: 32px; height: 32px;
  background: linear-gradient(135deg, #4f6ef7, #7c3aed);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.msg.ai .bubble {
  background: #f3f4f6;
  padding: 10px 12px;
  border-radius: 12px;
  border-top-left-radius: 2px;
  font-size: 13px;
  max-width: 80%;
}
.msg.user .bubble {
  background: var(--zd-primary);
  color: #fff;
  padding: 10px 12px;
  border-radius: 12px;
  border-top-right-radius: 2px;
  font-size: 13px;
  max-width: 80%;
}
.chat-input {
  display: flex;
  gap: 6px;
  padding: 12px;
  border-top: 1px solid #e5e7eb;
}
</style>
