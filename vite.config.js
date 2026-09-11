import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin API in dev (the session cookie needs it): /api → FastAPI on :8000.
    // changeOrigin: false keeps the browser's Host header, so the API's same-origin check
    // (Origin host == Host) passes on whatever port Vite ends up on — the string shorthand
    // would rewrite Host to localhost:8000 and every write would fail with BAD_ORIGIN
    // unless the page happened to be served from an allow-listed port.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
})
