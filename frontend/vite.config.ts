import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    strictPort: true,
    host: "0.0.0.0",
    port: 1420,
    proxy: {
      "/api": {
        target: process.env.SHOTMILL_BACKEND_URL ?? "http://127.0.0.1:8765",
        changeOrigin: true,
      },
      "/media": {
        target: process.env.SHOTMILL_BACKEND_URL ?? "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
