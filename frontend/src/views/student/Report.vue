<template>
  <div class="page-container" v-loading="loading">
    <div class="card" v-if="experiment">
      <div class="report-header">
        <div>
          <h2>实验报告 - {{ experiment.title }}</h2>
          <el-tag :type="statusTagType(status)">{{ statusLabel(status) }}</el-tag>
          <el-tag v-if="submitted" type="success" style="margin-left: 8px;">已提交</el-tag>
        </div>
        <div class="report-actions">
          <el-button @click="editMode = !editMode">
            <el-icon><Edit /></el-icon>{{ editMode ? '预览' : '编辑' }}
          </el-button>
          <el-button type="primary" :disabled="!editMode" :loading="submitting" @click="submitReport">
            <el-icon><Promotion /></el-icon>提交报告
          </el-button>
        </div>
      </div>

      <el-descriptions :column="2" border class="meta-desc">
        <el-descriptions-item label="实验类型">{{ experiment.type }}</el-descriptions-item>
        <el-descriptions-item label="使用软件">{{ experiment.software }}</el-descriptions-item>
        <el-descriptions-item label="完成步骤">{{ completedSteps }} 步</el-descriptions-item>
        <el-descriptions-item label="完成日期">{{ completedAt || '尚未完成' }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">报告内容</el-divider>

      <div class="report-sections">
        <div class="section" v-for="section in sections" :key="section.key">
          <h3>{{ section.title }}</h3>
          <el-input
            v-if="editMode"
            v-model="report[section.key]"
            type="textarea"
            :rows="4"
            :placeholder="'请输入' + section.title"
          />
          <div v-else class="section-content">
            {{ report[section.key] || '（尚未填写）' }}
          </div>
        </div>

        <div class="section">
          <h3>实验成果截图</h3>
          <div class="screenshots">
            <div v-for="n in 3" :key="n" class="screenshot-placeholder">
              <el-icon :size="36" color="#9ca3af"><Picture /></el-icon>
              <p>截图 {{ n }}（尚未采集）</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else-if="!loading" description="实验不存在或加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { experimentApi, progressApi, reportApi, type Experiment } from '@/api'

type ReportKey = 'purpose' | 'environment' | 'process' | 'result' | 'problems' | 'summary'

const route = useRoute()
const experiment = ref<Experiment | null>(null)
const loading = ref(false)
const submitting = ref(false)
const editMode = ref(false)
const submitted = ref(false)
const status = ref('')
const completedSteps = ref(0)
const completedAt = ref('')

const sections: Array<{ key: ReportKey; title: string }> = [
  { key: 'purpose', title: '实验目的' },
  { key: 'environment', title: '实验环境' },
  { key: 'process', title: '关键操作过程' },
  { key: 'result', title: '实验结果' },
  { key: 'problems', title: '遇到的问题及解决过程' },
  { key: 'summary', title: '实验总结与心得' }
]

const report = reactive<Record<ReportKey, string>>({
  purpose: '', environment: '', process: '', result: '', problems: '', summary: ''
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
function statusTagType(s: string) {
  return statusMap[s]?.type || 'info'
}

async function loadData() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    // 实验基本信息
    try {
      experiment.value = await experimentApi.detail(id)
      status.value = experiment.value.status
    } catch {
      experiment.value = null
      return
    }

    // 学生进度（未开始时会 404，按空处理）
    try {
      const progress = await progressApi.get(id)
      status.value = progress.status
      completedSteps.value = progress.completed_steps
      completedAt.value = progress.completed_at ? progress.completed_at.slice(0, 10) : ''
    } catch {
      completedSteps.value = 0
      completedAt.value = ''
    }

    // 已有报告则回填，404 视为暂无报告
    try {
      const data = await reportApi.get(id)
      if (data) {
        sections.forEach((s) => {
          report[s.key] = data[s.key] ?? ''
        })
        submitted.value = !!data.submitted
      }
    } catch {
      submitted.value = false
    }
  } finally {
    loading.value = false
  }
}

async function submitReport() {
  const id = Number(route.params.id)
  if (!id) return
  submitting.value = true
  try {
    await reportApi.save(id, { ...report })
    await reportApi.submit(id)
    submitted.value = true
    editMode.value = false
    ElMessage.success('报告已提交')
  } catch {
    // 错误已由请求拦截器提示
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.report-header h2 { margin: 0 0 6px; font-size: 20px; }
.meta-desc { margin-bottom: 16px; }
.section { margin-bottom: 20px; }
.section h3 {
  font-size: 15px;
  color: #374151;
  margin: 0 0 10px;
  padding-left: 10px;
  border-left: 3px solid var(--zd-primary);
}
.section-content {
  background: #f9fafb;
  border-radius: 6px;
  padding: 12px 14px;
  min-height: 40px;
  line-height: 1.7;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
}
.screenshots {
  display: flex;
  gap: 12px;
}
.screenshot-placeholder {
  width: 180px;
  height: 120px;
  background: #f3f4f6;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
}
.screenshot-placeholder p { margin: 0; font-size: 12px; color: #6b7280; }
</style>
