import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const target = 'http://localhost:3000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': target,
      '/api': target,
      '/socket.io': { target, ws: true },
    },
  },
});
