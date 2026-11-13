import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The built UI is committed to instai/static/app and served by Django under /static/app/.
export default defineConfig({
  base: '/static/app/',
  plugins: [react()],
  // the Remotion compositions live in ../remotion/src (one source for the preview here and for the render on the PC); their imports of
  // react / remotion must resolve to THIS project's copies, otherwise there would be two Reacts and two Remotions on one page
  resolve: { dedupe: ['react', 'react-dom', 'remotion'] },
  build: {
    outDir: '../instai/static/app',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    fs: { allow: ['..'] },
    proxy: {
      '/api': 'http://127.0.0.1:8799',
      '/media': 'http://127.0.0.1:8799',
    },
  },
})
