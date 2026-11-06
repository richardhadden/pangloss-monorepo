import { createMemo, For, Show } from "solid-js";
import { useModels } from "../context";
import { getModel } from "../schema";
import type { FieldDefinition, FieldListProps } from "../types";

function describe(field: FieldDefinition): string {
  switch (field.kind) {
    case "literal":
      return field.type.type;
    case "list":
      return `list of ${field.item.type}`;
    case "relation":
      return `${field.many ? "relations" : "relation"} to ${field.options
        .map((option) => ("type" in option ? option.type : option.name))
        .join(" | ")}`;
    case "embedded":
      return `embedded ${field.model ?? ""}`;
    case "annotatedValue":
      return `${field.model} value`;
    case "typeVar":
      return `${field.typeVar}`;
    default:
      return field.kind;
  }
}

/** (a placeholder: what a model has, from its definition) */
export function FieldList(props: FieldListProps) {
  const definitions = useModels();
  // (read in a computation, so that it follows the prop)
  const model = createMemo(() => getModel(definitions, props.model));
  return (
    <Show when={model()} fallback={<p>No model called {props.model}</p>}>
      {(definition) => (
        <ul class="pg-field-list">
          <For each={definition().fields}>
            {(field) => (
              <li>
                <strong>{field.name}</strong> ({describe(field)})
                <Show when={field.required}> *</Show>
              </li>
            )}
          </For>
        </ul>
      )}
    </Show>
  );
}
