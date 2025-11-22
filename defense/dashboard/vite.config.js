import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const orchestratorTarget = process.env.DEFENSE_API_TARGET || "http://localhost:7700";
const orchestratorWsTarget = orchestratorTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: orchestratorTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "")
      },
      "/ws": {
        target: orchestratorWsTarget,
        ws: true,
        changeOrigin: true
      }
    }
  }
});

