import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

/* 开发期由 Vite 承担 Nginx 的职责：静态资源 + /api 反向代理。
 * changeOrigin 必须保持 false —— 后端对所有 POST 校验 Origin 与 Host 同源，
 * 一旦把 Host 改写成后端地址，浏览器发来的 Origin 就对不上，会返回「跨站请求被拒绝」。 */
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8080';

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.DEV_PORT || 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1600,
  },
});
