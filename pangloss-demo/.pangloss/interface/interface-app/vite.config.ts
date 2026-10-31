import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import solid from "@solidjs/vite-plugin";
import { defineConfig, searchForWorkspaceRoot } from "vite";

// Where the Pangloss API is, for the dev server to pass `/api` requests on to. (`pangloss
// interface dev` sets this; the API is `pangloss run` or `pangloss dev`.) In production
// something in front of the server does it: see docs/interface.md.
const apiUrl = process.env.PANGLOSS_API_URL ?? "http://127.0.0.1:8000";

// The definitions of the project's models: generated into src/ when the interface is built in
// the project. `pangloss interface dev --link` runs this app from the package's own source
// instead, and has them somewhere else, which it says here.
const modelsModule =
  process.env.PANGLOSS_MODELS_MODULE ??
  fileURLToPath(new URL("./src/generated/models.ts", import.meta.url));

// The same for the interface modules of the installed apps: `modules.ts` (their manifests) and `sources.css` (where Tailwind
// looks for their classes). `pangloss interface dev --link` points them at the apps' own folders.
const modulesModule =
  process.env.PANGLOSS_MODULES_MODULE ??
  fileURLToPath(new URL("./src/generated/modules.ts", import.meta.url));
const translationsModule =
  process.env.PANGLOSS_TRANSLATIONS_MODULE ??
  fileURLToPath(new URL("./src/generated/translations.json", import.meta.url));
const sourcesCss =
  process.env.PANGLOSS_SOURCES_CSS ??
  fileURLToPath(new URL("./src/generated/sources.css", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@generated/models": modelsModule,
      "@generated/modules": modulesModule,
      "@generated/translations": translationsModule,
      "@generated/sources.css": sourcesCss,
    },
    // (an interface module has its own node_modules at times: one copy of each of these, or reactivity breaks)
    dedupe: ["solid-js", "@solidjs/web", "@solidjs/router", "@pangloss/interface-core"],
  },
  plugins: [
    solid({
      // Streaming server-side rendering. The plugin makes the entries around
      // src/App.tsx, in the shell of src/Document.tsx; `vite build` writes the client
      // to dist/client, and the server to dist/server (with `node.js`, which
      // `npm start` runs)
      ssr: true,
      start: { node: true },
      // "use server" functions: the translations of a language are fetched with one (src/translations.ts)
      serverFunctions: true,
      extensions: [".jsx", ".tsx"],
    }),
    tailwindcss(),
  ],
  // interface-core is source, which has to be compiled for the server as well
  ssr: { noExternal: ["@pangloss/interface-core"] },
  server: {
    port: 3000,
    // (the models may be outside of the workspace, in the project)
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        dirname(modelsModule),
        dirname(modulesModule),
        dirname(translationsModule),
        // (the modules of apps that are checked out, run where they are)
        ...(process.env.PANGLOSS_MODULE_ROOTS?.split(":").filter(Boolean) ?? []),
      ],
    },
    proxy: {
      "/api": { target: apiUrl, changeOrigin: false },
    },
  },
  build: {
    target: "esnext",
    assetsInlineLimit: 0,
  },
});
