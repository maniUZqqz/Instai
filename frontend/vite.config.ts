import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The built UI is committed to instai/static/app and served by Django under /static/app/.
export default defineConfig({
  base: '/static/app/',
  plugins: [react()],
  build: {
    outDir: '../instai/static/app',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8799',
      '/media': 'http://127.0.0.1:8799',
    },
  },
})
