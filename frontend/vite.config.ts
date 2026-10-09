import fs from 'node:fs'
import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Enable Banking redirects only to https URLs, localhost included, so bank
// connections in local work need the dev server on https.
const certDir = path.resolve(import.meta.dirname, '.cert')
const https = fs.existsSync(path.join(certDir, 'cert.pem'))
  ? {
      key: fs.readFileSync(path.join(certDir, 'key.pem')),
      cert: fs.readFileSync(path.join(certDir, 'cert.pem')),
    }
  : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: { https },
})
