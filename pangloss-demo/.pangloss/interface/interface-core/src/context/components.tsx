import { createContext, useContext } from "solid-js";
import type { ParentProps } from "solid-js";
import type { ComponentMap, ComponentName } from "../types";

const ComponentsContext = createContext<ComponentMap>();

/** Makes `components` the ones that `useComponent` finds below it */
export function ComponentsProvider(props: ParentProps<{ components: ComponentMap }>) {
  return <ComponentsContext value={props.components}>{props.children}</ComponentsContext>;
}

/**
 * A component of the library, or what the application has put in its place. Use this
 * rather than importing a component, in any component that another could override.
 */
export function useComponent<K extends ComponentName>(name: K): ComponentMap[K] {
  const components = useContext(ComponentsContext);
  if (!components) {
    throw new Error(`useComponent("${name}"): there is no <ComponentsProvider> above`);
  }
  return components[name];
}
