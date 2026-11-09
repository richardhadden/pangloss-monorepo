import {
  fieldGridClass,
  fieldRowClass,
  ItemSections,
  useComponent,
  useTranslations,
  ExternalLink,
} from "@pangloss/interface-core";
import type { ItemPageProps } from "@pangloss/interface-core";
import { createMemo, For, Reveal, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { creatorGroups, readableTime, roleWords, webAddress, withoutZoteroFields, zoteroData } from "../zoteroItem";

function Row(props: ParentProps<{ name: string }>) {
  return (
    <div class={fieldRowClass}>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">{props.name}</dt>
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
  const { t, language, fieldName } = useTranslations();
  const data = createMemo(() => zoteroData(props.item));
  const rest = createMemo(() => withoutZoteroFields(props.item));
  const title = () => (typeof props.item.title === "string" ? props.item.title : "");
  const url = () => webAddress(data());
  const itemLanguage = () => (typeof props.item.language === "string" ? props.item.language : "");
  const synced = () => readableTime(props.item.syncedWhen, language());
  return (
    <>
      <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
        {String(props.item.label ?? props.item.id)}
      </h1>
      <div class="@container mb-5 w-full min-w-0" data-testid="zotero-item">
        <dl class={fieldGridClass}>
          <Show when={title()}>
            <Row name={fieldName(props.type, "title")}>{title()}</Row>
          </Show>
          <For each={creatorGroups(props.item, data())}>
            {(group) => (
              <Row
                name={
                  group.role
                    ? t(`zotero_creator_${group.role}`, roleWords(group.role))
                    : t("zotero_creators", "Creators")
                }
              >
                {group.names.join("; ")}
              </Row>
            )}
          </For>
          <Show when={url()}>
            {(address) => (
              <Row name={t("zotero_url", "URL")}>
                <ExternalLink href={address()}>{address()}</ExternalLink>
              </Row>
            )}
          </Show>
          <Show when={itemLanguage()}>
            <Row name={fieldName(props.type, "language")}>{itemLanguage()}</Row>
          </Show>
          <Show when={synced()}>
            <Row name={fieldName(props.type, "synced_when")}>{synced()}</Row>
          </Show>
        </dl>
      </div>
      <Reveal>
        <ItemContents item={rest()} />
        <ItemSections item={props.item} />
      </Reveal>
    </>
  );
}
