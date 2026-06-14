import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Single app, single URL: production build is served by FastAPI at http://127.0.0.1:8000.
// In development, `npm run dev` runs a Vite server and proxies API + write calls to the running
// FastAPI backend so there is still one source of truth for data.
export default defineConfig({
  plugins: [react()],
  base: "/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/approvals": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
