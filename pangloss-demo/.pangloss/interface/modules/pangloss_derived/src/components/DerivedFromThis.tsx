import { createMemo, For, Loading, Show } from "solid-js";
import { SectionBar, useApi, useComponent, useSessionKey, useTranslations } from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { getDerivedFrom } from "../api";
import type { DerivedFromRow } from "../api";

/** No more derived documents than this are shown as chips: a factoid about a large family is the source of thousands */
export const SHOWN = 50;

/**
 * "Derived from this" (a section after an item's contents): the derived documents that rest on a document or on a
 * part of it, as chips. Nothing for a document nothing is derived from. Those the reader may not see are counted.
 */
export default function DerivedFromThis(props: ItemSectionProps) {
  const api = useApi();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const session = useSessionKey();
  const rows = createMemo((): Promise<DerivedFromRow[]> => {
    session();
    const meta = props.item.meta as Record<string, unknown> | undefined;
    // (a head document only: an entity is never a source, and a part is shown with its document)
    const asked = props.model.kind === "Document" && !!meta && !meta.headNodeId;
    return asked ? getDerivedFrom(api, props.type, props.id).catch(() => []) : Promise.resolve([]);
  });
  // (a document that rests on two parts of this one is one document)
  const documents = createMemo(() => {
    const found = new Map<string, DerivedFromRow>();
    for (const row of rows()) if (row.id && !found.has(row.id)) found.set(row.id, row);
    return [...found.values()];
  });
  const hidden = () => rows().filter((row) => row.hidden).length;
  return (
    <Loading>
      <Show when={rows().length > 0}>
        <section data-testid="derived-from-this">
          <SectionBar>{t("derived_from_this", "Derived from this ({count})", { count: documents().length + hidden() })}</SectionBar>
          <div class="flex flex-wrap items-center gap-2">
            <For each={documents().slice(0, SHOWN)}>
              {(row) => (
                <ReferenceChip
                  type={row.type ?? ""}
                  label={row.label ?? row.id ?? ""}
                  href={`/${encodeURIComponent(row.type ?? "")}/${encodeURIComponent(row.id ?? "")}`}
                />
              )}
            </For>
            <Show when={documents().length > SHOWN}>
              <span class="text-sm text-slate-500">
                {t("derived_more", "and {count} more", { count: documents().length - SHOWN })}
              </span>
            </Show>
            <Show when={hidden() > 0}>
              <span class="text-sm text-slate-500">
                {t("derived_from_hidden", "{count} not yet published", { count: hidden() })}
              </span>
            </Show>
          </div>
        </section>
      </Show>
    </Loading>
  );
}
