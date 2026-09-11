import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base` lets the same build serve from a GitHub Pages project subpath
// (/rankfield/) or from a domain root. Set RANKFIELD_BASE in CI.
// A project page serves from /<repo>/, and `actions/configure-pages` reports
// that path without a trailing slash. Vite expects one, so normalise here too.
const rawBase = process.env.RANKFIELD_BASE ?? "/";
const base = rawBase.endsWith("/") ? rawBase : `${rawBase}/`;

export default defineConfig({
  base,
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: { port: 5173 },
});
