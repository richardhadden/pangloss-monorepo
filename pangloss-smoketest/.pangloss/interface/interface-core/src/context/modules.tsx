import { createContext, lazy, useContext } from "solid-js";
import type { Component, ParentProps } from "solid-js";
import { findLoader, orderModules, slotOf } from "../schema";
import type {
  CollapseRule,
  ComponentLoader,
  ComponentReference,
  ConsoleActionProps,
  CustomProps,
  CustomSlot,
  IncomingView,
  IncomingViewProps,
  ItemSectionProps,
  ModuleManifest,
  NewItemActionProps,
} from "../types";
import { useModels } from "./models";

interface ModulesValue {
  modules: ModuleManifest[];
  /** The component a model names for a slot (lazy; the same one each time), or undefined */
  custom<S extends CustomSlot>(type: string, slot: S): Component<CustomProps[S]> | undefined;
  /** The rule `InterfaceMeta(collapse="app:name")` names, or undefined */
  collapseRule(reference: ComponentReference): CollapseRule | undefined;
  /** What the modules add to the console of an item (`consoleActions`), in the order of the modules (lazy; the same each time) */
  consoleActions(): Component<ConsoleActionProps>[];
  /** What the modules add to the console of the form that makes a new item (`newItemActions`), in order (lazy) */
  newItemActions(): Component<NewItemActionProps>[];
  /** What the modules add first among the fields of the form that makes a new item (`newItemFields`), in order */
  newItemFields(): Component<NewItemActionProps>[];
  /** What the modules add after the contents of an item's page (`itemSections`), in the order of the modules (lazy) */
  itemSections(): Component<ItemSectionProps>[];
  /** The same, as their loaders: for `ItemSections`, which waits for their code itself, in one boundary */
  itemSectionLoaders(): ComponentLoader[];
  /** The other ways of showing what refers to an item (`incomingViews`), by name `app:key` (each component lazy) */
  incomingViews(): LoadedIncomingView[];
  /**
   * Start loading the code the modules add to the page of an item of the type: the model's own page, the sections,
   * the views of what refers to it, and the cards of the models that have their own. A page calls it as it starts to read the item, so that the code is loaded
   * while the item is read: left to the first render that needs it, it was asked for only once the item had
   * come, and the server rendered the page in as many passes as there were things to wait for, one after another
   */
  preloadItemPage(type: string): void;
}

/** An `IncomingView` of a module, with its name and its component made */
export interface LoadedIncomingView {
  /** `app:key` */
  name: string;
  takes: IncomingView["takes"];
  component: Component<IncomingViewProps>;
}

// (without a provider there are no modules: a component of the library works in a test, or an application, that has none)
const NONE: ModulesValue = {
  modules: [],
  custom: () => undefined,
  collapseRule: () => undefined,
  consoleActions: () => [],
  newItemActions: () => [],
  newItemFields: () => [],
  itemSections: () => [],
  itemSectionLoaders: () => [],
  incomingViews: () => [],
  preloadItemPage: () => {},
};
const ModulesContext = createContext<ModulesValue>(NONE);

/** Makes the interface modules of the installed apps available below (without it, none are) */
export function ModulesProvider(props: ParentProps<{ modules: readonly ModuleManifest[] }>) {
  const definitions = useModels();
  const modules = orderModules(props.modules);
  const made = new Map<string, Component<any>>();
  // (what the project leaves out: `InterfaceConfig(disabled=...)`)
  const disabled = new Set(definitions.disabled ?? []);
  // (the components of one kind of contribution, `app:key` with its value, of every module, in order, not disabled)
  const each = <T,>(of: (module: ModuleManifest) => Record<string, T> | undefined): [string, T][] =>
    modules.flatMap((module) =>
      Object.entries(of(module) ?? {})
        .map(([key, value]): [string, T] => [`${module.name}:${key}`, value])
        .filter(([name]) => !disabled.has(name)),
    );
  let actions: Component<ConsoleActionProps>[] | undefined;
  let newActions: Component<NewItemActionProps>[] | undefined;
  let newFields: Component<NewItemActionProps>[] | undefined;
  let sections: Component<ItemSectionProps>[] | undefined;
  let views: LoadedIncomingView[] | undefined;
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
    collapseRule(reference) {
      const rules = modules.find((m) => m.name === reference.module)?.collapseRules;
      return rules && Object.hasOwn(rules, reference.name) ? rules[reference.name] : undefined;
    },
    consoleActions() {
      actions ??= each((module) => module.consoleActions).map(
        ([, loader]) => lazy(loader) as Component<ConsoleActionProps>,
      );
      return actions;
    },
    newItemActions() {
      newActions ??= each((module) => module.newItemActions).map(
        ([, loader]) => lazy(loader) as Component<NewItemActionProps>,
      );
      return newActions;
    },
    newItemFields() {
      newFields ??= each((module) => module.newItemFields).map(
        ([, loader]) => lazy(loader) as Component<NewItemActionProps>,
      );
      return newFields;
    },
    itemSections() {
      sections ??= each((module) => module.itemSections).map(
        ([, loader]) => lazy(loader) as Component<ItemSectionProps>,
      );
      return sections;
    },
    itemSectionLoaders() {
      return each((module) => module.itemSections).map(([, loader]) => loader);
    },
    incomingViews() {
      views ??= each((module) => module.incomingViews).map(([name, view]) => ({
        name,
        takes: view.takes,
        component: lazy(view.component) as Component<IncomingViewProps>,
      }));
      return views;
    },
    preloadItemPage(type) {
      const page = slotOf(definitions, type, "itemPage") ? value.custom(type, "itemPage") : undefined;
      // (the cards of the models that have their own: what is inside the item, or refers to it, can be of any of them)
      const cards = Object.keys(definitions.models)
        .filter((name) => slotOf(definitions, name, "viewCard"))
        .map((name) => value.custom(name, "viewCard"));
      for (const component of [
        page,
        ...cards,
        ...value.itemSections(),
        ...value.incomingViews().map((view) => view.component),
      ]) {
        // (a `lazy` component; what fails to load says so where it is shown, not here)
        void (component as { preload?: () => Promise<unknown> } | undefined)?.preload?.().catch(() => {});
      }
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
