import { Pager, useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import { createMemo, createSignal, For, Loading, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import { candidatesPage, hrefOf, SHOWN } from "../api";
import type { Candidate } from "../api";

/** How many candidates a page of the whole list has */
export const PAGE_SIZE = 25;

/**
 * Every linked candidate of a saved description, a page at a time, by label (`GET /api/criteria/{id}/candidates`):
 * chips; or, with `action`, a row for each, its chip and what `action` draws after it (the "This is the one" of
 * resolving). `empty` is said when there are none
 */
export function CandidatePages(props: { id: string; action?: (candidate: Candidate) => JSX.Element; empty?: string }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const { t } = useTranslations();
  const [page, setPage] = createSignal(1);
  const read = createMemo(() => candidatesPage(api, props.id, page(), PAGE_SIZE));
  const chip = (candidate: Candidate) => (
    <ReferenceChip type={candidate.type} label={candidate.label ?? candidate.id} href={hrefOf(candidate)} />
  );
  return (
    <div class="flex flex-col gap-3" data-testid="criteria-all-candidates">
      <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
        <Show
          when={read().candidates.length > 0}
          fallback={
            <p class="text-sm text-slate-500" data-testid="criteria-no-candidates">
              {props.empty ?? t("criteria_no_candidates", "No candidates")}
            </p>
          }
        >
          <Show
            when={props.action}
            fallback={
              <div class="flex flex-wrap gap-2">
                <For each={read().candidates}>{(candidate) => chip(candidate)}</For>
              </div>
            }
          >
            {(action) => (
              <ul class="flex flex-col gap-2">
                <For each={read().candidates}>
                  {(candidate) => (
                    <li class="flex min-w-0 items-center justify-between gap-3" data-testid="criteria-candidate-row">
                      {chip(candidate)}
                      {action()(candidate)}
                    </li>
                  )}
                </For>
              </ul>
            )}
          </Show>
        </Show>
        <Pager page={page()} pages={Math.max(1, Math.ceil(read().count / PAGE_SIZE))} onPage={setPage} />
      </Loading>
    </div>
  );
}

/**
 * The first candidates, each a chip, then what follows them (`after`: "and N more"); `faded`: they are the last found
 * of a description that is no longer evaluated
 */
export function CandidateChips(props: { candidates: Candidate[]; after?: JSX.Element; faded?: boolean }) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <Show when={props.candidates.length > 0}>
      <div
        class={["flex flex-wrap items-center gap-2", { "opacity-60": !!props.faded }]}
        data-faded={props.faded ? "" : undefined}
        data-testid="criteria-candidates"
      >
        <For each={props.candidates.slice(0, SHOWN)}>
          {(candidate) => <ReferenceChip type={candidate.type} label={candidate.label ?? candidate.id} href={hrefOf(candidate)} />}
        </For>
        {props.after}
      </div>
    </Show>
  );
}

/**
 * What a preview found, as the dialog and the closed card in a form say it: up to five chips and how many, or that
 * there are none yet, or that there are too many to link (then no chips: they would be the first of too many).
 * `note` follows the count ("not saved yet")
 */
export function PreviewResult(props: {
  count: number;
  tooBroad: boolean;
  candidates: Candidate[];
  note?: string;
  /** They are the last found of a description that is no longer evaluated */
  faded?: boolean;
}) {
  const { t } = useTranslations();
  const said = () => {
    if (props.tooBroad)
      return t("criteria_too_broad_preview", "Too broad: {count} found, more than are linked", { count: String(props.count) });
    if (props.count === 0) return t("criteria_none_yet", "No candidates yet: it will update as data is added");
    return props.count === 1
      ? t("criteria_found_one", "1 candidate found")
      : t("criteria_found", "{count} candidates found", { count: String(props.count) });
  };
  return (
    <div class="flex flex-col gap-2" data-testid="criteria-preview">
      <Show when={!props.tooBroad}>
        <CandidateChips candidates={props.candidates} faded={props.faded} />
      </Show>
      <p class="text-xs text-slate-500" data-testid="criteria-count">
        {said()}
        <Show when={props.note}>
          {" · "}
          <span class="font-semibold text-slate-600">{props.note}</span>
        </Show>
      </p>
    </div>
  );
}
