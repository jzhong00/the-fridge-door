import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  server: {
    // In development the API runs separately on :8000. Proxying it under the
    // same origin means no CORS handling and the same relative URLs the
    // production build uses, where Vercel serves both from one domain.
    proxy: {
      // API_PROXY_TARGET lets the end-to-end tests point at their own server
      // instead of the development one. `vite preview` reuses this proxy.
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
