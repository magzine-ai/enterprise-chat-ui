import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath, URL } from 'url'

// Fix for ES modules - get __dirname equivalent
const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  root: process.cwd(), // Use current working directory as root
  publicDir: 'public',
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        marketplace: path.resolve(__dirname, 'marketplace.html'),
        'developer-tools': path.resolve(__dirname, 'developer-tools.html'),
      },
    },
    outDir: 'dist',
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    host: '0.0.0.0', // Allow external connections
    strictPort: false,
    fs: {
      // Allow serving files from one level up to the project root
      allow: ['..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  // Ensure proper module resolution
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-redux', '@reduxjs/toolkit'],
    exclude: [],
  },
  // Fix for enterprise environments with strict file system
  clearScreen: false,
})

