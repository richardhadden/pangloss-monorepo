import {
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import type { JSX } from "@solidjs/web";
import { For, Show } from "solid-js";
import type { Mention, Suggestion } from "../api";
import { MentionChip } from "./MentionChip";
import { hrefOf } from "./taskIcons";

/** A mention where it is: its chip, then the document it is in */
export function MentionWhere(props: { mention: Mention }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-2">
      <MentionChip type={props.mention.unreconciledType} label={props.mention.label} />
      <span class="text-xs font-semibold text-slate-500 uppercase">{t("review_in", "in")}</span>
      <ReferenceChip
        type={props.mention.holder.type}
        label={props.mention.holder.label ?? props.mention.holder.id}
        href={hrefOf(props.mention.holder)}
      />
    </span>
  );
}

/** Who a suggestion could be: a chip each, with how likely at its end */
export function Candidates(props: { suggestion: Suggestion }) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-2" data-testid="suggestion-candidates">
      <For each={props.suggestion.candidates}>
        {(candidate) => (
          <span class="inline-flex min-w-0 items-center gap-1">
            <ReferenceChip type={candidate.type} label={candidate.label ?? candidate.id} href={hrefOf(candidate)} />
            <Show when={candidate.percent !== null && candidate.percent !== undefined}>
              <span class="text-xs text-slate-600 tabular-nums">{candidate.percent}%</span>
            </Show>
          </span>
        )}
      </For>
    </span>
  );
}

/** A suggestion where it is: its candidates, then the document it is in */
export function SuggestionWhere(props: { suggestion: Suggestion }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-2">
      <Candidates suggestion={props.suggestion} />
      <span class="text-xs font-semibold text-slate-500 uppercase">{t("review_in", "in")}</span>
      <ReferenceChip
        type={props.suggestion.holder.type}
        label={props.suggestion.holder.label ?? props.suggestion.holder.id}
        href={hrefOf(props.suggestion.holder)}
      />
    </span>
  );
}

/** Why a row is offered, and where it is: after what it is */
export function RowNotes(props: { sameUri?: boolean; inForm: boolean }) {
  const { t } = useTranslations();
  return (
    <span class="ml-2 inline-flex gap-2 text-xs font-semibold text-slate-500 uppercase">
      <Show when={props.sameUri}>
        <span data-testid="same-uri">{t("review_same_uri", "same URI")}</span>
      </Show>
      <Show when={props.inForm}>
        <span data-testid="in-this-document">{t("review_in_this_document", "in this document")}</span>
      </Show>
    </span>
  );
}

/** A table of parts to do with this one, each with a box */
export function Offered<T extends { id: string }>(props: {
  rows: T[];
  heading: string;
  testid: string;
  chosen: (row: T) => boolean;
  onToggle: (rows: T[], on: boolean) => void;
  children: (row: T) => JSX.Element;
}) {
  const { t } = useTranslations();
  const all = () => props.rows.every(props.chosen);
  return (
    <table class={tableClass} data-testid={props.testid}>
      <thead>
        <tr class={tableHeadRowClass}>
          <th class={[tableHeadCellClass, "w-8"]}>
            <input
              type="checkbox"
              aria-label={t("review_select_all", "All of them")}
              checked={all()}
              onChange={(event) => props.onToggle(props.rows, event.currentTarget.checked)}
            />
          </th>
          <th class={tableHeadCellClass}>{props.heading}</th>
        </tr>
      </thead>
      <tbody>
        <For each={props.rows}>
          {(row) => (
            <tr class={tableRowClass} data-testid={`${props.testid}-row`}>
              <td class={tableCellClass}>
                <input
                  type="checkbox"
                  aria-label={t("review_also_confirm", "This one too")}
                  checked={props.chosen(row)}
                  onChange={(event) => props.onToggle([row], event.currentTarget.checked)}
                />
              </td>
              <td class={tableCellClass}>{props.children(row)}</td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}

