<template>
  <div class="page-container">
    <!-- 欢迎区 -->
    <div class="welcome-card card">
      <div>
        <h2>你好，{{ userStore.userInfo?.real_name }} 👋</h2>
        <p>今天也要加油完成实验哦！AI 实训助手随时准备帮你。</p>
      </div>
      <el-button type="primary" size="large" @click="goOngoing">
        <el-icon><VideoPlay /></el-icon>继续进行中的实验
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <div class="stat-card card">
          <div class="stat-icon" :style="{ background: stat.bg }">
            <el-icon :size="24" :style="{ color: stat.color }"><component :is="stat.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stat.value }}</div>
            <div class="stat-label">{{ stat.label }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 实验列表 -->
    <div class="card">
      <div class="card-header">
        <h3 class="section-title">我的实验课程</h3>
        <el-radio-group v-model="filter" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="in_progress">进行中</el-radio-button>
          <el-radio-button value="completed">已完成</el-radio-button>
        </el-radio-group>
      </div>

      <el-empty v-if="filteredList.length === 0" description="暂无实验任务" />

      <div class="exp-grid" v-else>
        <div
          v-for="exp in filteredList"
          :key="exp.id"
          class="exp-card"
          @click="goDetail(exp.id)"
        >
          <div class="exp-type-tag">{{ exp.software }}</div>
          <h4>{{ exp.title }}</h4>
          <p class="exp-desc">{{ exp.description }}</p>
          <div class="exp-meta">
            <el-tag :type="statusTagType(exp.status)" size="small">{{ statusLabel(exp.status) }}</el-tag>
            <span class="progress-text">步骤 {{ exp.completed_steps }}/{{ exp.total_steps }}</span>
          </div>
          <el-progress :percentage="exp.progress" :status="progressStatus(exp.status)" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { experimentApi, type Experiment } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const filter = ref<'all' | 'in_progress' | 'completed'>('all')
const experiments = ref<Experiment[]>([])

const filteredList = computed(() => {
  if (filter.value === 'all') return experiments.value
  return experiments.value.filter((e) => e.status === filter.value)
})

const stats = computed(() => {
  const total = experiments.value.length
  const inProgress = experiments.value.filter((e) => e.status === 'in_progress').length
  const completed = experiments.value.filter((e) => e.status === 'completed').length
  const avg = total ? Math.round(experiments.value.reduce((s, e) => s + e.progress, 0) / total) : 0
  return [
    { label: '实验总数', value: total, icon: 'Document', color: '#4f6ef7', bg: '#eef1fe' },
    { label: '进行中', value: inProgress, icon: 'Loading', color: '#f59e0b', bg: '#fffbeb' },
    { label: '已完成', value: completed, icon: 'CircleCheckFilled', color: '#22c55e', bg: '#f0fdf4' },
    { label: '平均进度', value: avg + '%', icon: 'TrendCharts', color: '#7c3aed', bg: '#f5f3ff' }
  ]
})

async function loadData() {
  try {
    experiments.value = await experimentApi.list()
  } catch {
    // 加载失败保持空列表，页面展示空状态
    experiments.value = []
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
function progressStatus(s: string) {
  return s === 'completed' ? 'success' : undefined
}
function goDetail(id: number) { router.push(`/student/experiment/${id}`) }
function goOngoing() {
  const ongoing = experiments.value.find((e) => e.status === 'in_progress')
  if (ongoing) goDetail(ongoing.id)
}

onMounted(loadData)
</script>

<style scoped>
.welcome-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #4f6ef7 0%, #7c3aed 100%);
  color: #fff;
}
.welcome-card h2 { margin: 0 0 6px; font-size: 20px; }
.welcome-card p { margin: 0; opacity: 0.9; font-size: 13px; }
.welcome-card :deep(.el-button) {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #fff;
}
.stat-row { margin-bottom: 20px; }
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat-icon {
  width: 48px; height: 48px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 22px; font-weight: 700; color: #111827; }
.stat-label { font-size: 12px; color: #6b7280; margin-top: 2px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.exp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.exp-card {
  padding: 18px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.exp-card:hover {
  border-color: var(--zd-primary);
  box-shadow: 0 4px 12px rgba(79, 110, 247, 0.15);
  transform: translateY(-2px);
}
.exp-type-tag {
  display: inline-block;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 10px;
}
.exp-card h4 { margin: 0 0 6px; font-size: 15px; color: #111827; }
.exp-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: 36px;
}
.exp-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.progress-text { font-size: 12px; color: #6b7280; }
</style>
