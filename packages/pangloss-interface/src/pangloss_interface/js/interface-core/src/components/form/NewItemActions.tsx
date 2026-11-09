import { Errored, For, Loading, Show } from "solid-js";
import type { Component } from "solid-js";
import { useModules } from "../../context";
import type { EditItemFieldProps, ModelDefinition, NewItemActionProps, NewItemForm } from "../../types";

type Props = { type: string; model: ModelDefinition; form: NewItemForm };

/** Each of `parts`, given the form. One that fails, or is still loading, shows nothing, and the rest are unaffected. */
function Each(props: Props & { parts: Component<NewItemActionProps>[]; what: string }) {
  return (
    <Show when={props.parts.length > 0}>
      <For each={props.parts}>
        {(Part) => (
          <Errored
            fallback={(error) => {
              // (said in the browser's console, so that a module's author sees why there is nothing)
              console.error(`A ${props.what} of an interface module failed:`, error());
              return null;
            }}
          >
            <Loading fallback={null}>
              <Part type={props.type} model={props.model} form={props.form} />
            </Loading>
          </Errored>
        )}
      </For>
    </Show>
  );
}

/** What the interface modules add to the console of the form that makes a new item (their `newItemActions`) */
export function NewItemActions(props: Props) {
  return <Each {...props} parts={useModules().newItemActions()} what="new-item action" />;
}

/**
 * What the interface modules add first among the fields of the form that makes a new item (their `newItemFields`):
 * rows of the form's grid
 */
export function NewItemFields(props: Props) {
  return <Each {...props} parts={useModules().newItemFields()} what="new-item field" />;
}

/** What the interface modules add first among the fields of the form that edits an item (their `editItemFields`) */
export function EditItemFields(props: EditItemFieldProps) {
  return (
    <For each={useModules().editItemFields()}>
      {(Part) => (
        <Errored
          fallback={(error) => {
            console.error("An edit-item field of an interface module failed:", error());
            return null;
          }}
        >
          <Loading fallback={null}>
            <Part type={props.type} model={props.model} get={props.get} />
          </Loading>
        </Errored>
      )}
    </For>
  );
}
