import { Errored, For, Loading, Show } from "solid-js";
import { useModules } from "../../context";
import type { ModelDefinition, NewItemForm } from "../../types";

/**
 * What the interface modules add to the console of the form that makes a new item (their `newItemActions`), each given
 * the form. One that fails, or is still loading, shows nothing, and the rest of the console is unaffected.
 */
export function NewItemActions(props: { type: string; model: ModelDefinition; form: NewItemForm }) {
  const actions = useModules().newItemActions();
  return (
    <Show when={actions.length > 0}>
      <For each={actions}>
        {(Action) => (
          <Errored
            fallback={(error) => {
              // (said in the browser's console, so that a module's author sees why there is nothing)
              console.error("A new-item action of an interface module failed:", error());
              return null;
            }}
          >
            <Loading fallback={null}>
              <Action type={props.type} model={props.model} form={props.form} />
            </Loading>
          </Errored>
        )}
      </For>
    </Show>
  );
}
