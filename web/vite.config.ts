import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { loadEnv, type Plugin } from "vite";
// The published server is Node-builtins + app-server only. Its gateway
// middleware is mounted here too, so `npm run dev` goes through the same
// app-cookie session exchange as production (abstractcode/web/vite.config.ts
// does the same; development cannot bypass the proxy).
import { createGatewayMiddleware } from "./bin/server.js";

function gatewaySessionProxy(env: Record<string, string>): Plugin {
  return {
    name: "abstractassistant-gateway-session-proxy",
    configureServer(server) {
      const url = String(env.ABSTRACTASSISTANT_GATEWAY_URL || env.ABSTRACTGATEWAY_URL || "").trim();
      server.middlewares.use(createGatewayMiddleware(url ? { defaultGatewayUrl: url } : {}));
    },
  };
}

export default defineConfig(({ mode }) => ({
  // Relative base: the app is served under the gateway's /apps/assistant-web/.
  base: "./",
  plugins: [
    react(),
    gatewaySessionProxy({
      ...loadEnv(mode, process.cwd(), ""),
      ...(process.env as Record<string, string>),
    }),
  ],
  server: { host: "127.0.0.1", strictPort: false },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    environment: "node",
  },
}));
