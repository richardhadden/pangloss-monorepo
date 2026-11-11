import {
  buttonClass,
  Modal,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { confirmSuggestion, getSimilarSuggestions, getSuggestion } from "../api";
import type { Confirmed, Suggestion } from "../api";
import { hrefOf, reasonOf, TickIcon } from "./taskIcons";

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

function Contents(props: { id: string; onDone: (done: Confirmed) => void; onClose: () => void }) {
  const api = useApi();
  const toasts = useToasts();
  const { t } = useTranslations();
  // (as it is saved: one that is not there has not been saved yet, or was confirmed meanwhile)
  const suggestion = createMemo(() => getSuggestion(api, props.id));
  const similar = createMemo(() => getSimilarSuggestions(api, props.id));
  const [chosen, setChosen] = createSignal<Record<string, boolean>>({});
  const [busy, setBusy] = createSignal(false);
  // (the toolchain, and which version of it)
  const suggestedBy = () => [suggestion().identifiedBy, suggestion().toolchainVersion].filter(Boolean).join(" ");
  const all = () => similar().length > 0 && similar().every((row) => chosen()[row.id]);
  const confirm = () => {
    setBusy(true);
    const also = Object.entries(chosen())
      .filter(([, on]) => on)
      .map(([id]) => id);
    confirmSuggestion(api, props.id, also)
      .then((done) => {
        toasts?.show(
          done.queued > 0
            ? t("review_confirmed_more", "Confirmed; {count} more in the background", { count: String(done.queued) })
            : t("review_confirmed", "Confirmed"),
        );
        if (done.urisTaken.length > 0)
          toasts?.show(
            t("review_uris_taken", "Not given (another item has them): {uris}", { uris: done.urisTaken.join(", ") }),
            "error",
          );
        props.onDone(done);
      })
      .catch((error: unknown) => {
        console.error(error);
        toasts?.show(t("review_confirm_refused", "Not confirmed: {reason}", { reason: reasonOf(error) }), "error");
      })
      .finally(() => setBusy(false));
  };
  return (
    <div class="flex min-w-0 flex-col gap-4" data-testid="confirm-panel">
      <SuggestionWhere suggestion={suggestion()} />
      <p class="text-sm text-slate-600">
        <Show
          when={suggestedBy()}
          fallback={t("review_confirm_help", "Confirming says that you have checked it: it becomes your identification.")}
        >
          {t(
            "review_confirm_help_by",
            "Suggested by {toolchain}. Confirming says that you have checked it: it becomes your identification.",
            { toolchain: suggestedBy() },
          )}
        </Show>
      </p>
      <Show when={suggestion().uris.length > 0}>
        <p class="text-xs break-all text-slate-600" data-testid="confirm-uris">
          <Show
            when={suggestion().candidates.length === 1}
            fallback={t("review_uris_not_given", "URIs (given only when there is one candidate): {uris}", {
              uris: suggestion().uris.join(", "),
            })}
          >
            {t("review_uris", "URIs to give: {uris}", { uris: suggestion().uris.join(", ") })}
          </Show>
        </p>
      </Show>
      <Show
        when={similar().length > 0}
        fallback={
          <p class="py-2 text-sm text-slate-500" data-testid="confirm-no-similar">
            {t("review_similar_suggestions_none", "No other suggestion says the same")}
          </p>
        }
      >
        <p class="text-sm text-slate-600">
          {t(
            "review_similar_suggestions_help",
            "These suggest the same candidates, about as likely. Tick those to give the same identification, in the background.",
          )}
        </p>
        <table class={tableClass} data-testid="confirm-similar">
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={[tableHeadCellClass, "w-8"]}>
                <input
                  type="checkbox"
                  aria-label={t("review_select_all", "All of them")}
                  checked={all()}
                  onChange={(event) =>
                    setChosen(Object.fromEntries(similar().map((row) => [row.id, event.currentTarget.checked])))
                  }
                />
              </th>
              <th class={tableHeadCellClass}>{t("review_suggestion", "Suggestion")}</th>
            </tr>
          </thead>
          <tbody>
            <For each={similar()}>
              {(row) => (
                <tr class={tableRowClass} data-testid="confirm-similar-row">
                  <td class={tableCellClass}>
                    <input
                      type="checkbox"
                      aria-label={t("review_also_confirm", "This one too")}
                      checked={chosen()[row.id] ?? false}
                      onChange={(event) => setChosen({ ...chosen(), [row.id]: event.currentTarget.checked })}
                    />
                  </td>
                  <td class={tableCellClass}>
                    <SuggestionWhere suggestion={row} />
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
      </Show>
      <div class="flex justify-end gap-2">
        <button type="button" class={buttonClass("ordinary", "md")} onClick={props.onClose}>
          {t("cancel", "Cancel")}
        </button>
        <button
          type="button"
          class={buttonClass("primary", "md")}
          disabled={busy()}
          data-testid="confirm-submit"
          onClick={confirm}
        >
          <TickIcon />
          {t("review_confirm", "Confirm")}
        </button>
      </div>
    </div>
  );
}

/** Confirming an identification that a toolchain suggested, in a dialog: what it says, and the others that say the same */
export default function ConfirmDialog(props: { id: string; onDone: (done: Confirmed) => void; onClose: () => void }) {
  const { t } = useTranslations();
  return (
    <Modal title={t("review_confirm_title", "Confirm an identification")} onClose={props.onClose} size="lg">
      <div class="overflow-y-auto p-4" data-testid="confirm-dialog">
        <Errored
          fallback={() => (
            <p class="text-sm text-slate-700" data-testid="confirm-not-saved">
              {t("review_not_saved", "This is not in the saved document (any more). Save the document first.")}
            </p>
          )}
        >
          <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
            <Contents id={props.id} onDone={props.onDone} onClose={props.onClose} />
          </Loading>
        </Errored>
      </div>
    </Modal>
  );
}
