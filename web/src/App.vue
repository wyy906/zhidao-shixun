<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchHealth, type HealthResponse } from './api/health'

const health = ref<HealthResponse | null>(null)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    health.value = await fetchHealth()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <main class="page">
    <h1>智导实训 V2</h1>
    <p class="subtitle">AI 视觉感知与实时操作引导平台 · 基础骨架（V2-02）</p>

    <section v-if="health" class="card ok">
      <h2>后端连接正常</h2>
      <ul>
        <li>应用：{{ health.app }}</li>
        <li>环境：{{ health.app_env }}</li>
        <li>API 版本：{{ health.api_version }}</li>
        <li>契约版本：{{ health.contract_version }}</li>
      </ul>
    </section>

    <section v-else-if="error" class="card err">
      <h2>后端未连接</h2>
      <p>{{ error }}</p>
      <p>请先启动后端（scripts/start-server.ps1），然后刷新本页。</p>
    </section>

    <section v-else class="card">
      <h2>正在连接后端…</h2>
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 640px;
  margin: 0 auto;
  padding: 2rem 1rem;
  font-family: system-ui, 'Microsoft YaHei', sans-serif;
}
.subtitle {
  color: #64748b;
}
.card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-top: 1.5rem;
}
.card.ok {
  border-color: #16a34a;
}
.card.err {
  border-color: #dc2626;
}
.card h2 {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
}
.card ul {
  margin: 0;
  padding-left: 1.2rem;
}
</style>
