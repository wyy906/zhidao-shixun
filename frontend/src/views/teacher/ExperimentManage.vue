<template>
  <div class="page-container">
    <div class="card">
      <div class="page-header">
        <h2>实验管理</h2>
        <div class="header-actions">
          <el-button @click="downloadTemplate">下载模板</el-button>
          <el-button type="primary" plain @click="openImport">
            <el-icon><Upload /></el-icon>导入实验
          </el-button>
          <el-button type="primary" @click="openDialog()">
            <el-icon><Plus /></el-icon>新建实验
          </el-button>
        </div>
      </div>

      <el-table :data="experiments" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="实验名称" min-width="200" />
        <el-table-column prop="software" label="软件环境" width="160">
          <template #default="{ row }">
            <el-tag size="small">{{ row.software }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_steps" label="步骤数" width="100" />
        <el-table-column prop="progress" label="完成率" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" />
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="截止日期" width="140">
          <template #default="{ row }">{{ fmtDate(row.deadline) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" @click="editExperiment(row)">编辑</el-button>
            <el-button link size="small" @click="manageSteps(row)">步骤管理</el-button>
            <el-button link size="small" type="danger" @click="deleteExperiment(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新建/编辑实验对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑实验' : '新建实验'" width="680px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="实验名称">
          <el-input v-model="form.title" placeholder="请输入实验名称" />
        </el-form-item>
        <el-form-item label="实验类型">
          <el-select v-model="form.type" placeholder="选择类型">
            <el-option label="编程实验" value="python" />
            <el-option label="数据库实验" value="database" />
            <el-option label="数据分析" value="excel" />
            <el-option label="工程仿真" value="simulation" />
          </el-select>
        </el-form-item>
        <el-form-item label="使用软件">
          <el-input v-model="form.software" placeholder="如：MySQL Workbench" />
        </el-form-item>
        <el-form-item label="实验描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="实验目标和内容" />
        </el-form-item>
        <el-form-item label="前置知识">
          <el-input v-model="form.prerequisites" placeholder="逗号分隔，如：SQL 基础,数据库概念" />
        </el-form-item>
        <el-form-item label="完成标准">
          <el-input v-model="form.criteria" type="textarea" :rows="3" placeholder="每行一条" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveExperiment">保存</el-button>
      </template>
    </el-dialog>

    <!-- 导入实验对话框 -->
    <el-dialog v-model="importVisible" title="导入实验" width="760px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="粘贴或上传 JSON 实验包"
        description="实验包包含实验信息、步骤，以及每步的桌面助手定位提示（adapter：目标软件 / 窗口标题 / 关键词）。导入后桌面助手即可选择该实验逐步标注控件。"
      />
      <div class="import-toolbar">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".json,application/json"
          :on-change="onFileChange"
        >
          <el-button>选择 JSON 文件</el-button>
        </el-upload>
        <el-button link type="primary" @click="downloadTemplate">下载模板</el-button>
        <el-checkbox v-model="overwrite">同名实验覆盖</el-checkbox>
      </div>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="15"
        resize="vertical"
        placeholder='{ "version": 1, "experiment": { "title": "..." }, "steps": [ ... ] }'
      />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 步骤查看抽屉 -->
    <el-drawer v-model="stepsVisible" :title="`步骤列表：${stepExp?.title || ''}`" size="540px">
      <div v-loading="stepsLoading">
        <el-empty v-if="!steps.length" description="该实验暂无步骤" />
        <div v-for="(s, i) in steps" :key="s.id" class="step-item">
          <div class="step-title">{{ i + 1 }}. {{ s.title }}</div>
          <div v-if="s.instruction" class="step-line">{{ s.instruction }}</div>
          <div v-if="s.expected_result" class="step-line muted">期望结果：{{ s.expected_result }}</div>
          <div v-if="adapterLabel(s)" class="step-line muted">目标窗口：{{ adapterLabel(s) }}</div>
          <div v-if="s.adapter_hint?.keywords?.length" class="step-line muted">
            定位关键词：{{ s.adapter_hint.keywords.join('、') }}
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  experimentApi,
  type Experiment,
  type ExperimentStep,
  type ExperimentImportPayload
} from '@/api'

const experiments = ref<Experiment[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref<Experiment | null>(null)

// 导入
const importVisible = ref(false)
const importText = ref('')
const overwrite = ref(false)
const importing = ref(false)

// 步骤查看
const stepsVisible = ref(false)
const stepsLoading = ref(false)
const steps = ref<ExperimentStep[]>([])
const stepExp = ref<Experiment | null>(null)
const form = reactive({
  title: '', type: '', software: '', description: '', prerequisites: '', criteria: '', deadline: ''
})

const statusMap: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已归档', type: 'info' },
  not_started: { label: '未开始', type: 'info' },
  in_progress: { label: '进行中', type: 'warning' },
  completed: { label: '已完成', type: 'success' }
}

function statusLabel(s: string) { return statusMap[s]?.label || s }
function statusTagType(s: string) { return statusMap[s]?.type || 'info' }
function fmtDate(d?: string) { return d ? d.slice(0, 10) : '—' }

// 文本与字符串数组互转
function toLines(text: string) {
  return text.split(/[\n,，]/).map((s) => s.trim()).filter(Boolean)
}
function toText(list?: string[]) {
  return (list || []).join('\n')
}

async function loadList() {
  loading.value = true
  try {
    experiments.value = await experimentApi.list()
  } catch {
    experiments.value = []
  } finally {
    loading.value = false
  }
}

function openDialog() {
  editing.value = null
  Object.assign(form, { title: '', type: '', software: '', description: '', prerequisites: '', criteria: '', deadline: '' })
  dialogVisible.value = true
}

async function editExperiment(row: Experiment) {
  editing.value = row
  // 详情接口返回前置知识与完成标准，列表接口没有
  let detail = row
  try {
    detail = await experimentApi.detail(row.id)
  } catch {
    // 详情加载失败时退回列表数据
  }
  Object.assign(form, {
    title: detail.title || '',
    type: detail.type || '',
    software: detail.software || '',
    description: detail.description || '',
    prerequisites: toText(detail.prerequisites),
    criteria: toText(detail.criteria),
    deadline: fmtDate(detail.deadline) === '—' ? '' : fmtDate(detail.deadline)
  })
  dialogVisible.value = true
}

async function saveExperiment() {
  if (!form.title) { ElMessage.warning('请输入实验名称'); return }
  const payload: Partial<Experiment> = {
    title: form.title,
    type: form.type,
    software: form.software,
    description: form.description,
    prerequisites: toLines(form.prerequisites),
    criteria: toLines(form.criteria),
    deadline: form.deadline || undefined
  }
  saving.value = true
  try {
    if (editing.value) {
      await experimentApi.update(editing.value.id, payload)
    } else {
      await experimentApi.create(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadList()
  } catch {
    // 错误已由请求拦截器提示
  } finally {
    saving.value = false
  }
}

async function deleteExperiment(row: Experiment) {
  try {
    await ElMessageBox.confirm(`确定删除"${row.title}"吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await experimentApi.delete(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch {
    // 错误已由请求拦截器提示
  }
}

function manageSteps(row: Experiment) {
  stepExp.value = row
  steps.value = []
  stepsVisible.value = true
  stepsLoading.value = true
  experimentApi
    .steps(row.id)
    .then((list) => (steps.value = list || []))
    .catch(() => (steps.value = []))
    .finally(() => (stepsLoading.value = false))
}

function adapterLabel(s: ExperimentStep) {
  const a = s.adapter_hint || {}
  return a.window_title || a.target_app || ''
}

// ===== 导入实验 =====
const TEMPLATE = {
  version: 1,
  overwrite: false,
  experiment: {
    title: '示例实验：实验名称',
    type: 'python',
    software: '示例软件',
    description: '实验目标与内容说明',
    prerequisites: ['前置知识一'],
    criteria: ['完成标准一'],
    status: 'published'
  },
  steps: [
    {
      title: '第一步标题',
      instruction: '这一步要在目标软件里做什么',
      expected_result: '做完后应该看到什么',
      common_errors: ['常见错误一'],
      adapter: {
        target_app: 'notepad.exe',
        window_title: '记事本',
        keywords: ['保存', '文件'],
        type_hint: 'Button'
      }
    }
  ]
}

function openImport() {
  importText.value = ''
  overwrite.value = false
  importVisible.value = true
}

function onFileChange(file: any) {
  const raw = file?.raw as File | undefined
  if (!raw) return
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = String(reader.result || '')
  }
  reader.readAsText(raw, 'utf-8')
}

function downloadTemplate() {
  const blob = new Blob([JSON.stringify(TEMPLATE, null, 2)], {
    type: 'application/json;charset=utf-8'
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'experiment-template.json'
  a.click()
  URL.revokeObjectURL(url)
}

async function doImport() {
  const text = importText.value.trim()
  if (!text) {
    ElMessage.warning('请先粘贴实验包 JSON 或选择文件')
    return
  }
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch (e: any) {
    ElMessage.error(`JSON 解析失败：${e?.message || '格式不正确'}`)
    return
  }
  if (!parsed?.experiment?.title) {
    ElMessage.error('缺少 experiment.title')
    return
  }
  if (!Array.isArray(parsed.steps) || !parsed.steps.length) {
    ElMessage.error('steps 必须是非空数组')
    return
  }
  const payload: ExperimentImportPayload = {
    version: parsed.version || 1,
    overwrite: overwrite.value,
    experiment: parsed.experiment,
    steps: parsed.steps
  }
  importing.value = true
  try {
    const exp = await experimentApi.importExperiment(payload)
    ElMessage.success(`导入成功：${exp?.title || payload.experiment.title}`)
    importVisible.value = false
    await loadList()
  } catch {
    // 错误已由请求拦截器提示
  } finally {
    importing.value = false
  }
}

onMounted(loadList)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 { margin: 0; font-size: 20px; }
.header-actions { display: flex; align-items: center; gap: 4px; }
.import-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 14px 0 10px;
}
.step-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.step-title { font-weight: 600; margin-bottom: 6px; }
.step-line { font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); }
.step-line.muted { color: var(--el-text-color-secondary); }
</style>
