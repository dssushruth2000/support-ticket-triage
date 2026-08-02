import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/metrics": "http://127.0.0.1:8000",
      "/tickets": "http://127.0.0.1:8000",
    },
  },
  base: "/dashboard/",
});
