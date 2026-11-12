import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/student/dashboard',
    children: [
      // 学生端
      {
        path: 'student/dashboard',
        name: 'StudentDashboard',
        component: () => import('@/views/student/Dashboard.vue'),
        meta: { title: '我的实验', roles: ['student', 'teacher'] }
      },
      {
        path: 'student/experiment/:id',
        name: 'ExperimentDetail',
        component: () => import('@/views/student/ExperimentDetail.vue'),
        meta: { title: '实验详情', roles: ['student', 'teacher'] }
      },
      {
        path: 'student/workbench/:id',
        name: 'ExperimentWorkbench',
        component: () => import('@/views/student/Workbench.vue'),
        meta: { title: 'AI 实训工作台', roles: ['student'] }
      },
      {
        path: 'student/report/:id',
        name: 'ExperimentReport',
        component: () => import('@/views/student/Report.vue'),
        meta: { title: '实验报告', roles: ['student', 'teacher'] }
      },
      // 教师端
      {
        path: 'teacher/dashboard',
        name: 'TeacherDashboard',
        component: () => import('@/views/teacher/Dashboard.vue'),
        meta: { title: '教学总览', roles: ['teacher'] }
      },
      {
        path: 'teacher/experiments',
        name: 'TeacherExperiments',
        component: () => import('@/views/teacher/ExperimentManage.vue'),
        meta: { title: '实验管理', roles: ['teacher'] }
      },
      {
        path: 'teacher/analytics',
        name: 'TeacherAnalytics',
        component: () => import('@/views/teacher/Analytics.vue'),
        meta: { title: '数据分析', roles: ['teacher'] }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/student/dashboard' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const title = to.meta.title as string | undefined
  if (title) document.title = `${title} - 智导实训`

  if (to.meta.public) return next()

  if (!userStore.isLoggedIn) {
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }

  const requiredRoles = to.meta.roles as string[] | undefined
  if (requiredRoles && !requiredRoles.includes(userStore.role || '')) {
    return next('/student/dashboard')
  }

  next()
})

export default router
