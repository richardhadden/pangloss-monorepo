import type {
  ComponentLoader,
  CustomSlot,
  ModelDefinitions,
  ModuleManifest,
} from "../types";

/** Says what an interface module provides; the identity, so that a manifest that does not fit is a type error */
export function defineModule(manifest: ModuleManifest): ModuleManifest {
  return manifest;
}

/** The modules with those a module `requires` first (and otherwise in the order given); throws on one that is missing or a cycle */
export function orderModules(modules: readonly ModuleManifest[]): ModuleManifest[] {
  const byName = new Map(modules.map((module) => [module.name, module]));
  const ordered: ModuleManifest[] = [];
  const done = new Set<string>();
  const visiting: string[] = [];
  const visit = (module: ModuleManifest) => {
    if (done.has(module.name)) return;
    if (visiting.includes(module.name)) {
      throw new Error(`Interface modules require each other in a circle: ${[...visiting, module.name].join(" -> ")}`);
    }
    visiting.push(module.name);
    for (const name of module.requires ?? []) {
      const required = byName.get(name);
      if (!required) throw new Error(`The interface module '${module.name}' requires '${name}', which is not installed`);
      visit(required);
    }
    visiting.pop();
    done.add(module.name);
    ordered.push(module);
  };
  modules.forEach(visit);
  return ordered;
}

/** The loader of the component `app:name` names, if there is one */
export function findLoader(
  modules: readonly ModuleManifest[],
  reference: { module: string; name: string },
): ComponentLoader | undefined {
  const module = modules.find((m) => m.name === reference.module);
  return module && Object.hasOwn(module.components, reference.name)
    ? module.components[reference.name]
    : undefined;
}

/** The reference a model names for a slot (already resolved through its parents by the export) */
export function slotOf(
  definitions: ModelDefinitions,
  type: string,
  slot: CustomSlot,
): { module: string; name: string } | null {
  return Object.hasOwn(definitions.models, type)
    ? (definitions.models[type]!.interfaceMeta?.[slot] ?? null)
    : null;
}
