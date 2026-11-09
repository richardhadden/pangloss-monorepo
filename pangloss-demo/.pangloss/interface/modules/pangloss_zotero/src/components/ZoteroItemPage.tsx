import {
  fieldGridClass,
  fieldRowClass,
  ItemSections,
  useComponent,
  ExternalLink,
} from "@pangloss/interface-core";
import type { ItemPageProps } from "@pangloss/interface-core";
import { createMemo, For, Reveal, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { withoutZoteroFields } from "../zoteroItem";
import { useZoteroRows } from "../zoteroRows";
import { ZoteroControlled } from "./ZoteroIcon";

function Row(props: ParentProps<{ name: string }>) {
  return (
    <div class={fieldRowClass}>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">
        <ZoteroControlled />
        {props.name}
      </dt>
      <dd class="min-w-0 text-sm break-words whitespace-pre-wrap">{props.children}</dd>
    </div>
  );
}

/**
 * The page of an item that may be from Zotero (`item_page` of `ZoteroBacked`): its title, creators by role, address,
 * language and when it was synced, in place of the raw fields the sync writes. Then what any item page has, for what
 * the project's class adds (a Book's pages), what refers to it, and the modules' sections.
 */
export default function ZoteroItemPage(props: ItemPageProps) {
  const ItemContents = useComponent("ItemContents");
  const rest = createMemo(() => withoutZoteroFields(props.item));
  const rows = useZoteroRows(
    () => props.type,
    () => props.item,
  );
  return (
    <>
      <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
        {String(props.item.label ?? props.item.id)}
      </h1>
      <div class="@container mb-5 w-full min-w-0" data-testid="zotero-item">
        <dl class={fieldGridClass}>
          <For each={rows()} keyed={(row) => row.key}>
            {(row) => (
              <Row name={row().name}>
                <Show when={row().link} fallback={row().value}>
                  <ExternalLink href={row().value}>{row().value}</ExternalLink>
                </Show>
              </Row>
            )}
          </For>
        </dl>
      </div>
      <Reveal>
        <ItemContents item={rest()} />
        <ItemSections item={props.item} />
      </Reveal>
    </>
  );
}
