import { references, useApi } from "@pangloss/interface-core";
import { createEffect, createSignal } from "solid-js";
import type { Accessor } from "solid-js";

/** An entity criteria name, as `/api/references` says it is now */
export interface Named {
  type: string;
  label: string;
}

export type Labels = ReadonlyMap<string, Named>;

/**
 * What the entities `ids` names are now, by id, from `/api/references` (one request for all of them, asked again
 * when the ids change): `undefined` until the answer has come, and on the server, which does not wait for it (a card
 * on an item's page is drawn with the page, and its chips follow in the browser). An id that is not in the answer is
 * of an entity that has been deleted
 */
export function createLabels(ids: Accessor<string[]>): Accessor<Labels | undefined> {
  const api = useApi();
  const [labels, setLabels] = createSignal<Labels | undefined>(undefined);
  let asked = 0;
  createEffect(
    () => [...new Set(ids())].sort().join(" "),
    (key) => {
      const ask = ++asked;
      const wanted = key === "" ? [] : key.split(" ");
      if (wanted.length === 0) {
        setLabels(new Map());
        return;
      }
      references(api, wanted).then(
        (found) => {
          if (ask === asked) setLabels(new Map(found.map((each) => [each.id, { type: each.type, label: each.label ?? "" }])));
        },
        () => {
          // (not known: the summary keeps "…" for them, and says no entity is gone)
        },
      );
    },
  );
  return labels;
}

/** The ids of `ids` that were not found (deleted entities); none while it is not known */
export function missing(ids: string[], labels: Labels | undefined): string[] {
  return labels === undefined ? [] : ids.filter((id) => !labels.has(id));
}
