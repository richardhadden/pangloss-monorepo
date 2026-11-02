import { createSignal, For, onSettled, Show, untrack } from "solid-js";
import { ApiError, createItem, problemsOf, updateItem } from "../../api";
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
import { cleanForSave, getModel } from "../../schema";
import type { ItemFormProps } from "../../types";
import { ItemFields } from "./ModelFields";

/**
 * The form to make an item or to change one. It edits a copy of `initial` (the edit view of an
 * item, or `{ type }` for a new one) in the fields of the model, and Save, on the right of the
 * console, sends it all: a create, or an update that says which version it is based on. A
 * rejected form shows what is wrong, in the place the API names; an item someone else saved
 * meanwhile (a 412) is not overwritten, and the form offers to load the new version. A save that
 * worked is told in a toast (`useToasts`).
 */
export function ItemForm(props: ItemFormProps) {
  const Console = useComponent("Console");
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const state = createItemFormState(
    untrack(() => props.initial),
    untrack(() => (props.version === undefined ? undefined : String(props.initial.id))),
  );
  const model = () => getModel(definitions, props.type);
  const [saving, setSaving] = createSignal(false);
  const [problems, setProblems] = createSignal<string[]>([]);
  const [stale, setStale] = createSignal(false);
  const creating = () => props.version === undefined;
  const toasts = useToasts();
  // (tells the clipboard bar there is somewhere to paste, for as long as the page has this)
  const clipboard = useClipboard();
  onSettled(() => clipboard?.registerForm());
  const label = () => {
    const given = state.get(["label"]);
    return typeof given === "string" && given !== "" ? given : undefined;
  };

  async function save() {
    setSaving(true);
    setProblems([]);
    setStale(false);
    try {
      const body = cleanForSave(definitions, state.plain());
      let saved: Summary;
      if (props.version === undefined) {
        // (the type of what is made is the address's: the body of a create has none of its own)
        delete body.type;
        saved = await createItem(api, props.type, body);
      } else {
        saved = await updateItem(api, props.type, String(props.initial.id), body, props.version);
      }
      const named = { type: modelName(saved.type), label: saved.label };
      toasts?.show(
        props.version === undefined
          ? t("toast_created", "{type} “{label}” created", named)
          : t("toast_saved", "{type} “{label}” saved", named),
      );
      props.onSaved(saved);
    } catch (error) {
      if (error instanceof ApiError && error.status === 412) setStale(true);
      else if (error instanceof ApiError) setProblems(problemsOf(error));
      else setProblems([String(error)]);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ItemFormProvider state={state}>
      <Console
        type={props.type}
        label={label() ?? (creating() ? t("new", "New") : undefined)}
        meta={props.meta}
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
            class="flex items-center gap-4 rounded-sm border-[0.5px] border-amber-700/60 bg-amber-100/70 p-3 text-sm"
          >
            <span>
              {t(
                "stale_version",
                "Someone has saved this item since you opened it. Nothing was overwritten: load the new version, and make your changes again.",
              )}
            </span>
            <button
              type="button"
              class="shrink-0 cursor-pointer rounded-sm border-[0.5px] border-slate-500 px-2 py-1 text-xs font-semibold uppercase hover:bg-slate-300/50"
              onClick={() => props.onReload?.()}
            >
              {t("reload", "Load the new version")}
            </button>
          </div>
        </Show>
        <Show when={problems().length > 0}>
          <ul
            role="alert"
            class="list-disc rounded-sm border-[0.5px] border-red-700/60 bg-red-100/70 p-3 pl-7 text-sm"
          >
            <For each={problems()}>{(problem) => <li>{problem}</li>}</For>
          </ul>
        </Show>
        <Show when={model()}>
          <ItemFields model={model()!} path={() => []} creating={creating()} title />
        </Show>
      </form>
    </ItemFormProvider>
  );
}
