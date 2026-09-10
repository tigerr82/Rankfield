import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base` lets the same build serve from a GitHub Pages project subpath
// (/rankfield/) or from a domain root. Set RANKFIELD_BASE in CI.
export default defineConfig({
  base: process.env.RANKFIELD_BASE ?? "/",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: { port: 5173 },
});
