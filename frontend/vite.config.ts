import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the API is proxied so the browser sees a same-origin /api and CORS
// never enters the picture. In production VITE_API_BASE_URL points at the
// deployed backend instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
