import { createMemo, For, Show } from "solid-js";
import { buttonClass, numberBadgeClass, useApi, useComponent, useSessionKey, useTranslations } from "@pangloss/interface-core";
import { getCandidates } from "../api";
import type { Candidate, ReconcileCandidatesProps, SharedEntity } from "../api";
import { barWidth, countShown, itemHref, partsText, rowsOf, scoreText } from "../candidates";

/** An entity the document names that the candidate is named with elsewhere: its chip, and in how many documents if more than one */
function Shared(props: { entity: SharedEntity }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const count = () => t("reconcile_in_documents", "in {count} documents", { count: String(props.entity.documents) });
  return (
    <span class="inline-flex items-center gap-1" data-testid="reconcile-candidate-shared">
      <ReferenceChip type={props.entity.type} label={props.entity.label} href={itemHref(props.entity)} />
      <Show when={countShown(props.entity.documents)}>
        <span class={numberBadgeClass} title={count()} aria-label={count()}>
          {props.entity.documents}
        </span>
      </Show>
    </span>
  );
}

/**
 * One candidate: its chip (a link to its page), a bar as long as its score with the figure (as the Similar section's
 * rows), and Choose; under it, quietly, the entities of the document it is named with elsewhere
 */
function Row(props: { candidate: Candidate; onPick: ReconcileCandidatesProps["onPick"] }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const figure = () => scoreText(props.candidate.score, language());
  const parts = () => partsText(props.candidate.scores, language());
  return (
    <li
      class="col-span-4 grid grid-cols-subgrid items-center gap-y-1"
      data-testid="reconcile-candidate"
      data-id={props.candidate.id}
      data-score={String(props.candidate.score)}
    >
      <span class="min-w-0">
        <ReferenceChip type={props.candidate.type} label={props.candidate.label} href={itemHref(props.candidate)} />
      </span>
      {/* (slate only, as the Similar section's: a colour here would mean nothing) */}
      <span
        class="block h-1 w-24 bg-slate-200"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={props.candidate.score}
        aria-label={t("reconcile_score", "Score {value}: {parts}", { value: figure(), parts: parts() })}
        title={parts()}
      >
        <span class="block h-full bg-slate-500" style={{ width: barWidth(props.candidate.score) }} />
      </span>
      <span class="text-xs text-slate-500 tabular-nums" aria-hidden="true">
        {figure()}
      </span>
      <button
        type="button"
        class={buttonClass("quiet", "sm")}
        aria-label={t("reconcile_choose_named", "Choose {label}", { label: props.candidate.label })}
        data-testid="reconcile-candidate-choose"
        onClick={() =>
          props.onPick({ type: props.candidate.type, id: props.candidate.id, label: props.candidate.label })
        }
      >
        {t("reconcile_choose", "Choose")}
      </button>
      <Show when={props.candidate.shared.length > 0}>
        <span class="col-span-4 flex flex-wrap items-center gap-2" data-testid="reconcile-candidate-reasons">
          <span class="text-xs text-slate-500">{t("reconcile_also_named_with", "also named with")}</span>
          <For each={props.candidate.shared} keyed={(entity) => entity.id}>
            {(entity) => <Shared entity={entity()} />}
          </For>
        </span>
      </Show>
    </li>
  );
}

/**
 * The entities a mention may be (review's place `reconcileCandidates`, above the picker of its reconcile panel): the
 * best of `GET /api/reconcile/candidates/{id}`, each a row with Choose, which makes it the panel's choice. It reads
 * by itself, in a memo of the mention's id and the session (another mention, another request); the panel gives it a
 * boundary, which hides it while it loads and if it fails. Nothing at all (no heading) when there is no candidate to
 * show or the profile is still being built
 */
export default function ReconcileCandidates(props: ReconcileCandidatesProps) {
  const api = useApi();
  const session = useSessionKey();
  const { t } = useTranslations();
  const answer = createMemo(() => {
    session();
    return getCandidates(api, props.mention.id);
  });
  const rows = () => rowsOf(answer(), props.mention.id);
  return (
    <Show when={rows().length > 0}>
      <section class="flex flex-col gap-2" data-testid="reconcile-candidates">
        <span class="text-xs font-semibold text-slate-500 uppercase">{t("reconcile_suggested", "Suggested")}</span>
        {/* (a grid: the chips are one column, the bars, figures and buttons the others) */}
        <ul class="grid grid-cols-[minmax(0,max-content)_auto_auto_auto] items-center justify-start gap-x-3 gap-y-2">
          <For each={rows()} keyed={(candidate) => candidate.id}>
            {(candidate) => <Row candidate={candidate()} onPick={props.onPick} />}
          </For>
        </ul>
      </section>
    </Show>
  );
}
