import { action, createMemo, createOptimistic, createSignal, Errored, For, Loading, Show } from "solid-js";
import { ApiError, checkDeletable, deleteItem } from "../../api";
import { useApi, useComponent, useToasts, useTranslations } from "../../context";
import { smallButtonClass } from "./styles";

// (as `smallButtonClass`, in red)
const dangerButtonClass =
  "inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-xs border-[0.5px] border-red-700/60 bg-red-100 px-2 py-1 text-xs font-semibold text-red-900 uppercase select-none hover:bg-red-200 disabled:pointer-events-none disabled:opacity-40";

/**
 * Asks before deleting an item. It first asks the API whether the delete would go through: if it would, it asks
 * "are you sure", and Delete deletes; if not, it says why (an entity that something refers to, with what does, as
 * links), and there is only Close. (Should something come to refer to an entity in between, the API refuses the
 * delete with a 409, and that is said instead.) What refers to it is shown as chips, as references are everywhere.
 */
export function DeleteDialog(props: {
  type: string;
  id: string;
  label: string | undefined;
  onDeleted: () => void;
  onClose: () => void;
}) {
  const Modal = useComponent("Modal");
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const toasts = useToasts();
  const { t, modelName } = useTranslations();
  const check = createMemo(() => checkDeletable(api, props.type, props.id));
  const [deleting, setDeleting] = createOptimistic(false);
  const [refused, setRefused] = createSignal<string>();
  const named = () => ({ type: modelName(props.type), label: props.label ?? props.id });

  const send = action(function* () {
    setDeleting(true);
    yield deleteItem(api, props.type, props.id);
  });

  async function remove() {
    try {
      await send();
    } catch (error) {
      setRefused(error instanceof ApiError ? error.detail : String(error));
      return;
    }
    toasts?.show(t("toast_deleted", "{type} “{label}” deleted", named()));
    props.onDeleted();
  }

  return (
    <Modal title={t("delete_title", "Delete {type}", named())} onClose={props.onClose}>
      <div class="flex flex-col gap-4 p-4 text-sm">
        <Errored
          fallback={(error) => (
            <p role="alert" class="text-red-800">
              {error() instanceof ApiError ? (error() as ApiError).detail : String(error())}
            </p>
          )}
        >
          <Loading fallback={<p class="text-slate-600">{t("delete_checking", "Checking whether this can be deleted…")}</p>}>
            <Show
              when={check().deletable && !refused()}
              fallback={
                <div role="alert" class="flex flex-col gap-3">
                  <p>
                    <span class="font-semibold">
                      {t("delete_cannot", "“{label}” cannot be deleted.", named())}
                    </span>{" "}
                    {refused() ?? check().reason}
                  </p>
                  <Show when={!refused() && check().referencedBy.length > 0}>
                    <ul class="flex flex-wrap items-center gap-2">
                      <For each={check().referencedBy}>
                        {(reference) => (
                          <li>
                            <ReferenceChip
                              type={reference.type}
                              label={reference.label}
                              href={`/${encodeURIComponent(reference.type)}/${encodeURIComponent(reference.id)}`}
                            />
                          </li>
                        )}
                      </For>
                      <Show when={check().referenceCount > check().referencedBy.length}>
                        <li class="text-slate-600">
                          {t("delete_and_more", "and {count} more", {
                            count: check().referenceCount - check().referencedBy.length,
                          })}
                        </li>
                      </Show>
                    </ul>
                  </Show>
                  <div class="flex justify-end">
                    <button type="button" class={smallButtonClass} onClick={props.onClose} autofocus>
                      {t("close", "Close")}
                    </button>
                  </div>
                </div>
              }
            >
              <p>{t("delete_confirm", "Are you sure you want to delete the {type} “{label}”?", named())}</p>
              <div class="flex justify-end gap-2">
                <button type="button" class={smallButtonClass} onClick={props.onClose} autofocus>
                  {t("cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  class={dangerButtonClass}
                  disabled={deleting()}
                  onClick={() => void remove()}
                >
                  {t("delete", "Delete")}
                </button>
              </div>
            </Show>
          </Loading>
        </Errored>
      </div>
    </Modal>
  );
}

export default DeleteDialog;
