import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:18765',
    },
  },
  build: {
    // App is shipped inside a PyInstaller .exe and served from local disk —
    // the default 500 kB chunk-size nag isn't meaningful here.
    chunkSizeWarningLimit: 1500,
  },
})
