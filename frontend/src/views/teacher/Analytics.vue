<template>
  <div class="page-container">
    <div class="card">
      <div class="page-header">
        <h2>教学数据分析</h2>
      </div>

      <el-row :gutter="16">
        <el-col :span="12">
          <h3 class="section-title">各实验完成率对比</h3>
          <el-empty v-if="experiments.length === 0" description="暂无实验数据" />
          <div v-else ref="chart1Ref" class="chart-box"></div>
        </el-col>
        <el-col :span="12">
          <h3 class="section-title">AI 指导使用趋势</h3>
          <el-empty description="暂无数据" />
        </el-col>
      </el-row>

      <el-row :gutter="16" style="margin-top: 16px;">
        <el-col :span="14">
          <h3 class="section-title">各步骤错误分布热力图</h3>
          <el-empty description="暂无数据" />
        </el-col>
        <el-col :span="10">
          <h3 class="section-title">学生 AI 助手使用频次</h3>
          <el-empty description="暂无数据" />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { experimentApi, type Experiment } from '@/api'

const experiments = ref<Experiment[]>([])
const chart1Ref = ref<HTMLElement>()

function initCharts() {
  if (!chart1Ref.value || experiments.value.length === 0) return
  const c1 = echarts.init(chart1Ref.value)
  c1.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 100, right: 60, top: 20, bottom: 30 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: experiments.value.map((e) => e.title) },
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
  window.addEventListener('resize', () => c1.resize())
}

onMounted(async () => {
  try {
    experiments.value = await experimentApi.list()
  } catch {
    experiments.value = []
  }
  await nextTick()
  initCharts()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 { margin: 0; font-size: 20px; }
.chart-box { height: 280px; }
.chart-box.heatmap { height: 260px; }
.section-title {
  font-size: 14px;
  color: #374151;
  margin: 0 0 10px;
}
</style>
