// Reads the manifests of interface modules (TypeScript, with lazy imports that are not called) and
// prints them as JSON, one per file given, on the last line: `pangloss interface check` uses it.
// Vite's loader compiles them as the application would. Run in interface-app.
import solid from "@solidjs/vite-plugin";
import { createServer } from "vite";

const server = await createServer({
  configFile: false,
  // (the library is source, with JSX: compiled as the application compiles it)
  plugins: [solid({ ssr: true, extensions: [".jsx", ".tsx"] })],
  ssr: { noExternal: ["@pangloss/interface-core"] },
  logLevel: "silent",
  appType: "custom",
  server: { middlewareMode: true, hmr: false, watch: null },
  optimizeDeps: { noDiscovery: true },
});
try {
  const manifests = [];
  for (const file of process.argv.slice(2)) {
    const { default: manifest } = await server.ssrLoadModule(file);
    manifests.push({
      name: manifest.name,
      requires: manifest.requires ?? [],
      components: Object.keys(manifest.components ?? {}),
      routes: (manifest.routes ?? []).map(({ path, component }) => ({ path, component })),
    });
  }
  console.log(JSON.stringify(manifests));
} finally {
  await server.close();
}
