import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

const proxy = { '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false } }

export default defineConfig({
  plugins: [react(), tailwindcss(), VitePWA({
    registerType: 'prompt',
    strategies: 'injectManifest', srcDir: 'src', filename: 'sw.ts',
    includeAssets: ['icon.svg', 'offline.html', 'icons/*.png'],
    manifest: {
      id: '/', name: 'NTECH Enterprise Management System', short_name: 'NTECH EMS',
      description: 'ETS-NTECH enterprise workspace', start_url: '/', scope: '/',
      display: 'standalone', background_color: '#f6f8fb', theme_color: '#14213a', lang: 'en',
      icons: [
        { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      ],
    },
    injectManifest: {
      globPatterns: ['**/*.{js,css,html,png,svg,woff2}'],
      maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
    },
  })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
})
