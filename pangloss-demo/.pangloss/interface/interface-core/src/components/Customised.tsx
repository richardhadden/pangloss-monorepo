import { Dynamic } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
import { Show } from "solid-js";
import type { Component } from "solid-js";
import { useCustom } from "../context";
import type { CustomProps, CustomSlot } from "../types";

export interface CustomisedProps<S extends CustomSlot> {
  /** Which of the model's components to look for */
  slot: S;
  /** The model (the type of the item, or of the list) */
  type: string;
  /** What the component is given */
  props: CustomProps[S];
  /** What is shown if the model names no component for the slot (or one that does not exist) */
  fallback: JSX.Element;
  /** Show the fallback whatever the model names (when what the component needs is not there) */
  skip?: boolean;
}

/**
 * The component an interface module gives a model for a slot (`InterfaceMeta(item_page=...)` and the
 * others), given `props`, or `fallback` when the model names none. This is the one place that asks
 * the modules: the pages and cards of the library and the application use it, so each stays as it is
 * for a model that names nothing.
 */
export function Customised<S extends CustomSlot>(props: CustomisedProps<S>) {
  const custom = useCustom();
  const component = () => (props.skip ? undefined : custom(props.type, props.slot));
  return (
    <Show when={component()} fallback={props.fallback}>
      {(found) => <Dynamic component={found() as unknown as Component<Record<string, unknown>>} {...(props.props as unknown as Record<string, unknown>)} />}
    </Show>
  );
}
