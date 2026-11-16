import { numberBadgeClass, buttonClass, Modal, useModels, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import type { Content, VersionRecord } from "../api";
import { changedRows } from "../align";
import type { AlignedRow, Step } from "../align";
import { CHANGE_TAG, when } from "../format";
import { deletedEntities } from "../deleted";
import { useFieldName } from "../names";
import { OpIcon, useOpWords } from "./OpIcon";
import { ChangedValue } from "./AlignedCell";

export interface RestoreDialogProps {
  type: string;
  version: number;
  /** The versions whose work a restore undoes, newest first */
  undone: VersionRecord[];
  /** What the item is now, to compare with what it would be */
  now: Now;
  /** What it would be (in the read form) */
  restored: Content;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * What the item is now, as the dialog knows it. One value, so that "not known yet" and "could not be read" are never
 * taken for "nothing will change":
 * - `reading`: the latest version is still being read (Restore waits for it);
 * - `known`: its content, which the changes are listed against;
 * - `unrecorded`: the graph is at a version the history did not record, so the changes since cannot all be listed;
 * - `unreadable`: the latest version could not be read, and why (Restore may go on: what it undoes is still listed).
 */
export type Now =
  | { state: "reading" }
  | { state: "known"; content: Content }
  | { state: "unrecorded"; version: number }
  | { state: "unreadable"; reason: string };

/** Where a row is, in words: `Statements › Activity "A coronation" › Places` */
export function useTrail() {
  const { modelName } = useTranslations();
  const fieldName = useFieldName();
  const step = (each: Step) =>
    each.kind === "field"
      ? fieldName(each.model, each.field.key)
      : each.label
        ? `${modelName(each.type)} “${each.label}”`
        : modelName(each.type);
  return (row: AlignedRow) => [...row.trail.map(step), fieldName(row.model, row.field.key)];
}

/** "Are you sure": what a restore would undo, the later versions and the changes field by field */
export function RestoreDialog(props: RestoreDialogProps) {
  const { t, language, modelName } = useTranslations();
  const definitions = useModels();
  const opWords = useOpWords();
  const trail = useTrail();
  const known = () => (props.now.state === "known" ? props.now.content : undefined);
  const unrecorded = () => (props.now.state === "unrecorded" ? props.now.version : undefined);
  const unreadable = () => (props.now.state === "unreadable" ? props.now.reason : undefined);
  const rows = () => {
    const now = known();
    return now ? changedRows(definitions, props.type, now, props.restored) : [];
  };
  return (
    <Modal
      title={t("history_restore_title", "Restore version {version}?", { version: String(props.version) })}
      onClose={props.onClose}
      size="lg"
    >
      <div class="flex flex-col gap-5 p-4 text-sm" data-testid="history-restore-dialog">
        <section>
          <h3 class="mb-2 text-xs font-semibold text-slate-700 uppercase">
            {t("history_restore_undone", "The work of these versions will be undone")}
          </h3>
          <ol class="flex flex-col divide-y-[0.5px] divide-slate-300 rounded-xs border-[0.5px] border-slate-400/70 bg-white">
            <For each={props.undone}>
              {(record) => (
                <li class="flex items-center gap-2 px-3 py-1.5 text-xs text-slate-600" data-testid="history-undone">
                  <span class={[numberBadgeClass, "bg-slate-600 text-white"]}>
                    v{record.version}
                  </span>
                  <OpIcon op={record.op} class="size-3" />
                  <span class="font-semibold uppercase">{opWords(record)}</span>
                  <span>
                    · {record.who} · {when(record.at, language())}
                  </span>
                </li>
              )}
            </For>
          </ol>
          <Show when={unrecorded()}>
            {(version) => (
              <p class="mt-2 text-xs text-amber-800">
                {t(
                  "history_restore_unrecorded",
                  "The latest version ({version}) wasn't recorded in the history, so its changes can't be listed here. They will be undone too.",
                  { version: String(version()) },
                )}
              </p>
            )}
          </Show>
        </section>
        <Show when={props.now.state !== "unrecorded"}>
          <section data-testid="history-restore-changes" data-state={props.now.state}>
            <h3 class="mb-2 text-xs font-semibold text-slate-700 uppercase">
              {t("history_restore_changes", "What will change")}
            </h3>
            <Show when={props.now.state === "reading"}>
              <p class="text-xs text-slate-500">{t("history_restore_reading", "Reading what the item is now…")}</p>
            </Show>
            <Show when={unreadable()}>
              {(reason) => (
                <p class="text-xs text-amber-800" data-testid="history-restore-unreadable">
                  {t(
                    "history_restore_unreadable",
                    "The latest version couldn't be read, so what will change can't be listed here: {reason}",
                    { reason: reason() },
                  )}
                </p>
              )}
            </Show>
            <Show when={known()}>
              <Show
                when={rows().length > 0}
                fallback={
                  <p class="text-xs text-slate-500">
                    {t("history_restore_no_changes", "Nothing: the content is the same as it is now.")}
                  </p>
                }
              >
                <ul class="flex flex-col divide-y-[0.5px] divide-slate-300 rounded-xs border-[0.5px] border-slate-400/70 bg-white">
                  <For each={rows()}>
                    {(row) => (
                      <li class="flex flex-col gap-1.5 px-3 py-2" data-testid="history-change-row" data-kind={row.cells[1]!.mark}>
                        <div class="flex flex-wrap items-center gap-1.5 text-[0.65rem] font-semibold text-slate-500 uppercase">
                          <span
                            class={[
                              "rounded-xs px-1.5 py-0.5 ring-[0.5px] ring-inset",
                              CHANGE_TAG[row.cells[1]!.mark as "added" | "removed" | "changed"],
                            ]}
                          >
                            {row.cells[1]!.mark === "added"
                              ? t("history_mark_added", "Put back")
                              : row.cells[1]!.mark === "removed"
                                ? t("history_mark_removed", "Taken out")
                                : t("history_mark_changed", "Changed")}
                          </span>
                          <span data-testid="history-trail">{trail(row).join(" › ")}</span>
                        </div>
                        <ChangedValue row={row} index={1} />
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </Show>
          </section>
        </Show>
        <Show when={deletedEntities(props.restored).length > 0}>
          <p class="text-xs text-amber-800" data-testid="history-restore-undeletes">
            {t("history_restore_undeletes", "Deleted since, and brought back by this restore: {names}.", {
              names: deletedEntities(props.restored)
                .map((entity) => `${modelName(entity.type)} “${entity.label}”`)
                .join(", "),
            })}
          </p>
        </Show>
        <p class="text-xs text-slate-500">
          {t(
            "history_restore_nothing_erased",
            "Nothing is erased: the history keeps every version, and this restore can be undone the same way.",
          )}
        </p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class={buttonClass("ordinary", "md")}
            onClick={() => props.onClose()}
            autofocus
          >
            {t("cancel", "Cancel")}
          </button>
          <button
            type="button"
            class={[buttonClass("primary", "md"), "gap-2"]}
            disabled={props.busy || props.now.state === "reading"}
            data-testid="history-restore-confirm"
            onClick={() => props.onConfirm()}
          >
            <OpIcon op="restore" class="size-4" />
            {props.busy ? t("history_restoring", "Restoring…") : t("history_restore", "Restore")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
