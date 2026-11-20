import { createEffect, createSignal, flush, onSettled, Show, untrack } from "solid-js";
import { useTranslations } from "../../context";
import { buttonClass, CloseIcon } from "../../primitives";
import type { NodeSearch } from "../../schema";
import { inputClass, smallButtonClass } from "../form/styles";
import { MenuSelect } from "./MenuSelect";
import { SearchFields } from "./SearchFields";
import type { SearchFieldsControl } from "./SearchFields";
import { deleteSearch, saveSearch, savedSearches } from "./saved";
import type { SavedSearch } from "./saved";

// (how long the panel takes to slide open: its `duration-300`)
const SLIDE_MS = 300;

// (the button that deletes a saved search, in the foot of the panel: as small as the buttons beside it)
const removeSmallClass = `${buttonClass("ordinary", "sm", true).replace("w-7", "w-6.5")} not-disabled:hover:text-red-800`;

/**
 * The search form of a list, which slides out from under the console bar (`open`) and pushes the list down: a row for
 * each field of `type` that can be searched, as the entry form has them, each with an operator (and a toggle to want
 * what does not hold), and the rows for what a document mentions or what refers to an entity (`SearchFields`, which
 * a dialog can hold too), with the saved searches, Clear and Close under them. It edits a copy of `initial`, and says
 * what it holds a moment after each change (`onChange`), or at once on Enter. See implementation_docs/search-form.md.
 */
export function SearchPanel(props: {
  type: string;
  initial?: NodeSearch;
  open: boolean;
  onChange: (form: NodeSearch) => void;
  onClose: () => void;
}) {
  const { t, modelName } = useTranslations();
  const type = untrack(() => props.type);
  // (the fields themselves, which hold the form: given once they are made, for Clear and the saved searches)
  let fields: SearchFieldsControl | undefined;
  const clear = () => fields?.replace({ type });
  // (what is in it can only be clipped while it slides: a menu or a list of matches opens over its edge. Unclipped
  // when the slide is over by the clock, not by `transitionend`: the panel's code is loaded when it is first asked for,
  // so it is often made already open, there is no slide, and no event came, which left every menu cut off)
  const [settled, setSettled] = createSignal(false);
  createEffect(
    () => props.open,
    (open) => {
      setSettled(false);
      if (!open) return;
      const timer = setTimeout(() => setSettled(true), SLIDE_MS);
      return () => clearTimeout(timer);
    },
  );
  // (from under the bar: up into the page's top padding, which is given back under it)
  return (
    <div class="-mt-8">
      <section
        aria-label={t("search_form_of", "Search {type} by fields", { type: modelName(props.type) })}
        aria-hidden={props.open ? undefined : "true"}
        inert={props.open ? undefined : true}
        data-open={props.open ? "" : undefined}
        class={[
          // (a little in from the ends of the console, so the two read as two things)
          "mx-3 grid transition-[grid-template-rows,opacity] duration-300",
          { "grid-rows-[1fr]": props.open, "opacity-100": props.open },
          { "grid-rows-[0fr]": !props.open, "opacity-0": !props.open },
        ]}
      >
        <div class={["min-h-0", { "overflow-hidden": !settled() || !props.open }]}>
          <div class="rounded-b-xs border-[0.5px] border-t-0 border-slate-400/70 bg-slate-200/40">
            <div class="px-6 pt-6 pb-5">
              <SearchFields
                type={props.type}
                initial={props.initial}
                onChange={(form) => props.onChange(form)}
                control={(control) => (fields = control)}
              />
            </div>
            <div class="flex items-center justify-end gap-2 border-t-[0.5px] border-slate-400/50 px-6 py-2">
              <SavedSearches
                type={props.type}
                current={() => fields?.current() ?? { type }}
                onLoad={(form) => fields?.replace(form)}
              />
              <button type="button" class={smallButtonClass} onClick={clear}>
                {t("search_clear", "Clear")}
              </button>
              <button type="button" class={smallButtonClass} onClick={() => props.onClose()}>
                {t("search_close", "Close")}
              </button>
            </div>
          </div>
        </div>
      </section>
      <div class="h-8" />
    </div>
  );
}

/**
 * The searches saved in this browser for the type (local storage): a menu to load one (which replaces what is in the
 * form) and a button to delete it; Save asks for a name, and saves what is in the form under it
 */
function SavedSearches(props: { type: string; current: () => NodeSearch; onLoad: (form: NodeSearch) => void }) {
  const { t } = useTranslations();
  const [all, setAll] = createSignal<SavedSearch[]>([]);
  const [chosen, setChosen] = createSignal("");
  const [naming, setNaming] = createSignal(false);
  const [name, setName] = createSignal("");
  let nameBox: HTMLInputElement | undefined;
  // (in the browser only: they are in its storage)
  onSettled(() => {
    setAll(savedSearches(props.type));
  });
  const save = () => {
    const given = name().trim();
    if (!given) return;
    setAll(saveSearch(props.type, given, props.current()));
    setChosen(given);
    setNaming(false);
  };
  return (
    <div class="mr-auto flex min-w-0 items-center gap-2">
      <Show when={all().length > 0}>
        <MenuSelect
          look="small"
          class="w-48"
          label={t("search_saved", "Saved searches")}
          placeholder={t("search_saved_placeholder", "Saved searches…")}
          value={chosen()}
          options={all().map((each) => ({ value: each.name, label: each.name }))}
          onChoose={(picked) => {
            const found = all().find((each) => each.name === picked);
            setChosen(picked);
            if (found) props.onLoad(structuredClone(found.form));
          }}
        />
        <Show when={chosen()}>
          <button
            type="button"
            class={removeSmallClass}
            aria-label={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            title={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            onClick={() => {
              setAll(deleteSearch(props.type, chosen()));
              setChosen("");
            }}
          >
            <CloseIcon size="3.5" />
          </button>
        </Show>
      </Show>
      <Show
        when={naming()}
        fallback={
          <button
            type="button"
            class={smallButtonClass}
            onClick={() => {
              setName(chosen());
              setNaming(true);
              // (the box drawn, then the cursor in it)
              flush();
              nameBox?.focus();
            }}
          >
            {t("search_save", "Save")}…
          </button>
        }
      >
        <input
          type="text"
          class={[inputClass, "h-6.5 w-48 py-0"]}
          aria-label={t("search_save_name", "Name of this search")}
          placeholder={t("search_save_name", "Name of this search")}
          value={name()}
          ref={nameBox}
          onInput={(event) => setName(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") save();
            if (event.key === "Escape") setNaming(false);
          }}
        />
        <button type="button" class={smallButtonClass} disabled={!name().trim()} onClick={save}>
          {t("search_save", "Save")}
        </button>
        <button type="button" class={smallButtonClass} onClick={() => setNaming(false)}>
          {t("cancel", "Cancel")}
        </button>
      </Show>
    </div>
  );
}

export default SearchPanel;
