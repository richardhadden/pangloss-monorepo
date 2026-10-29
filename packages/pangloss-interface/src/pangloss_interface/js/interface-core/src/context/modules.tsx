import { createContext, lazy, useContext } from "solid-js";
import type { Component, ParentProps } from "solid-js";
import { findLoader, orderModules, slotOf } from "../schema";
import type { CustomProps, CustomSlot, ModuleManifest } from "../types";
import { useModels } from "./models";

interface ModulesValue {
  modules: ModuleManifest[];
  /** The component a model names for a slot (lazy; the same one each time), or undefined */
  custom<S extends CustomSlot>(type: string, slot: S): Component<CustomProps[S]> | undefined;
}

// (without a provider there are no modules: a component of the library works in a test, or an application, that has none)
const NONE: ModulesValue = { modules: [], custom: () => undefined };
const ModulesContext = createContext<ModulesValue>(NONE);

/** Makes the interface modules of the installed apps available below (without it, none are) */
export function ModulesProvider(props: ParentProps<{ modules: readonly ModuleManifest[] }>) {
  const definitions = useModels();
  const modules = orderModules(props.modules);
  const made = new Map<string, Component<any>>();
  const value: ModulesValue = {
    modules,
    custom(type, slot) {
      const reference = slotOf(definitions, type, slot);
      if (!reference) return undefined;
      const key = `${reference.module}:${reference.name}`;
      const found = made.get(key);
      if (found) return found as never;
      const loader = findLoader(modules, reference);
      if (!loader) {
        // (a reference that resolves to nothing falls back to the generic page: `pangloss interface check` says why)
        console.warn(`The interface module component '${key}' (${type}.${slot}) does not exist`);
        return undefined;
      }
      const component = lazy(loader);
      made.set(key, component);
      return component as never;
    },
  };
  return <ModulesContext value={value}>{props.children}</ModulesContext>;
}

export function useModules(): ModulesValue {
  return useContext(ModulesContext);
}

/** The component a model names for a slot, or undefined: `useCustom()(type, "viewCard")` */
export function useCustom(): ModulesValue["custom"] {
  return useModules().custom;
}
