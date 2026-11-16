import { buttonClass, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import { mergeHref } from "../api";
import type { MergeResult } from "../api";
import { HeadChip, Heading, Notice, Pair } from "./parts";

/** What a merge that has just been made did, with the documents a person should look at */
export function MergeSummary(props: { result: MergeResult }) {
  const { t } = useTranslations();
  const merge = () => props.result.merge;
  return (
    <div class="flex flex-col gap-3" data-testid="merge-summary">
      <Notice>
        <Pair record={merge()} />
        <span data-testid="merge-summary-counts">
          {t("merge_summary", "Merged: {moved} references moved, in {heads} documents and entities.", {
            moved: merge().moved.toLocaleString(),
            heads: merge().heads.toLocaleString(),
          })}
        </span>
      </Notice>
      <Show when={props.result.collapsed.length > 0}>
        <Heading>{t("merge_summary_collapsed", "These named both in one relation, and now name the survivor once: look at them")}</Heading>
        <div class="flex flex-wrap gap-2" data-testid="merge-summary-collapsed">
          <For each={props.result.collapsed}>{(head) => <HeadChip head={head} />}</For>
        </div>
      </Show>
      <Show when={props.result.both.length > 0}>
        <Heading>{t("merge_summary_both", "These named both in different relations, and now name the survivor in each: look at them")}</Heading>
        <div class="flex flex-wrap gap-2" data-testid="merge-summary-both">
          <For each={props.result.both}>{(head) => <HeadChip head={head} />}</For>
        </div>
      </Show>
      <Show when={props.result.kept > 0}>
        <p class="text-sm">
          {t("merge_summary_kept", "{kept} references stay on the entity absorbed, as their relations say they must.", {
            kept: props.result.kept.toLocaleString(),
          })}
        </p>
      </Show>
      <div class="mt-4 flex justify-end">
        <a class={buttonClass("ordinary", "md")} href={mergeHref(merge().id)} data-testid="merge-summary-record">
          {t("merge_summary_record", "The record of this merge (to undo it)")}
        </a>
      </div>
    </div>
  );
}
