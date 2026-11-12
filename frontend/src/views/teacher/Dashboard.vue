<template>
  <div class="page-container">
    <div class="welcome-teacher card">
      <div>
        <h2>{{ userStore.userInfo?.real_name }}，欢迎回来 👩‍🏫</h2>
        <p>以下是你所带班级的实验教学概况</p>
      </div>
      <el-button type="primary" @click="$router.push('/teacher/experiments')">
        <el-icon><DocumentAdd /></el-icon>新建实验
      </el-button>
    </div>

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

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="card">
          <div class="card-header">
            <h3 class="section-title">实验完成率分布</h3>
          </div>
          <el-empty v-if="experiments.length === 0" description="暂无实验数据" />
          <div v-else ref="chartRef" class="chart-box"></div>
        </div>
      </el-col>

      <el-col :span="10">
        <div class="card">
          <h3 class="section-title">学生常见困难 TOP 5</h3>
          <el-empty description="暂无数据（需采集操作记录）" />
        </div>
      </el-col>
    </el-row>

    <div class="card" style="margin-top: 16px;">
      <h3 class="section-title">班级实验进度总览</h3>
      <el-empty v-if="students.length === 0" description="暂无学生数据" />
      <el-table v-else :data="students" stripe style="width: 100%">
        <el-table-column prop="name" label="学生" width="140" />
        <el-table-column prop="total_progresses" label="参与实验" width="120" />
        <el-table-column prop="completed_count" label="已完成" width="120" />
        <el-table-column prop="in_progress_count" label="进行中" width="120" />
        <el-table-column label="完成率" width="200">
          <template #default="{ row }">
            <el-progress :percentage="completionRate(row)" />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useUserStore } from '@/stores/user'
import {
  analyticsApi,
  experimentApi,
  type ClassAnalytics,
  type Experiment,
  type StudentAnalytics
} from '@/api'

const userStore = useUserStore()
const chartRef = ref<HTMLElement>()
const experiments = ref<Experiment[]>([])
const students = ref<StudentAnalytics[]>([])
const overview = ref<ClassAnalytics | null>(null)

const stats = computed(() => [
  { label: '学生总数', value: overview.value?.total_students ?? 0, icon: 'User', color: '#4f6ef7', bg: '#eef1fe' },
  { label: '实验总数', value: overview.value?.total_experiments ?? 0, icon: 'Document', color: '#7c3aed', bg: '#f5f3ff' },
  { label: '完成率', value: (overview.value?.completion_rate ?? 0) + '%', icon: 'TrendCharts', color: '#22c55e', bg: '#f0fdf4' },
  { label: '已完成实验', value: overview.value?.completed_count ?? 0, icon: 'CircleCheckFilled', color: '#f59e0b', bg: '#fffbeb' }
])

function completionRate(row: StudentAnalytics) {
  return row.total_progresses
    ? Math.round((row.completed_count / row.total_progresses) * 100)
    : 0
}

function initChart() {
  if (!chartRef.value || experiments.value.length === 0) return
  const chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 80, right: 60, top: 20, bottom: 30 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: {
      type: 'category',
      data: experiments.value.map((e) => e.title)
    },
    series: [
      {
        type: 'bar',
        data: experiments.value.map((e) => e.progress),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#4f6ef7' }, { offset: 1, color: '#7c3aed' }
          ]),
          borderRadius: [0, 6, 6, 0]
        },
        label: { show: true, position: 'right', formatter: '{c}%' }
      }
    ]
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  try {
    experiments.value = await experimentApi.list()
  } catch {
    experiments.value = []
  }
  try {
    overview.value = await analyticsApi.overview()
  } catch {
    overview.value = null
  }
  try {
    students.value = await analyticsApi.studentList()
  } catch {
    students.value = []
  }
  await nextTick()
  initChart()
})
</script>

<style scoped>
.welcome-teacher {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
  color: #fff;
  margin-bottom: 20px;
}
.welcome-teacher h2 { margin: 0 0 6px; font-size: 20px; }
.welcome-teacher p { margin: 0; opacity: 0.9; font-size: 13px; }
.welcome-teacher :deep(.el-button) {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.stat-row { margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-icon {
  width: 48px; height: 48px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 22px; font-weight: 700; }
.stat-label { font-size: 12px; color: #6b7280; margin-top: 2px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.chart-box { height: 280px; }
</style>
