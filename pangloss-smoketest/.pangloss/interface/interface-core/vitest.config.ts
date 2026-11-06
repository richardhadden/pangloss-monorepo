import solid from "@solidjs/vite-plugin";
import { defineConfig } from "vitest/config";

// Logic is tested in node; a component is tested in a DOM (a file says `// @vitest-environment
// happy-dom`), where Solid must be its browser build, not the server one
export default defineConfig({
  plugins: [solid()],
  resolve: { conditions: ["browser", "development"] },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    server: { deps: { inline: [/solid-js/, /@solidjs/] } },
  },
});
