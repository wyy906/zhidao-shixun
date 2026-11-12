<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar">
      <div class="brand">
        <div class="logo">智</div>
        <div class="brand-text">
          <div class="title">智导实训</div>
          <div class="subtitle">AI 实训平台</div>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="transparent"
        text-color="#9ca3af"
        active-text-color="#ffffff"
      >
        <!-- 学生端菜单 -->
        <template v-if="userStore.role === 'student'">
          <el-menu-item index="/student/dashboard">
            <el-icon><Reading /></el-icon>
            <span>我的实验</span>
          </el-menu-item>
        </template>
        <!-- 教师端菜单 -->
        <template v-else-if="userStore.role === 'teacher'">
          <el-menu-item index="/teacher/dashboard">
            <el-icon><DataAnalysis /></el-icon>
            <span>教学总览</span>
          </el-menu-item>
          <el-menu-item index="/teacher/experiments">
            <el-icon><Document /></el-icon>
            <span>实验管理</span>
          </el-menu-item>
          <el-menu-item index="/teacher/analytics">
            <el-icon><TrendCharts /></el-icon>
            <span>数据分析</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="breadcrumb">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag :type="roleTagType" size="small">{{ roleLabel }}</el-tag>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32">{{ userStore.userInfo?.real_name?.charAt(0) }}</el-avatar>
              <span class="name">{{ userStore.userInfo?.real_name }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)
const currentTitle = computed(() => (route.meta.title as string) || '')

const roleLabel = computed(() => (userStore.role === 'teacher' ? '教师' : '学生'))
const roleTagType = computed(() => (userStore.role === 'teacher' ? 'warning' : 'primary'))

async function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning'
    })
    userStore.logout()
    ElMessage.success('已退出')
    router.push('/login')
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}
.sidebar {
  background: var(--zd-sidebar);
  padding-top: 0;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px 24px;
}
.brand .logo {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #4f6ef7, #7c3aed);
  border-radius: 10px;
  color: #fff;
  font-weight: 700;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-text .title {
  color: #fff;
  font-size: 15px;
  font-weight: 600;
}
.brand-text .subtitle {
  color: #6b7280;
  font-size: 11px;
}
:deep(.el-menu) {
  border-right: none;
  flex: 1;
}
:deep(.el-menu-item) {
  height: 46px;
  line-height: 46px;
  margin: 2px 12px;
  border-radius: 8px;
}
:deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06) !important;
}
:deep(.el-menu-item.is-active) {
  background: var(--zd-primary) !important;
  color: #fff !important;
}
.header {
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background 0.2s;
}
.user-info:hover {
  background: #f3f4f6;
}
.name {
  font-size: 14px;
  color: #374151;
}
.main-content {
  background: var(--zd-bg);
  padding: 0;
  overflow: auto;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
