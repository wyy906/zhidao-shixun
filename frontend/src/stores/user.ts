import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { post } from '@/utils/request'

export interface UserInfo {
  id: number
  username: string
  real_name: string
  role: 'student' | 'teacher'
  class_name?: string
}

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('zd_token') || '')
  const userInfo = ref<UserInfo | null>(
    JSON.parse(localStorage.getItem('zd_user') || 'null')
  )

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => userInfo.value?.role)

  async function login(username: string, password: string): Promise<void> {
    // 登录失败时直接抛异常，由调用方提示
    const res = await post<{ token: string; user: UserInfo }>('/v1/auth/login', {
      username,
      password
    })
    token.value = res.token
    userInfo.value = res.user
    localStorage.setItem('zd_token', res.token)
    localStorage.setItem('zd_user', JSON.stringify(res.user))
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('zd_token')
    localStorage.removeItem('zd_user')
  }

  return { token, userInfo, isLoggedIn, role, login, logout }
})
