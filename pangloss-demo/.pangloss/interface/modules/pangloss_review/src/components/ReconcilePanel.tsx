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
import { getSimilarMentions, reconcileMention } from "../api";
import type { Mention, Reconciled, Ref, SimilarMention } from "../api";
import { hrefOf, reasonOf, SpannerIcon } from "./taskIcons";

/** A mention where it is: its chip, then the document it is in */
export function MentionWhere(props: { mention: Mention }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-2">
      <DefaultReferenceChip type={props.mention.unreconciledType} label={props.mention.label} />
      <span class="text-xs font-semibold text-slate-500 uppercase">{t("review_in", "in")}</span>
      <ReferenceChip
        type={props.mention.holder.type}
        label={props.mention.holder.label ?? props.mention.holder.id}
        href={hrefOf(props.mention.holder)}
      />
    </span>
  );
}

/** The other mentions that may be of the same thing, each with a box to reconcile it too */
function Similar(props: {
  mention: Mention;
  chosen: (row: SimilarMention) => boolean;
  onToggle: (row: SimilarMention, on: boolean) => void;
  onLoaded: (rows: SimilarMention[]) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const read = createMemo(() => getSimilarMentions(api, props.mention.id));
  // (what is offered is what can be chosen: the panel is told, in a plain name and not a signal, as this is drawn)
  const similar = () => {
    const rows = read();
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
        {t("review_similar_help", "These may be the same. Tick those to reconcile with it as well, in the background.")}
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

/**
 * Reconciling one mention: find the entity it is (or make one), tick the other mentions that are the same, and
 * Reconcile. The entity takes the mention's place in its document at once; the others are done in the background.
 * In a dialog (`ReconcileDialog`) and on the page of reconciliations.
 */
export function ReconcilePanel(props: { mention: Mention; onDone: (done: Reconciled) => void; onCancel?: () => void }) {
  const api = useApi();
  const definitions = useModels();
  const toasts = useToasts();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, modelName } = useTranslations();
  const [entity, setEntity] = createSignal<Ref>();
  // (the boxes as the reader left them: one not touched is ticked if its label is the same)
  const [toggled, setToggled] = createSignal<Record<string, boolean>>({});
  // (the rows of the table, as `Similar` read them: a plain name, set while it draws)
  let offered: SimilarMention[] = [];
  const [busy, setBusy] = createSignal(false);
  // (another mention: nothing chosen yet)
  createEffect(
    () => props.mention.id,
    () => {
      setEntity(undefined);
      setToggled({});
      offered = [];
    },
  );
  const chosen = (row: SimilarMention) => toggled()[row.id] ?? row.exact;
  const types = () => getModel(definitions, props.mention.unreconciledType)?.concreteTypes ?? [props.mention.unreconciledType];
  const reconcile = () => {
    const found = entity();
    if (!found) return;
    setBusy(true);
    reconcileMention(api, props.mention.id, found, offered.filter(chosen).map((row) => row.id))
      .then((done) => {
        toasts?.show(
          done.queued > 0
            ? t("review_reconciled_more", "Reconciled with {label}; {count} more in the background", {
                label: done.entity.label ?? "",
                count: String(done.queued),
              })
            : t("review_reconciled", "Reconciled with {label}", { label: done.entity.label ?? "" }),
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
              onPick={(found) => setEntity({ type: found.type, id: found.id, label: found.label })}
            />
          }
        >
          {(found) => (
            <span class="flex items-center gap-2" data-testid="reconcile-chosen">
              <DefaultReferenceChip type={found().type} label={found().label ?? found().id} href={hrefOf(found())} />
              <button type="button" class={buttonClass("quiet", "sm")} onClick={() => setEntity(undefined)}>
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
            chosen={chosen}
            onToggle={(row, on) => setToggled({ ...toggled(), [row.id]: on })}
            onLoaded={(rows) => {
              offered = rows;
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
