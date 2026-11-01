import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the page is served by Vite (port 5173) and talks to the Python server (port 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: { environment: "node" },
});
