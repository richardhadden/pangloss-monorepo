import { FieldRow, inputClass } from "@pangloss/interface-core";
import type { EditItemFieldProps } from "@pangloss/interface-core";
import { For } from "solid-js";
import { fromForm, useZoteroRows } from "../zoteroRows";
import { ZoteroControlled } from "./ZoteroIcon";

/** On the form of an item from Zotero (an `editItemFields` entry), what Zotero says of it, to see and not to change */
export default function ZoteroFormRows(props: EditItemFieldProps) {
  const rows = useZoteroRows(
    () => props.type,
    () => fromForm(props.get),
  );
  return (
    <For each={rows()} keyed={(row) => row.key}>
      {(row) => (
        <FieldRow name={row().name} icon={<ZoteroControlled />}>
          <input
            type="text"
            disabled
            class={[inputClass, "cursor-not-allowed bg-slate-100 text-slate-500"]}
            aria-label={row().name}
            title={row().value}
            value={row().value}
          />
        </FieldRow>
      )}
    </For>
  );
}
