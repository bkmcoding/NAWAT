import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Bypasses the strict package.json "exports" check
      'react-map-gl': 'react-map-gl/dist/esm/index.js'
    }
  }
})