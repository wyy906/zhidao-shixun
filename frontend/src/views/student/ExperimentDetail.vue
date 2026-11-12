<template>
  <div class="page-container" v-loading="loading">
    <template v-if="experiment">
      <div class="card exp-header">
        <div class="header-left">
          <el-tag size="large" :type="statusTagType(statusKey)">
            {{ statusLabel(statusKey) }}
          </el-tag>
          <h2>{{ experiment.title }}</h2>
          <div class="meta">
            <el-tag type="info" size="small">{{ experiment.software }}</el-tag>
            <span>步骤 {{ completedSteps }}/{{ totalSteps }}</span>
            <el-icon><Clock /></el-icon>截止：{{ experiment.deadline || '无' }}
          </div>
        </div>
        <div class="header-right">
          <el-progress type="circle" :percentage="progressPercent" :width="80" />
          <el-button type="primary" size="large" @click="startWorkbench">
            <el-icon><VideoPlay /></el-icon>
            {{ statusKey === 'not_started' ? '开始实验' : '继续实验' }}
          </el-button>
        </div>
      </div>

      <el-tabs v-model="activeTab" class="tabs-card">
        <el-tab-pane label="实验介绍" name="intro">
          <div class="card">
            <h3 class="section-title">实验目标</h3>
            <p>{{ experiment.description }}</p>
            <h3 class="section-title" style="margin-top: 24px;">前置知识</h3>
            <el-tag v-for="k in prerequisites" :key="k" style="margin-right: 8px;">{{ k }}</el-tag>
            <h3 class="section-title" style="margin-top: 24px;">完成标准</h3>
            <ul class="checklist">
              <li v-for="(c, i) in criteria" :key="i">
                <el-icon color="#22c55e"><CircleCheckFilled /></el-icon> {{ c }}
              </li>
            </ul>
          </div>
        </el-tab-pane>

        <el-tab-pane label="实验步骤" name="steps">
          <div class="card">
            <el-steps direction="vertical" :active="completedSteps">
              <el-step
                v-for="(step, idx) in steps"
                :key="step.id"
                :title="`步骤 ${idx + 1}：${step.title}`"
                :status="stepStatus(idx)"
                :icon="getStepIcon(idx)"
              >
                <template #description>
                  <div class="step-desc">
                    <el-icon class="info-icon"><InfoFilled /></el-icon>
                    {{ step.instruction }}
                  </div>
                  <div class="step-expected" v-if="step.expected_result">
                    <strong>预期结果：</strong>{{ step.expected_result }}
                  </div>
                </template>
              </el-step>
            </el-steps>
          </div>
        </el-tab-pane>

        <el-tab-pane label="AI 助手说明" name="assistant">
          <div class="card assistant-info">
            <div class="assistant-feature">
              <el-icon :size="28" color="#4f6ef7"><View /></el-icon>
              <div>
                <h4>主动视觉感知</h4>
                <p>AI 会观察你的屏幕，识别当前使用的软件、窗口和按钮，主动提供指导。</p>
              </div>
            </div>
            <div class="assistant-feature">
              <el-icon :size="28" color="#22c55e"><Pointer /></el-icon>
              <div>
                <h4>屏幕级操作引导</h4>
                <p>指导直接标记在软件界面上，通过箭头、边框和编号帮你准确定位。</p>
              </div>
            </div>
            <div class="assistant-feature">
              <el-icon :size="28" color="#f59e0b"><MagicStick /></el-icon>
              <div>
                <h4>动态颗粒度调整</h4>
                <p>先简洁提示，找不到就标注位置，仍不会就详细解释，必要时局部示范。</p>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
    <el-empty v-else-if="!loading" description="实验不存在或加载失败" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { experimentApi, progressApi, type Experiment, type ExperimentStep } from '@/api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const experiment = ref<Experiment | null>(null)
const steps = ref<ExperimentStep[]>([])
const activeTab = ref('intro')
const completedSteps = ref(0)

const prerequisites = computed(() => experiment.value?.prerequisites || [])
const criteria = computed(() => experiment.value?.criteria || [])

// 学生进度状态优先，未开始时回落到实验本身状态
const studentStatus = ref('')
const statusKey = computed(() => studentStatus.value || experiment.value?.status || '')
const totalSteps = computed(() => steps.value.length)
const progressPercent = computed(() =>
  totalSteps.value ? Math.round((completedSteps.value / totalSteps.value) * 100) : 0
)

async function loadData() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    experiment.value = await experimentApi.detail(id)
    steps.value = await experimentApi.steps(id)
    try {
      const progress = await progressApi.get(id)
      studentStatus.value = progress.status
      completedSteps.value = progress.completed_steps
    } catch {
      // 未开始实验时无进度记录
      studentStatus.value = ''
      completedSteps.value = 0
    }
  } catch {
    // 加载失败：清空数据，页面展示空状态
    experiment.value = null
    steps.value = []
  } finally {
    loading.value = false
  }
}

const statusMap: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
  draft: { label: '草稿', type: 'info' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已归档', type: 'info' },
  not_started: { label: '未开始', type: 'info' },
  in_progress: { label: '进行中', type: 'warning' },
  completed: { label: '已完成', type: 'success' }
}

function statusLabel(s: string) {
  return statusMap[s]?.label || s
}
function statusTagType(s: string) {
  return statusMap[s]?.type || 'info'
}
function stepStatus(idx: number) {
  if (idx < completedSteps.value) return 'finish'
  if (idx === completedSteps.value) return 'process'
  return 'wait'
}
function getStepIcon(idx: number) {
  // 可以根据状态返回图标组件
  return undefined
}
function startWorkbench() {
  router.push(`/student/workbench/${route.params.id}`)
}

onMounted(loadData)
</script>

<style scoped>
.exp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header-left h2 { margin: 10px 0; font-size: 22px; }
.meta {
  display: flex;
  align-items: center;
  gap: 16px;
  color: #6b7280;
  font-size: 13px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.tabs-card {
  background: #fff;
  border-radius: 12px;
}
:deep(.el-tabs__content) { padding: 0; }
.checklist { list-style: none; padding: 0; }
.checklist li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 14px;
  color: #374151;
}
.step-desc {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: #4b5563;
  margin-bottom: 4px;
}
.info-icon { color: #4f6ef7; margin-top: 3px; }
.step-expected { color: #6b7280; font-size: 13px; }
.assistant-info {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.assistant-feature {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.assistant-feature h4 { margin: 0 0 4px; font-size: 15px; }
.assistant-feature p { margin: 0; color: #6b7280; font-size: 13px; }
</style>
