import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/jobs': 'http://localhost:8000',
      '/languages': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    }
  },
  build: {
    // Builds to /app/dist inside the Docker stage — copied to backend/static after
    outDir: 'dist',
    emptyOutDir: true,
  }
})
