import {
  buttonClass,
  DefaultReferenceChip,
  getModel,
  PickOrCreate,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useModels,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import { createEffect, createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { getSimilarMentions, getSuggestionsOfMention, reconcileMention } from "../api";
import type { Mention, Reconciled, Ref, SimilarMention, Suggestion } from "../api";
import { hrefOf, reasonOf, SpannerIcon } from "./taskIcons";
import { MentionWhere, Offered, RowNotes, SuggestionWhere } from "./where";

/** Whether a part of the form's own document is still what it was there (not reconciled, confirmed or taken out) */
export type StillThere = (id: string, kind: "mention" | "suggestion") => boolean;

/** What was ticked that is in the document of the mention: for its form to change with it */
export interface DoneHere {
  mentions: string[];
  suggestions: Suggestion[];
}

/** The other mentions that may be of the same thing, each with a box to reconcile it too */
function Similar(props: {
  mention: Mention;
  chosen: (row: SimilarMention) => boolean;
  onToggle: (row: SimilarMention, on: boolean) => void;
  onLoaded: (rows: SimilarMention[]) => void;
  /** (in a form) Of the mention's own document, only those the form still has as they were */
  stillThere?: StillThere;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const read = createMemo(() => getSimilarMentions(api, props.mention.id));
  // (what is offered is what can be chosen: the panel is told, in a plain name and not a signal, as this is drawn)
  const similar = () => {
    const rows = read().filter(
      (row) => row.head.id !== props.mention.head.id || !props.stillThere || props.stillThere(row.id, "mention"),
    );
    props.onLoaded(rows);
    return rows;
  };
  return (
    <Show
      when={similar().length > 0}
      fallback={
        <p class="py-2 text-sm text-slate-500" data-testid="reconcile-no-similar">
          {t("review_similar_none", "No other mention is like this one")}
        </p>
      }
    >
      <p class="mb-2 text-sm text-slate-600">
        {t(
          "review_similar_help",
          "These may be the same: they name the same URI or have the same label (ticked), or one much like it. Those ticked are reconciled with it as well.",
        )}
      </p>
      <table class={tableClass} data-testid="reconcile-similar">
        <thead>
          <tr class={tableHeadRowClass}>
            <th class={[tableHeadCellClass, "w-8"]} />
            <th class={tableHeadCellClass}>{t("review_mention", "Mention")}</th>
            <th class={[tableHeadCellClass, "text-right"]}>{t("review_likeness", "Alike")}</th>
          </tr>
        </thead>
        <tbody>
          <For each={similar()}>
            {(row) => (
              <tr class={tableRowClass} data-testid="reconcile-similar-row" data-exact={String(row.exact)}>
                <td class={tableCellClass}>
                  <input
                    type="checkbox"
                    aria-label={t("review_also", "Reconcile {label} too", { label: row.label })}
                    checked={props.chosen(row)}
                    onChange={(event) => props.onToggle(row, event.currentTarget.checked)}
                  />
                </td>
                <td class={tableCellClass}>
                  <MentionWhere mention={row} />
                  <RowNotes sameUri={row.sameUri} inForm={!!props.stillThere && row.head.id === props.mention.head.id} />
                </td>
                <td class={[tableCellClass, "text-right text-slate-600 tabular-nums"]}>
                  <Show when={!row.exact} fallback={t("review_same", "same")}>
                    {Math.round(row.score * 100)}%
                  </Show>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
    </Show>
  );
}

/** The identifications a toolchain suggested that name a URI of the mention, each with a box to confirm it as the entity */
function SameUriSuggestions(props: {
  mention: Mention;
  chosen: (row: Suggestion) => boolean;
  onToggle: (rows: Suggestion[], on: boolean) => void;
  onLoaded: (rows: Suggestion[]) => void;
  stillThere?: StillThere;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const read = createMemo(() => (props.mention.uris.length > 0 ? getSuggestionsOfMention(api, props.mention.id) : []));
  const rows = () => {
    const found = read().filter(
      (row) => row.head.id !== props.mention.head.id || !props.stillThere || props.stillThere(row.id, "suggestion"),
    );
    props.onLoaded(found);
    return found;
  };
  return (
    <Show when={rows().length > 0}>
      <p class="mb-2 text-sm text-slate-600">
        {t(
          "review_same_uri_suggestions_help",
          "These identifications suggested by a toolchain name the same URI. Those ticked are confirmed as who it is reconciled with.",
        )}
      </p>
      <Offered
        rows={rows()}
        heading={t("review_suggestion", "Suggestion")}
        testid="reconcile-suggestions"
        chosen={props.chosen}
        onToggle={props.onToggle}
      >
        {(row) => (
          <>
            <SuggestionWhere suggestion={row} />
            <RowNotes sameUri inForm={!!props.stillThere && row.head.id === props.mention.head.id} />
          </>
        )}
      </Offered>
    </Show>
  );
}

/**
 * Reconciling one mention: find the entity it is (or make one), tick the other parts that are of the same, and
 * Reconcile. The entity takes the mention's place in its document at once; the others are done in the background:
 * the mentions that name the same URI or have the same label (ticked) or one like it, and the identifications a
 * toolchain suggested that name its URI (ticked), which are confirmed as the entity. An entity that has its URI
 * already is put forward. In a dialog (`ReconcileDialog`) and on the page of reconciliations.
 *
 * In the form of its document (`inForm`) the document is not written: the form is given the entity (`onDone`) and
 * what was ticked that is in the same document, and changes them, saved with the rest; the entity is given the
 * URIs, and what was ticked in other documents is done.
 */
export function ReconcilePanel(props: {
  mention: Mention;
  onDone: (done: Reconciled, here: DoneHere) => void;
  onCancel?: () => void;
  inForm?: boolean;
  stillThere?: StillThere;
}) {
  const api = useApi();
  const definitions = useModels();
  const toasts = useToasts();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, modelName } = useTranslations();
  // (who has its URI already: that is who it is, unless the reader says otherwise)
  const known = () => ((props.mention.known ?? []).length === 1 ? props.mention.known?.[0] : undefined);
  // (what the reader chose: nothing yet, an entity, or `null` once what was put forward is turned down)
  const [choice, setChoice] = createSignal<Ref | null>();
  const entity = () => (choice() === undefined ? known() : (choice() ?? undefined));
  // (the boxes as the reader left them: one not touched is ticked if it names the same URI or has the same label)
  const [toggled, setToggled] = createSignal<Record<string, boolean>>({});
  // (the rows of the tables, as they were read: plain names, set while they draw)
  let offered: SimilarMention[] = [];
  let suggested: Suggestion[] = [];
  const [busy, setBusy] = createSignal(false);
  // (another mention: nothing chosen yet)
  createEffect(
    () => props.mention.id,
    () => {
      setChoice(undefined);
      setToggled({});
      offered = [];
      suggested = [];
    },
  );
  const chosen = (row: SimilarMention) => toggled()[row.id] ?? (row.exact || !!row.sameUri);
  const confirmed = (row: Suggestion) => toggled()[row.id] ?? true;
  const here = (row: { head: Ref }) => !!props.inForm && row.head.id === props.mention.head.id;
  const types = () => getModel(definitions, props.mention.unreconciledType)?.concreteTypes ?? [props.mention.unreconciledType];
  const reconcile = () => {
    const found = entity();
    if (!found) return;
    setBusy(true);
    const mentions = offered.filter(chosen);
    const suggestions = suggested.filter(confirmed);
    reconcileMention(
      api,
      props.mention.id,
      found,
      mentions.map((row) => row.id),
      props.inForm,
      suggestions.map((row) => row.id),
    )
      .then((done) => {
        const label = done.entity.label ?? "";
        const count = String(done.queued);
        if (props.inForm) {
          toasts?.show(t("review_reconciled_in_form", "Reconciled with {label}: it is saved with the document", { label }));
          if (done.queued > 0)
            toasts?.show(t("review_reconciling_others", "{count} more are being reconciled, in the background", { count }));
        } else
          toasts?.show(
            done.queued > 0
              ? t("review_reconciled_more", "Reconciled with {label}; {count} more in the background", { label, count })
              : t("review_reconciled", "Reconciled with {label}", { label }),
          );
        if (done.urisTaken.length > 0)
          toasts?.show(
            t("review_uris_taken", "Not given (another item has them): {uris}", { uris: done.urisTaken.join(", ") }),
            "error",
          );
        // (with the entity as it was chosen: what the form shows in the mention's place)
        props.onDone(
          { ...done, entity: { ...done.entity, label: done.entity.label ?? found.label } },
          { mentions: mentions.filter(here).map((row) => row.id), suggestions: suggestions.filter(here) },
        );
      })
      .catch((error: unknown) => {
        console.error(error);
        toasts?.show(t("review_reconcile_refused", "Not reconciled: {reason}", { reason: reasonOf(error) }), "error");
      })
      .finally(() => setBusy(false));
  };
  return (
    <div class="flex min-w-0 flex-col gap-4" data-testid="reconcile-panel">
      <MentionWhere mention={props.mention} />
      <Show when={props.mention.uris.length > 0}>
        <p class="text-xs break-all text-slate-600" data-testid="reconcile-uris">
          {t("review_uris", "URIs to give: {uris}", { uris: props.mention.uris.join(", ") })}
        </p>
      </Show>
      <div class="flex flex-col gap-2">
        <span class="text-xs font-semibold text-slate-500 uppercase">
          {t("review_reconcile_with", "Reconcile with")}
        </span>
        <Show
          when={entity()}
          fallback={
            <PickOrCreate
              types={types()}
              placeholder={t("review_find_entity", "Find {type}, or + to make one", {
                type: modelName(props.mention.unreconciledType),
              })}
              initial={() => ({ label: props.mention.label })}
              onPick={(found) => setChoice({ type: found.type, id: found.id, label: found.label })}
            />
          }
        >
          {(found) => (
            <span class="flex flex-wrap items-center gap-2" data-testid="reconcile-chosen">
              <DefaultReferenceChip type={found().type} label={found().label ?? found().id} href={hrefOf(found())} />
              <Show when={known()?.id === found().id}>
                <span class="text-xs font-semibold text-slate-500 uppercase" data-testid="reconcile-known">
                  {t("review_has_uri", "has this URI already")}
                </span>
              </Show>
              <button type="button" class={buttonClass("quiet", "sm")} onClick={() => setChoice(null)}>
                {t("review_change", "Change")}
              </button>
            </span>
          )}
        </Show>
      </div>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
          <Similar
            mention={props.mention}
            stillThere={props.inForm ? props.stillThere : undefined}
            chosen={chosen}
            onToggle={(row, on) => setToggled({ ...toggled(), [row.id]: on })}
            onLoaded={(rows) => {
              offered = rows;
            }}
          />
          <SameUriSuggestions
            mention={props.mention}
            stillThere={props.inForm ? props.stillThere : undefined}
            chosen={confirmed}
            onToggle={(rows, on) =>
              setToggled({ ...toggled(), ...Object.fromEntries(rows.map((row) => [row.id, on])) })
            }
            onLoaded={(rows) => {
              suggested = rows;
            }}
          />
        </Loading>
      </Errored>
      <div class="flex justify-end gap-2">
        <Show when={props.onCancel}>
          <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel?.()}>
            {t("cancel", "Cancel")}
          </button>
        </Show>
        <button
          type="button"
          class={buttonClass("primary", "md")}
          disabled={!entity() || busy()}
          data-testid="reconcile-submit"
          onClick={reconcile}
        >
          <SpannerIcon />
          {t("review_reconcile", "Reconcile")}
        </button>
      </div>
    </div>
  );
}
