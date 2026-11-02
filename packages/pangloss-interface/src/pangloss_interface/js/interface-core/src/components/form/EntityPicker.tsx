import { createSignal, For, onCleanup, Show } from "solid-js";
import { autocomplete } from "../../api";
import type { Summary } from "../../api";
import { useApi, useTranslations } from "../../context";
import { Spinner } from "../../primitives";
import { inputClass } from "./styles";

// (how long after the last key the search is made)
const DEBOUNCE_MS = 250;

/**
 * A search box for an entity of one of `types`: what is typed is looked for in the labels (the
 * API's autocomplete), and the matches are listed to choose from.
 */
export function EntityPicker(props: { types: string[]; onPick: (entity: Summary) => void }) {
  const api = useApi();
  const { t, modelName } = useTranslations();
  const [text, setText] = createSignal("");
  const [results, setResults] = createSignal<Summary[]>([]);
  const [busy, setBusy] = createSignal(false);
  const [failed, setFailed] = createSignal(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ticket = 0;
  onCleanup(() => clearTimeout(timer));
  const look = (q: string) => {
    const mine = ++ticket;
    setBusy(true);
    setFailed(false);
    autocomplete(api, { q, types: props.types, pageSize: 8 })
      .then((page) => {
        if (mine === ticket) setResults(page.results);
      })
      .catch(() => {
        if (mine === ticket) setFailed(true);
      })
      .finally(() => {
        if (mine === ticket) setBusy(false);
      });
  };
  const typed = (value: string) => {
    setText(value);
    clearTimeout(timer);
    if (value.trim() === "") {
      ticket += 1;
      setResults([]);
      setBusy(false);
      return;
    }
    timer = setTimeout(() => look(value.trim()), DEBOUNCE_MS);
  };
  return (
    <div class="relative w-full max-w-md">
      <input
        type="text"
        class={inputClass}
        value={text()}
        placeholder={t("find_entity", "Find {type}…", {
          type: props.types.map((type) => modelName(type)).join(", "),
        })}
        aria-label={t("find_entity", "Find {type}…", {
          type: props.types.map((type) => modelName(type)).join(", "),
        })}
        onInput={(event) => typed(event.currentTarget.value)}
      />
      <Show when={busy()}>
        <span class="absolute top-1.5 right-2">
          <Spinner />
        </span>
      </Show>
      <Show when={failed()}>
        <p class="mt-1 text-xs text-red-800" role="alert">
          {t("search_failed", "The search failed")}
        </p>
      </Show>
      <Show when={text().trim() !== "" && !busy() && !failed() && results().length === 0}>
        <p class="mt-1 text-xs text-slate-500">{t("nothing_found", "Nothing found")}</p>
      </Show>
      <Show when={results().length > 0}>
        <ul
          class="absolute left-0 z-20 mt-1 w-full rounded-sm border-[0.5px] border-slate-400/70 bg-white shadow-lg"
          role="listbox"
        >
          <For each={results()}>
            {(result) => (
              <li role="option" aria-selected="false">
                <button
                  type="button"
                  class="flex w-full cursor-pointer items-center gap-2 px-2 py-1 text-left text-sm hover:bg-slate-400/30"
                  onClick={() => {
                    setResults([]);
                    setText("");
                    props.onPick(result);
                  }}
                >
                  <span class="shrink-0 text-xs font-semibold text-slate-500 uppercase select-none">
                    {modelName(result.type)}
                  </span>
                  <span class="truncate">{result.label}</span>
                </button>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
