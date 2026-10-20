import solid from "@solidjs/vite-plugin";
import { defineConfig } from "vitest/config";

// (tests of the logic of the library; components are tested through the application)
export default defineConfig({
  plugins: [solid()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
