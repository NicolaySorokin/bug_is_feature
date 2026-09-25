/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// В разработке запросы к API и Keycloak идут через прокси Vite: клиент
// ходит на тот же адрес, что и в бою (/api/v1), и CORS не нужен.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const api = env.VITE_DEV_API_URL || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": { target: api, changeOrigin: true },
      },
    },
    build: {
      // Разбивка на части: код библиотек меняется реже кода приложения
      // и дольше живёт в кэше браузера.
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query"],
            keycloak: ["keycloak-js"],
          },
        },
      },
      chunkSizeWarningLimit: 900,
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
