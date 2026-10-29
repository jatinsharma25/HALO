import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Our backend's routers mount unprefixed (/auth, /cameras, ...), same as
      // nginx.conf strips /api/ in the Docker build — so this dev proxy must
      // strip it too. ws: true so /api/alerts/ws and /api/stream/* upgrade.
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
