/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  },
  // Frontend tests (`npm test`). jsdom only; no test contacts the backend or Bitbucket.
  test: {
    environment: 'jsdom',
    // e2e/ holds the Playwright suite (`npm run e2e`), which needs the real app running.
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true
  }
})
