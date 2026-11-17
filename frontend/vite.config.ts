import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = process.env.VITE_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    host: "127.0.0.1",          // Add this line
    allowedHosts: [".ts.net"],   // Add this line
    proxy: {
      "/api": {
        target,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});