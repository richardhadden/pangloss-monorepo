import { action, createOptimistic, createSignal, onSettled, Show, untrack } from "solid-js";
import { ApiError, createItem, updateItem } from "../../api";
import type { Summary } from "../../api";
import {
  createItemFormState,
  ItemFormProvider,
  useApi,
  useClipboard,
  useComponent,
  useModels,
  useToasts,
  useTranslations,
} from "../../context";
import { ConsoleButton } from "../../primitives";
import { cleanForSave, createFormHooks, getModel } from "../../schema";
import type { FormData } from "../../schema";
import type { ItemFormProps } from "../../types";
import { ItemFields } from "./ModelFields";
import { useSaveChecks } from "./Problems";

/**
 * The form to make an item or to change one. It edits a copy of `initial` (the edit view of an
 * item, or `{ type }` for a new one) in the fields of the model, and Save, on the right of the
 * console, sends it all: a create, or an update that says which version it is based on. It is
 * checked first, by the schemas of the models (`useSaveChecks`): what is wrong is not sent, but
 * shown at its fields, red, with a red toast; so is what the API refuses. An item someone else saved
 * meanwhile (a 412) is not overwritten, and the form offers to load the new version. A save that
 * worked is told in a toast (`useToasts`).
 */
export function ItemForm(props: ItemFormProps) {
  const Console = useComponent("Console");
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const state = createItemFormState(untrack(() => props.initial), {
    headId: untrack(() => (props.version === undefined ? undefined : String(props.initial.id))),
    binder: createFormHooks(definitions),
  });
  const model = () => getModel(definitions, props.type);
  // (while a save is being sent: it goes back to false when the save is over, whatever the answer)
  const [saving, setSaving] = createOptimistic(false);
  const [stale, setStale] = createSignal(false);
  let formElement: HTMLFormElement | undefined;
  const checks = useSaveChecks(state, () => formElement);
  const creating = () => props.version === undefined;
  const toasts = useToasts();
  // (tells the clipboard bar there is somewhere to paste, for as long as the page has this)
  const clipboard = useClipboard();
  onSettled(() => clipboard?.registerForm());
  const label = () => {
    const given = state.get(["label"]);
    return typeof given === "string" && given !== "" ? given : undefined;
  };

  // Sends the item: a create, or an update of the version it was loaded at. What comes of it is the caller's
  // (`save`), once it is over: a toast and `onSaved`, or what is wrong shown at the fields
  const send = action(function* (body: FormData) {
    setSaving(true);
    if (props.version === undefined) {
      // (the type of what is made is the address's: the body of a create has none of its own)
      delete body.type;
      return (yield createItem(api, props.type, body)) as Summary;
    }
    return (yield updateItem(api, props.type, String(props.initial.id), body, props.version)) as Summary;
  });

  async function save() {
    setStale(false);
    if (!checks.check()) return;
    let saved: Summary;
    try {
      saved = await send(cleanForSave(definitions, state.plain()));
    } catch (error) {
      if (error instanceof ApiError && error.status === 412) setStale(true);
      else checks.refused(error);
      return;
    }
    const named = { type: modelName(saved.type), label: saved.label };
    toasts?.show(
      props.version === undefined
        ? t("toast_created", "{type} “{label}” created", named)
        : t("toast_saved", "{type} “{label}” saved", named),
    );
    props.onSaved(saved);
  }

  return (
    <ItemFormProvider state={state}>
      <Console
        type={props.type}
        label={label() ?? (creating() ? t("new", "New") : undefined)}
        meta={props.meta}
        item={creating() ? undefined : { type: props.type, id: String(props.initial.id) }}
        page="edit"
      >
        <ConsoleButton label={t("cancel", "Cancel")} onClick={props.onCancel} tone="danger">
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-2"
            stroke-linecap="round"
            aria-hidden="true"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </ConsoleButton>
        <ConsoleButton
          label={t("save", "Save")}
          text
          disabled={saving()}
          tone={model()?.kind === "Entity" ? "entity" : "document"}
          onClick={() => void save()}
        >
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </ConsoleButton>
      </Console>
      <form
        ref={formElement}
        class="flex flex-col gap-6"
        aria-label={t("edit_form", "{type} form", { type: modelName(props.type) })}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <Show when={stale()}>
          <div
            role="alert"
            class="flex items-center gap-4 rounded-xs border-[0.5px] border-amber-700/60 bg-amber-100/70 p-3 text-sm"
          >
            <span>
              {t(
                "stale_version",
                "Someone has saved this item since you opened it. Nothing was overwritten: load the new version, and make your changes again.",
              )}
            </span>
            <button
              type="button"
              class="shrink-0 cursor-pointer rounded-xs border-[0.5px] border-slate-500 px-2 py-1 text-xs font-semibold uppercase hover:bg-slate-300/50"
              onClick={() => props.onReload?.()}
            >
              {t("reload", "Load the new version")}
            </button>
          </div>
        </Show>
        <Show when={model()}>
          <ItemFields model={model()!} path={() => []} creating={creating()} title />
        </Show>
      </form>
    </ItemFormProvider>
  );
}
