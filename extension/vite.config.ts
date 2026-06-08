import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: "index.html",
        background: "src/background/background.ts",
        content: "src/content/content.ts"
      },
      output: {
        entryFileNames: (chunk) => {
          if (chunk.name === "background") return "background/background.js";
          if (chunk.name === "content") return "content/content.js";
          return "assets/[name]-[hash].js";
        }
      }
    }
  }
});
