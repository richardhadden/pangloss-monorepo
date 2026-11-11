import { useModels, useTranslations } from "@pangloss/interface-core";
import type { PartActionProps } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import { Dynamic } from "@solidjs/web";

const IDENTIFICATION = "Identification";

/**
 * In the form of an identification that has URIs (`partActions`, first in its body): one that a toolchain suggested,
 * or one confirmed with several candidates still, which keeps them. The URIs the toolchain gave for who it is, as links. They are shown and not edited: they are what the toolchain said, and what
 * other parts that name them are found by; the form leaves the field out (`hide_on_forms`), so it is sent back as
 * it was read.
 */
export function SuggestionUris(props: PartActionProps) {
  const definitions = useModels();
  const { fieldName } = useTranslations();
  // (the class, or a project's subclass of it at any remove)
  const suggested = () => {
    const seen = new Set<string>();
    for (let name: string | null | undefined = props.type; name && !seen.has(name); name = definitions.models[name]?.parent) {
      if (name === IDENTIFICATION) return true;
      seen.add(name);
    }
    return false;
  };
  const uris = () =>
    props.place === "body" && suggested() && Array.isArray(props.item.uris)
      ? props.item.uris.filter((uri): uri is string => typeof uri === "string")
      : [];
  return (
    <Show when={uris().length > 0 && props.Row}>
      {/* (the row is the form's, given: importing it would bring the form's code to every reader) */}
      <Dynamic component={props.Row} name={fieldName(props.type, "uris")}>
        <ul class="flex min-w-0 flex-col gap-0.5 py-1 text-sm text-slate-700" data-testid="suggestion-uris">
          <For each={uris()}>
            {(uri) => (
              <li class="truncate">
                <a href={uri} class="underline hover:text-slate-900" rel="noreferrer" target="_blank">
                  {uri}
                </a>
              </li>
            )}
          </For>
        </ul>
      </Dynamic>
    </Show>
  );
}
