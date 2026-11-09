import { createSignal, For, onCleanup, onSettled, Show, untrack } from "solid-js";
import { searchEverything } from "../api";
import type { Page, Summary } from "../api";
import { useApi, useComponent, useModels, useTranslations } from "../context";
import { kindRule, kindTint, Spinner } from "../primitives";
import { foldWord, getModel, takeTypeWord, typeFinder } from "../schema";

const DEBOUNCE_MS = 250;

interface TypeChip {
  model: string;
  word: string;
}

/**
 * The box of the homepage: finds documents and entities of any class by their label, and shows the most connected
 * under it. A finished word that names a type, in any language, becomes a chip that narrows the search to it;
 * Backspace against the chip turns it back into the word. Nothing is asked until words or a type are typed; a type alone shows the most connected of it. (See
 * docs/homepage-and-pages.md.)
 */
export function GlobalSearch(props: { limit?: number }) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName, modelNames } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const [chip, setChip] = createSignal<TypeChip | undefined>();
  const [found, setFound] = createSignal<Page<Summary> | undefined>();
  const [failed, setFailed] = createSignal(false);
  const [pending, setPending] = createSignal(false);
  let box: HTMLInputElement | undefined;
  let results: HTMLUListElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // (what is in force now: a signal's new value is not read back until the next flush)
  let current: TypeChip | undefined;
  // (a word turned back from a chip, which stays a word until the box is emptied)
  let declined: string | undefined;
  // (an answer that is not to the last question is dropped)
  let asked = 0;
  onCleanup(() => clearTimeout(timer));
  onSettled(() => box?.focus({ preventScroll: true }));

  const showChip = (next: TypeChip | undefined) => {
    current = next;
    setChip(next);
  };
  const search = () => {
    clearTimeout(timer);
    const q = box?.value.trim() ?? "";
    const ticket = ++asked;
    setFailed(false);
    // (a type by itself lists the most connected of it; an empty box asks nothing)
    if (!q && !current) {
      setFound(undefined);
      setPending(false);
      return;
    }
    setPending(true);
    searchEverything(api, {
      q,
      types: current ? [current.model] : undefined,
      pageSize: untrack(() => props.limit) ?? 25,
    }).then(
      (page) => {
        if (ticket !== asked) return;
        setFound(page);
        setPending(false);
      },
      () => {
        if (ticket !== asked) return;
        setFound(undefined);
        setFailed(true);
        setPending(false);
      },
    );
  };
  const searchSoon = () => {
    clearTimeout(timer);
    timer = setTimeout(search, DEBOUNCE_MS);
  };
  const typed = () => {
    if (!box) return;
    if (!box.value.trim()) declined = undefined;
    if (!current) {
      const taken = takeTypeWord(box.value, typeFinder(definitions, modelNames), declined);
      if (taken) {
        showChip({ model: taken.model, word: taken.word });
        box.value = taken.rest ? `${taken.rest} ` : "";
      }
    }
    searchSoon();
  };
  const turnBackChip = () => {
    if (!box || !current) return;
    const word = current.word;
    const rest = box.value.trimStart();
    declined = foldWord(word);
    box.value = rest ? `${word} ${rest}` : word;
    box.setSelectionRange(word.length, word.length);
    showChip(undefined);
    searchSoon();
  };
  const chipModel = (name: string) => getModel(definitions, name);

  return (
    <div class="flex flex-col gap-4">
      <div class="flex h-16 items-center rounded-xs border-[0.5px] border-slate-400/70 bg-white focus-within:border-slate-600">
        <svg
          viewBox="0 0 24 24"
          class="ml-4 size-5 shrink-0 select-none fill-none stroke-slate-500 stroke-[1.5]"
          stroke-linecap="square"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-4-4" />
        </svg>
        <Show when={chip()}>
          {(shown) => (
            <span
              data-testid="search-type-chip"
              data-type-info={shown().model}
              class={[
                "ml-3 shrink-0 rounded-xs border-[0.5px] px-2.5 py-0.5 text-sm font-semibold uppercase select-none",
                kindTint(chipModel(shown().model)?.kind, chipModel(shown().model)?.interfaceMeta?.colour),
                kindRule(chipModel(shown().model)?.kind, chipModel(shown().model)?.interfaceMeta?.colour),
              ]}
            >
              {modelName(shown().model)}
            </span>
          )}
        </Show>
        <input
          type="search"
          ref={box}
          aria-label={t("search_everything", "Search everything")}
          placeholder={t("search_everything", "Search everything")}
          onInput={typed}
          onKeyDown={(event) => {
            const atStart = event.currentTarget.selectionStart === 0 && event.currentTarget.selectionEnd === 0;
            if (event.key === "Backspace" && atStart && current) {
              event.preventDefault();
              turnBackChip();
            } else if (event.key === "Enter") {
              // (the first of what is on show, once it is of what is in the box)
              if (!pending()) results?.querySelector("a")?.click();
            }
          }}
          class="h-full min-w-0 flex-1 bg-transparent px-3 text-xl outline-none placeholder:text-sm placeholder:font-semibold placeholder:text-slate-500 placeholder:uppercase"
        />
        <Show when={pending()}>
          <span class="pr-4">
            <Spinner />
          </span>
        </Show>
      </div>
      <Show when={failed()}>
        <p class="text-sm text-red-800">{t("search_failed", "The search failed")}</p>
      </Show>
      <Show when={found()}>
        {(page) => (
          <Show
            when={page().results.length > 0}
            fallback={<p class="text-sm text-slate-500">{t("nothing_found", "Nothing found")}</p>}
          >
            <ul ref={results} class="flex flex-col items-start gap-1.5">
              <For each={page().results} keyed={(item) => item.id}>
                {(item) => (
                  <li>
                    <ReferenceChip
                      type={item().type}
                      label={item().label}
                      href={`/${encodeURIComponent(item().type)}/${encodeURIComponent(item().id)}`}
                    />
                  </li>
                )}
              </For>
            </ul>
          </Show>
        )}
      </Show>
    </div>
  );
}
