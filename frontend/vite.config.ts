import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth':        'https://verisync-j5em.onrender.com',
      '/api':         'https://verisync-j5em.onrender.com',
      '/repos':       'https://verisync-j5em.onrender.com',
      '/events':      'https://verisync-j5em.onrender.com',
      '/webhook':     'https://verisync-j5em.onrender.com',
    }
  }
});
