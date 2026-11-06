import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = Number(env.DEV_PORT)
  return {
    plugins: [vue()],
    // 与 Nginx root、同仓库其它 H5 项目一致：prod → dist-prod
    build: {
      outDir: mode === 'prod' ? 'dist-prod' : 'dist',
    },
    server: {
      host: env.DEV_HOST || '0.0.0.0',
      port: Number.isFinite(port) && port > 0 ? port : 5173,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: env.API_PROXY || 'http://127.0.0.1:8010',
          changeOrigin: true,
        },
      },
    },
  }
})
