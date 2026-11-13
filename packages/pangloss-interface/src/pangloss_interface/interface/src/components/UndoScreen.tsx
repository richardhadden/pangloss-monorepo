import {
  ApiError,
  buttonClass,
  getModel,
  inputClass,
  ItemValue,
  Modal,
  references,
  useApi,
  useCurrentUser,
  useModels,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import { createMemo, createSignal, For, Show } from "solid-js";
import { getPermissions, proposeUndo, rejectUndo, undoMerge } from "../api";
import type { HeadRef, MergeRecord, UnmergeResult } from "../api";
import { daysSince, isEmpty } from "../compare";
import { absorbedOf, HeadChip, Heading, Notice, reasonOf, survivorOf, valuesClass } from "./parts";

/** What an undo puts back and what it leaves: said before it is made (`done` false) and after */
export function UndoReport(props: { result: UnmergeResult; done: boolean; heads: Record<string, HeadRef> }) {
  const definitions = useModels();
  const { t, modelName, fieldName } = useTranslations();
  const result = () => props.result;
  const draftModel = () => (result().draftType ? getModel(definitions, result().draftType!) : undefined);
  const draftRows = () =>
    (draftModel()?.fields ?? []).filter((field) => !isEmpty(result().draft?.[field.key]));
  const why = (reason: string) => {
    switch (reason) {
      case "gone":
        return t("merge_unmatched_gone", "no longer there");
      case "deleted":
        return t("merge_unmatched_deleted", "deleted since");
      case "changed":
        return t("merge_unmatched_changed", "changed since, and no longer refers to the survivor there");
      default:
        return reason;
    }
  };
  return (
    <div class="flex flex-col gap-3 text-sm" data-testid="merge-undo-report">
      <p data-testid="merge-undo-restored">
        {props.done
          ? t("merge_undo_restored", "{restored} references went back, in {heads} documents and entities.", {
              restored: result().restored.toLocaleString(),
              heads: result().heads.toLocaleString(),
            })
          : t("merge_undo_would_restore", "{restored} references go back, in {heads} documents and entities.", {
              restored: result().restored.toLocaleString(),
              heads: result().heads.toLocaleString(),
            })}
      </p>
      <Show when={result().unmatched.length > 0}>
        <Heading>
          {t("merge_undo_unmatched", "Cannot be put back ({count}): what held them was changed or removed since the merge", {
            count: result().unmatched.length.toLocaleString(),
          })}
        </Heading>
        <ul class="flex flex-col gap-2" data-testid="merge-undo-unmatched">
          <For each={result().unmatched}>
            {(move) => (
              <li class="flex flex-wrap items-center gap-2">
                <Show
                  when={move.head ? props.heads[move.head] : undefined}
                  fallback={<span>{modelName(move.sourceType ?? "")}</span>}
                >
                  {(head) => <HeadChip head={head()} />}
                </Show>
                <span class="text-slate-600">
                  {(move.field ?? "").replaceAll("_", " ")}: {why(move.reason)}
                </span>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <Show when={result().madeSince.length > 0}>
        <Heading>
          {t("merge_undo_made_since", "Written to the survivor since the merge ({count}): they stay on it", {
            count: result().madeSince.length.toLocaleString(),
          })}
        </Heading>
        <p class="text-xs text-slate-500">
          {t(
            "merge_undo_made_since_help",
            "Some may have been meant for the entity absorbed, and only a person can tell: look at each, and change it by hand.",
          )}
        </p>
        <div class="flex flex-wrap gap-2" data-testid="merge-undo-made-since">
          <For each={result().madeSince}>{(head) => <HeadChip head={head} />}</For>
        </div>
      </Show>
      <Show when={result().fieldsRestored}>
        <p data-testid="merge-undo-fields">
          {props.done
            ? t("merge_undo_fields_restored", "The survivor's own fields are as they were before the merge.")
            : t("merge_undo_fields_would_restore", "The survivor's own fields go back to what they were before the merge.")}
        </p>
      </Show>
      <Show when={!result().fieldsRestored && result().draft}>
        <Heading>{t("merge_undo_draft", "The survivor's own fields stay as they are")}</Heading>
        <p data-testid="merge-undo-draft">
          {t("merge_undo_draft_why", "{reason}. What they were before the merge, to put back by hand where it is wanted:", {
            reason: result().draftReason ?? t("merge_undo_draft_changed", "The survivor has changed since the merge"),
          })}
        </p>
        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt class="text-xs font-semibold text-slate-600 uppercase">{t("label", "Label")}</dt>
          <dd>{String(result().draft?.label ?? "")}</dd>
          <For each={draftRows()}>
            {(field) => (
              <>
                <dt class="text-xs font-semibold text-slate-600 uppercase">
                  {fieldName(draftModel()!.name, field.name)}
                </dt>
                <dd class={valuesClass}>
                  <ItemValue value={result().draft![field.key]} field={field} />
                </dd>
              </>
            )}
          </For>
        </dl>
      </Show>
    </div>
  );
}

/** The heads of what could not be put back, by id, where they are still there (for their chips) */
export async function headsOf(api: Parameters<typeof references>[0], result: UnmergeResult): Promise<Record<string, HeadRef>> {
  const ids = [...new Set(result.unmatched.map((move) => move.head).filter((id): id is string => !!id))];
  try {
    const found = await references(api, ids);
    return Object.fromEntries(found.map((head) => [head.id, { id: head.id, type: head.type, label: head.label }]));
  } catch {
    // (their chips are a help, not the point: without them each is said by its type)
    return {};
  }
}

/**
 * A merge that stands, and what undoing it would do: how old it is, what goes back, what cannot, and what was
 * written to the survivor since, which stays on it. Then the undo, asked again in a dialog; or, for someone who may
 * not undo alone, the proposal that it be undone, which someone else accepts (by undoing it) or rejects.
 *
 * It reads what the user may do and a dry run of the undo: draw it in a `Loading`.
 */
export function UndoScreen(props: {
  record: MergeRecord;
  onChanged: () => void;
  onUndone: (result: UnmergeResult, heads: Record<string, HeadRef>) => void;
}) {
  const api = useApi();
  const toasts = useToasts();
  const { t } = useTranslations();
  const record = () => props.record;
  const user = () => useCurrentUser()?.username;
  const plan = createMemo(() =>
    Promise.all([
      // (a dry run shows what would still go back whatever has been migrated; what refuses the undo is said)
      undoMerge(api, props.record.id, { dryRun: true, confirmMigrated: true }).then(
        async (result) => ({ result, heads: await headsOf(api, result), refused: undefined }),
        (error: unknown) => ({ result: undefined, heads: {}, refused: reasonOf(error) }),
      ),
      getPermissions(api),
    ]).then(([dry, permissions]) => ({ ...dry, permissions })),
  );
  const [confirming, setConfirming] = createSignal(false);
  const [rejecting, setRejecting] = createSignal(false);
  const [text, setText] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  // (the database was migrated since the merge: the undo is asked for again, saying so)
  const [migrated, setMigrated] = createSignal(false);

  const proposedByOther = () => !!record().undoProposedBy && record().undoProposedBy !== user();
  const proposedByMe = () => !!record().undoProposedBy && record().undoProposedBy === user();
  const mayUndo = () => plan().permissions.direct || proposedByOther();
  const days = () => daysSince(record().when, Date.now());

  const refused = (error: unknown) => {
    console.error(error);
    toasts?.show(t("merge_refused", "Not done: {reason}", { reason: reasonOf(error) }), "error");
  };
  const undo = async () => {
    setBusy(true);
    try {
      const result = await undoMerge(api, record().id, { confirmMigrated: migrated() });
      const heads = await headsOf(api, result);
      setConfirming(false);
      toasts?.show(t("merge_undone", "The merge is undone"), "success");
      props.onUndone(result, heads);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && /migrated/.test(error.detail) && !migrated()) {
        setMigrated(true);
      } else {
        setConfirming(false);
        refused(error);
      }
    } finally {
      setBusy(false);
    }
  };
  const send = async (request: () => Promise<unknown>, said: string) => {
    setBusy(true);
    try {
      await request();
      setRejecting(false);
      setText("");
      toasts?.show(said, "success");
      props.onChanged();
    } catch (error) {
      refused(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="flex flex-col gap-4" data-testid="merge-undo-screen">
      <p class="text-sm" data-testid="merge-age">
        {days() === 0
          ? t("merge_age_today", "This merge was made today.")
          : t("merge_age_days", "This merge was made {days} days ago.", { days: days().toLocaleString() })}{" "}
        {t("merge_moved", "It moved {moved} references, in {heads} documents and entities.", {
          moved: record().moved.toLocaleString(),
          heads: record().heads.toLocaleString(),
        })}
      </p>
      <Heading>{t("merge_undo_heading", "If it is undone")}</Heading>
      <Show
        when={plan().result}
        fallback={
          <Notice tone="refused" testid="merge-undo-impossible">
            {t("merge_undo_impossible", "It cannot be undone as things are: {reason}", { reason: plan().refused ?? "" })}
          </Notice>
        }
      >
        {(result) => (
          <>
            <UndoReport result={result()} done={false} heads={plan().heads} />
            <Show when={proposedByMe()}>
              <Notice tone="waiting" testid="merge-undo-own-proposal">
                {t("merge_undo_own_proposal", "You proposed that this merge be undone: someone else undoes it, or rejects that.")}
              </Notice>
            </Show>
            <Show when={!plan().permissions.direct && !record().undoProposedBy}>
              <label class="flex flex-col gap-1.5 text-xs font-semibold text-slate-600 uppercase">
                {t("merge_undo_note", "Why it should be undone (for whoever undoes it)")}
                <textarea
                  class={[inputClass, "h-20 font-normal normal-case"]}
                  data-testid="merge-undo-note-box"
                  value={text()}
                  onInput={(event) => setText(event.currentTarget.value)}
                />
              </label>
            </Show>
            <div class="flex flex-wrap justify-end gap-2">
              <Show when={record().undoProposedBy}>
                <button
                  type="button"
                  class={buttonClass("ordinary", "md")}
                  disabled={busy()}
                  data-testid="merge-undo-reject"
                  onClick={() => setRejecting(true)}
                >
                  {proposedByMe()
                    ? t("merge_undo_withdraw", "Withdraw the proposal")
                    : t("merge_undo_reject", "Leave it merged")}
                </button>
              </Show>
              <Show
                when={mayUndo()}
                fallback={
                  <Show when={!record().undoProposedBy}>
                    <button
                      type="button"
                      class={buttonClass("primary", "md")}
                      disabled={busy()}
                      data-testid="merge-undo-propose"
                      onClick={() =>
                        void send(
                          () => proposeUndo(api, record().id, text().trim()),
                          t("merge_undo_proposed", "Proposed: someone else undoes it"),
                        )
                      }
                    >
                      {t("merge_undo_propose", "Propose undoing it")}
                    </button>
                  </Show>
                }
              >
                <button
                  type="button"
                  class={buttonClass("danger", "md")}
                  disabled={busy()}
                  data-testid="merge-undo-start"
                  onClick={() => setConfirming(true)}
                >
                  {t("merge_undo", "Undo the merge")}
                </button>
              </Show>
            </div>
          </>
        )}
      </Show>

      <Show when={confirming()}>
        <Modal title={t("merge_undo_confirm_title", "Undo this merge?")} onClose={() => setConfirming(false)} size="lg">
          <div class="flex flex-col gap-4 p-4 text-sm" data-testid="merge-undo-dialog">
            <div class="flex flex-wrap items-center gap-2">
              <HeadChip head={absorbedOf(record())} />
              <span>{t("merge_undo_confirm_from", "will be an entity of its own again, apart from")}</span>
              <HeadChip head={survivorOf(record())} />
            </div>
            <Show when={plan().result}>
              {(result) => (
                <p>
                  {t(
                    "merge_undo_confirm_what",
                    "{restored} references go back to it. {since} written to the survivor since the merge stay there.",
                    {
                      restored: result().restored.toLocaleString(),
                      since: result().madeSince.length.toLocaleString(),
                    },
                  )}
                </p>
              )}
            </Show>
            <Show when={migrated()}>
              <Notice tone="waiting" testid="merge-undo-migrated">
                {t(
                  "merge_undo_migrated",
                  "The database has been migrated since this merge, so some of what it moved may be in fields that have changed. What can still be put back is listed on the page. Undo again to go on.",
                )}
              </Notice>
            </Show>
            <div class="flex justify-end gap-2">
              <button type="button" class={buttonClass("ordinary", "md")} onClick={() => setConfirming(false)} autofocus>
                {t("cancel", "Cancel")}
              </button>
              <button
                type="button"
                class={buttonClass("danger", "md")}
                disabled={busy()}
                data-testid="merge-undo-confirm"
                onClick={() => void undo()}
              >
                {busy() ? t("merge_undoing", "Undoing…") : t("merge_undo", "Undo the merge")}
              </button>
            </div>
          </div>
        </Modal>
      </Show>
      <Show when={rejecting()}>
        <Modal title={t("merge_undo_reject_title", "Leave it merged?")} onClose={() => setRejecting(false)}>
          <div class="flex flex-col gap-4 p-4 text-sm" data-testid="merge-undo-reject-dialog">
            <label class="flex flex-col gap-1.5 text-xs font-semibold text-slate-600 uppercase">
              {t("merge_undo_reject_reason", "Why (kept with the merge)")}
              <textarea
                class={[inputClass, "h-20 font-normal normal-case"]}
                data-testid="merge-undo-reject-reason"
                value={text()}
                onInput={(event) => setText(event.currentTarget.value)}
              />
            </label>
            <div class="flex justify-end gap-2">
              <button type="button" class={buttonClass("ordinary", "md")} onClick={() => setRejecting(false)}>
                {t("cancel", "Cancel")}
              </button>
              <button
                type="button"
                class={buttonClass("primary", "md")}
                disabled={busy()}
                data-testid="merge-undo-reject-confirm"
                onClick={() =>
                  void send(
                    () => rejectUndo(api, record().id, text().trim()),
                    t("merge_undo_rejected", "It stays merged"),
                  )
                }
              >
                {t("merge_undo_reject", "Leave it merged")}
              </button>
            </div>
          </div>
        </Modal>
      </Show>
    </div>
  );
}
