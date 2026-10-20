import solid from "@solidjs/vite-plugin";
import { fileRoutes } from "filesystem-routing/vite";
import { defineConfig } from "vite";

// Where the Pangloss API is, for the dev server to pass `/api` requests on to. (`pangloss
// interface dev` sets this; the API is `pangloss run` or `pangloss dev`.) In production
// something in front of the server does it: see docs/interface.md.
const apiUrl = process.env.PANGLOSS_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [
    solid({
      // Streaming server-side rendering. The plugin makes the entries around
      // src/App.tsx, in the shell of src/Document.tsx; `vite build` writes the client
      // to dist/client, and the server to dist/server (with `node.js`, which
      // `npm start` runs)
      ssr: true,
      start: { node: true },
      // (so that the route modules of the file router are compiled)
      extensions: [".jsx", ".tsx"],
    }),
    fileRoutes({ types: true }),
  ],
  // interface-core is source, which has to be compiled for the server as well
  ssr: { noExternal: ["@pangloss/interface-core"] },
  server: {
    port: 3000,
    proxy: {
      "/api": { target: apiUrl, changeOrigin: false },
    },
  },
  build: {
    target: "esnext",
    assetsInlineLimit: 0,
  },
});
