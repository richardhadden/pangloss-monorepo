import { buttonClass, firstParam, readableTime, useApi, useTranslations, userIsLoggedIn } from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { createMemo, For, Show } from "solid-js";
import { mergeHref, mergesOf, stands } from "../api";
import type { MergeRecord } from "../api";
import { absorbedOf, HeadChip, Notice, survivorOf } from "./parts";

/** The notices of one entity: read here, for someone logged in */
function Notices(props: { type: string; id: string; arrivedBy: string | undefined }) {
  const api = useApi();
  const { t, language } = useTranslations();
  const merges = createMemo(() =>
    // (a notice is a help: if they cannot be read, the page is shown without)
    mergesOf(api, props.type, props.id).catch((): MergeRecord[] => []),
  );
  const other = (record: MergeRecord) => (record.survivor === props.id ? absorbedOf(record) : survivorOf(record));
  const proposed = () => merges().filter((record) => record.state === "proposed");
  const undoProposed = () => merges().filter((record) => stands(record) && !!record.undoProposedBy);
  // (the merge that brought the reader here: they asked for the entity it absorbed)
  const arrived = () =>
    merges().filter((record) => stands(record) && props.arrivedBy !== undefined && record.absorbed === props.arrivedBy);
  return (
    <Show when={proposed().length + undoProposed().length + arrived().length > 0}>
      <div class="mb-6 flex flex-col gap-2" data-testid="merge-notices">
        <For each={arrived()}>
          {(record) => (
            <Notice testid="merge-notice-merged">
              <HeadChip head={absorbedOf(record)} plain />
              <span>
                {t("merge_notice_merged", "was merged into this, {when}, by {who}.", {
                  when: readableTime(record.when, language()),
                  who: record.by ?? "?",
                })}
              </span>
              <a class={buttonClass("ordinary")} href={mergeHref(record.id)}>
                {t("merge_notice_undo", "Look at the merge, or undo it")}
              </a>
            </Notice>
          )}
        </For>
        <For each={proposed()}>
          {(record) => (
            <Notice tone="waiting" testid="merge-notice-proposed">
              <span>{t("merge_notice_proposed", "{who} proposed a merge with", { who: record.proposedBy ?? "?" })}</span>
              <HeadChip head={other(record)} />
              <a class={buttonClass("ordinary")} href={mergeHref(record.id)}>
                {t("merge_notice_review", "Look at it")}
              </a>
            </Notice>
          )}
        </For>
        <For each={undoProposed()}>
          {(record) => (
            <Notice tone="waiting" testid="merge-notice-undo-proposed">
              <span>
                {t("merge_notice_undo_proposed", "{who} proposed undoing the merge with", {
                  who: record.undoProposedBy ?? "?",
                })}
              </span>
              <HeadChip head={other(record)} />
              <a class={buttonClass("ordinary")} href={mergeHref(record.id)}>
                {t("merge_notice_review", "Look at it")}
              </a>
            </Notice>
          )}
        </For>
      </div>
    </Show>
  );
}

/**
 * What a reader of an entity's page should see first (an `itemNotices` entry): a merge of it that someone proposed,
 * an undo that someone proposed, and, for someone who asked for an entity that was merged into this one
 * (`?merged=<its id>`, which the page adds when it shows the survivor instead), that it was. For someone logged in,
 * as the merges are; nothing for a document.
 */
export default function MergeNotices(props: ItemSectionProps) {
  const [search] = useSearchParams();
  return (
    <Show when={props.model.kind === "Entity" && userIsLoggedIn()}>
      <Notices type={props.type} id={props.id} arrivedBy={firstParam(search.merged)} />
    </Show>
  );
}
