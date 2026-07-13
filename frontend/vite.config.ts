import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "frontend",
  base: "/static/",
  plugins: [react()],
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
});
