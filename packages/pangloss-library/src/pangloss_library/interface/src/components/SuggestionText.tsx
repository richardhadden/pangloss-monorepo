import { useModels, useTranslations } from "@pangloss/interface-core";
import type { PartActionProps } from "@pangloss/interface-core";
import { Show } from "solid-js";
import { Dynamic } from "@solidjs/web";

const SUGGESTION = "IdentificationByToolchain";

/**
 * In the form of a toolchain's suggestion that keeps what the source wrote (`IdentificationByToolchainFromText`, or a
 * project's subclass of a suggestion with a `text`; `partActions`, first in its body): the text, shown and not
 * edited. It is what the toolchain read; the form leaves the field out (`hide_on_forms`), so it is sent back as it
 * was read. (In an `IdentificationFromText`, which a person may make, `text` is an ordinary field of the form.)
 */
export function SuggestionText(props: PartActionProps) {
  const definitions = useModels();
  const { fieldName } = useTranslations();
  // (the class, or a project's subclass of it at any remove)
  const suggested = () => {
    const seen = new Set<string>();
    for (let name: string | null | undefined = props.type; name && !seen.has(name); name = definitions.models[name]?.parent) {
      if (name === SUGGESTION) return true;
      seen.add(name);
    }
    return false;
  };
  const text = () =>
    props.place === "body" && suggested() && typeof props.item.text === "string" ? props.item.text : "";
  return (
    <Show when={text() && props.Row}>
      {/* (the row is the form's, given: importing it would bring the form's code to every reader) */}
      <Dynamic component={props.Row} name={fieldName(props.type, "text")}>
        <p class="min-w-0 py-1 text-sm break-words text-slate-700" data-testid="suggestion-text">
          {text()}
        </p>
      </Dynamic>
    </Show>
  );
}
