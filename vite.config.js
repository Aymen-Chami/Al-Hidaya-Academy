import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin API in dev (the session cookie needs it): /api → FastAPI on :8000.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
