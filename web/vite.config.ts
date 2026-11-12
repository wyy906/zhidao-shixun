import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发服务器代理：前端页面对 /health、/api 的请求转发到本地后端，避免开发期跨域配置。
// 后端地址默认 8000；若端口被占用，可用 ZD_API_PROXY_TARGET 环境变量覆盖（如 http://127.0.0.1:8100）。
const apiProxyTarget = process.env.ZD_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/health': { target: apiProxyTarget, changeOrigin: true },
      '/api': { target: apiProxyTarget, changeOrigin: true },
    },
  },
})

