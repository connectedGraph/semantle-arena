import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 开发时 /api 代理到 FastAPI(:8010)，生产由后端同源托管 dist
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5180,
    host: "127.0.0.1",
    proxy: { "/api": { target: "http://127.0.0.1:8010", changeOrigin: true } },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
