/**
 * Keeps interface-core free of circular dependencies, and keeps the dependencies
 * between its layers (and between the packages) going one way. See docs/interface.md,
 * "Layers of interface-core".
 *
 * The layers, from the bottom (each may import only from those below it):
 *
 *   types  <  schema  <  api  <  context  <  primitives  <  components  <  registry  <  index
 *
 * `npm run check:layers`
 */

const core = "^interface-core/src";

// From the bottom: each layer may import only from itself and those before it
const layers = ["types", "schema", "api", "context", "primitives", "components"];

function layerRules() {
  return layers.map((layer, index) => ({
    name: `core-${layer}-imports-only-below`,
    severity: "error",
    comment: `\`${layer}\` may import only from: ${layers.slice(0, index + 1).join(", ")}`,
    from: { path: `${core}/${layer}/` },
    to: {
      path: core,
      pathNot: layers.slice(0, index + 1).map((below) => `${core}/${below}/`),
    },
  }));
}

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "A circular dependency; type-only imports count too",
      from: {},
      to: { circular: true, viaOnly: { dependencyTypesNot: [] } },
    },
    ...layerRules(),
    {
      name: "core-never-imports-the-app",
      severity: "error",
      comment: "The library knows nothing of the application, or of what overrides it",
      from: { path: core },
      to: { path: ["^interface-app", "@pangloss/interface-app"] },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["solid", "import", "types", "default"],
    },
  },
};
