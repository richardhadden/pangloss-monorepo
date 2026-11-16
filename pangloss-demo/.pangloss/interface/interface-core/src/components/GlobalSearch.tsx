import {
  createEffect,
  createMemo,
  createSignal,
  For,
  isPending,
  Loading,
  onCleanup,
  onSettled,
  Show,
  untrack,
} from "solid-js";
import type { JSX } from "@solidjs/web";
import { searchEverything } from "../api";
import { useApi, useComponent, useModels, useSearchAddress, useTranslations } from "../context";
import type { EverythingSearch } from "../context";
import { kindRule, kindTint, Spinner } from "../primitives";
import { beginsLongerName, foldWord, getModel, offerTypes, pluralNameOf, takeTypeWord, typeCandidates, typeCompletion, typeFinder } from "../schema";
import type { TypeOffer, TypeSuggestion } from "../schema";

const DEBOUNCE_MS = 250;

interface TypeChip {
  model: string;
  word: string;
}

/**
 * The box of the homepage: finds documents and entities of any class by their label, and shows the most connected
 * under it. A finished word that names a type, in any language, becomes a chip that narrows the search to it;
 * Backspace against the chip turns it back into the word. While a word is being typed, the types it could be are offered
 * in a list under the box, and the rest of the first is shown in grey after it: Tab takes it, the arrows choose another. With no types on offer, the arrows go through the results, and Enter opens the one chosen (or the first). Nothing is asked until words or a type are typed; a type alone shows the most connected of it. (See
 * implementation_docs/homepage-and-pages.md.) As the search of a list, it is kept in the address (`?q=&type=`), and read from there on
 * the server: see `SearchAddress`.
 */
export function GlobalSearch(props: {
  limit?: number;
  /** Takes the place of following a result, by click or Enter. `command`: Cmd or Ctrl was held */
  onPick?: (item: { type: string; id: string; label: string }, command: boolean) => void;
  /** Something was typed in the box */
  onTyped?: () => void;
  /** Draws the results (under the box, if not given) */
  arrange?: (results: () => JSX.Element) => JSX.Element;
  /** Documents only, and only their types offered: no entities (what a citation is chosen from) */
  documentsOnly?: boolean;
}) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName, modelNames } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const address = useSearchAddress();
  const onPick = untrack(() => props.onPick);
  const arrange = untrack(() => props.arrange);
  const documentsOnly = untrack(() => props.documentsOnly === true);
  const [local, setLocal] = createSignal<EverythingSearch>({ q: "" });
  // (a type in the address that the search cannot be narrowed to is no type)
  const known = (type: string | undefined) =>
    type !== undefined && typeCandidates(definitions, () => [], documentsOnly).some((found) => found.model === type)
      ? type
      : undefined;
  const asked = (): EverythingSearch => (address ? { q: address.q(), type: known(address.type()) } : local());
  const keyOf = (search: EverythingSearch) => JSON.stringify([search.q, search.type]);
  // What the page opened with, which is in the box from the server's render on, and is not followed
  const initial = untrack(asked);
  // (the text the box starts with, as a plain name: written as `initial.q` in the markup it is taken for something
  // that can change, and is put in the box again whenever another attribute of the box is, as when the language
  // changes its label and placeholder. What was typed or deleted since was lost)
  const startingText = initial.q;
  const chipOf = (type: string | undefined): TypeChip | undefined =>
    type ? { model: type, word: untrack(() => modelName(type)) } : undefined;
  const [chip, setChip] = createSignal<TypeChip | undefined>(chipOf(initial.type));
  // (an answer that could not be had is shown as such, not thrown: the next search replaces it)
  const found = createMemo(() => {
    const { q, type } = asked();
    if (!q && !type) return undefined;
    return searchEverything(api, {
      q,
      types: type ? [type] : undefined,
      pageSize: props.limit ?? 25,
      documentsOnly,
    }).then(
      (page) => ({ page, failed: false }),
      () => ({ page: undefined, failed: true }),
    );
  });
  const pending = () => isPending(found);
  // (what is in the box, for the grey completion to be drawn after it)
  const [draft, setDraft] = createSignal(initial.q);
  // (the types on offer, and which is chosen with the arrows: -1, none)
  const [offer, setOffer] = createSignal<TypeOffer | undefined>();
  const [active, setActive] = createSignal(-1);
  // (the result chosen with the arrows, when no types are on offer: -1, none)
  const [activeResult, setActiveResult] = createSignal(-1);
  // (select all, with a chip: the chip is selected with the text)
  const [chipSelected, setChipSelected] = createSignal(false);
  let box: HTMLInputElement | undefined;
  let results: HTMLUListElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // (what is in force now: a signal's new value is not read back until the next flush)
  let current: TypeChip | undefined = chipOf(initial.type);
  // (a word turned back from a chip, which stays a word until the box is emptied)
  let declined: string | undefined;
  // (as `current`: a key can come before the flush)
  let offered: TypeOffer | undefined;
  let chosen = -1;
  let chosenResult = -1;
  let wholeSelected = false;
  // (the last search asked for: the address coming back with it is not a change to show)
  let lastAsked = keyOf(initial);
  onCleanup(() => clearTimeout(timer));
  onSettled(() => {
    box?.setSelectionRange(box.value.length, box.value.length);
    box?.focus({ preventScroll: true });
  });

  const showChip = (next: TypeChip | undefined) => {
    current = next;
    setChip(next);
  };
  const selectWhole = (selected: boolean) => {
    wholeSelected = selected;
    setChipSelected(selected);
  };
  const showOffer = (next: TypeOffer | undefined) => {
    offered = next;
    chosen = -1;
    setOffer(next);
    setActive(-1);
  };
  const choose = (index: number) => {
    chosen = index;
    setActive(index);
  };
  const chooseResult = (index: number) => {
    chosenResult = index;
    setActiveResult(index);
  };
  // (the list of results on show, if there is one: once it has gone, `results` is what it was)
  const resultRows = () => (results?.isConnected ? [...results.children] : []);
  const search = () => {
    clearTimeout(timer);
    const next: EverythingSearch = { q: box?.value.trim() ?? "", type: current?.model };
    if (keyOf(next) === lastAsked) return;
    lastAsked = keyOf(next);
    if (address) address.set(next);
    else setLocal(next);
  };
  // (the address changed otherwise, such as by going back: show it)
  createEffect(
    () => keyOf(asked()),
    (key) => {
      // (other results are coming: what was chosen is not among them)
      chooseResult(-1);
      if (key === lastAsked) return;
      lastAsked = key;
      const now = untrack(asked);
      if (box) box.value = now.q;
      setDraft(now.q);
      showChip(chipOf(now.type));
      showOffer(undefined);
      declined = undefined;
    },
  );
  const searchSoon = () => {
    clearTimeout(timer);
    timer = setTimeout(search, DEBOUNCE_MS);
  };
  const pick = (row: HTMLElement, command: boolean) => {
    const { itemType: type, itemId: id, itemLabel: label } = row.dataset;
    if (type && id) onPick?.({ type, id, label: label ?? id }, command);
  };
  // (before the router, which is told of a click at the document: only a click on the link itself, not on a chip's buttons)
  const clickRow = (event: MouseEvent) => {
    const row = (event.target as Element).closest("a")?.closest<HTMLElement>("li[data-item-id]");
    if (!row) return;
    event.preventDefault();
    event.stopPropagation();
    pick(row, event.metaKey || event.ctrlKey);
  };
  const typed = () => {
    if (!box) return;
    props.onTyped?.();
    chooseResult(-1);
    // (what was typed replaced everything that was selected, which was the chip too)
    if (wholeSelected) {
      showChip(undefined);
      selectWhole(false);
    }
    if (!box.value.trim()) declined = undefined;
    const candidates = typeCandidates(definitions, modelNames, documentsOnly);
    if (!current) {
      const taken = takeTypeWord(box.value, typeFinder(definitions, modelNames, documentsOnly), declined);
      if (taken && !beginsLongerName(candidates, taken.word)) {
        showChip({ model: taken.model, word: taken.word });
        box.value = taken.rest ? `${taken.rest} ` : "";
      }
    }
    setDraft(box.value);
    const atEnd = box.selectionEnd === box.value.length;
    showOffer(
      !current && atEnd ? offerTypes(box.value, candidates, declined) : undefined,
    );
    searchSoon();
  };
  const takeSuggestion = (suggestion: TypeSuggestion) => {
    if (!box || !offered) return;
    const rest = offered.rest;
    showChip({ model: suggestion.model, word: suggestion.name });
    box.value = rest ? `${rest} ` : "";
    setDraft(box.value);
    showOffer(undefined);
    // (in a moment, not with these writes: they would otherwise wait with it for the answer, and the chip with them)
    clearTimeout(timer);
    timer = setTimeout(search, 0);
  };
  const turnBackChip = () => {
    if (!box || !current) return;
    const word = current.word;
    const rest = box.value.trimStart();
    declined = foldWord(word);
    box.value = rest ? `${word} ${rest}` : word;
    box.setSelectionRange(word.length, word.length);
    showChip(undefined);
    setDraft(box.value);
    showOffer(undefined);
    searchSoon();
  };
  const clearWhole = () => {
    if (!box) return;
    box.value = "";
    showChip(undefined);
    selectWhole(false);
    declined = undefined;
    setDraft("");
    showOffer(undefined);
    clearTimeout(timer);
    timer = setTimeout(search, 0);
  };
  const chipModel = (name: string) => getModel(definitions, name);
  // (the types among the results, as they first come)
  const typesFound = () => [...new Set(found()?.page?.results.map((item) => item.type) ?? [])];
  const moreHref = (type: string) => {
    const path = `/${encodeURIComponent(type)}`;
    return asked().q ? `${path}?q=${encodeURIComponent(asked().q)}` : path;
  };
  // (the rest of the chosen type, or of the first if none is)
  const completion = () => {
    const shown = offer();
    const suggestion = shown?.suggestions[Math.max(active(), 0)];
    if (!shown || !suggestion) return "";
    const rest = typeCompletion(suggestion.name, shown.typed);
    // (the box already has the space after the word)
    return /\s$/.test(draft()) ? rest.trimStart() : rest;
  };

  const resultsView = () => (
      <Loading fallback={<Spinner class="size-5 text-slate-500" />}>
      <Show when={found()}>
        {(result) => (
      <Show
        when={result().page}
        fallback={<p class="text-sm text-red-800">{t("search_failed", "The search failed")}</p>}
      >
        {(page) => (
          <Show
            when={page().results.length > 0}
            fallback={<p class="text-sm text-slate-500">{t("nothing_found", "Nothing found")}</p>}
          >
            <div class="flex flex-col gap-4">
            <ul
              ref={(element) => {
                results = element;
                if (onPick) element.addEventListener("click", clickRow, true);
              }}
              class="flex flex-col items-start gap-1.5"
            >
              <For each={page().results} keyed={(item) => item.id}>
                {(item, index) => (
                  // (the margin: clear of the console, which stays at the top of the page)
                  <li
                    data-item-type={item().type}
                    data-item-id={item().id}
                    data-item-label={item().label}
                    aria-current={activeResult() === index() ? "true" : undefined}
                    class={["scroll-my-16 rounded-xs", { "ring-2 ring-blue-400": activeResult() === index() }]}
                  >
                    <ReferenceChip
                      type={item().type}
                      label={item().label}
                      href={`/${encodeURIComponent(item().type)}/${encodeURIComponent(item().id)}`}
                    />
                  </li>
                )}
              </For>
            </ul>
              <hr class="border-0 border-t-[0.5px] border-slate-400/70" />
              <div class="flex flex-wrap gap-1.5">
                <For each={typesFound()}>
                  {(type) => (
                    <a
                      href={moreHref(type)}
                      data-testid="search-more"
                      data-type-info={type}
                      class={[
                        "rounded-xs border-[0.5px] px-2 py-0.5 text-xs font-semibold uppercase select-none hover:brightness-95",
                        kindTint(chipModel(type)?.kind, chipModel(type)?.interfaceMeta?.colour),
                        kindRule(chipModel(type)?.kind, chipModel(type)?.interfaceMeta?.colour),
                      ]}
                    >
                      {t("more_type", "More {type}", { type: pluralNameOf(modelName, type) })}
                    </a>
                  )}
                </For>
              </div>
            </div>
          </Show>
        )}
      </Show>
        )}
      </Show>
      </Loading>
  );
  const below = () => (arrange ? arrange(resultsView) : resultsView());

  return (
    <div class="flex flex-col gap-4">
      <div class="relative flex h-16 items-center rounded-xs border-[0.5px] border-slate-400/70 bg-white shadow-sm focus-within:border-slate-600">
        <svg
          viewBox="0 0 24 24"
          class="ml-4 size-5 shrink-0 translate-y-px select-none fill-none stroke-slate-500 stroke-[1.5]"
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
              data-selected={chipSelected() ? "" : undefined}
              class={[
                "ml-3 shrink-0 rounded-xs border-[0.5px] px-2.5 py-0.5 text-sm font-semibold uppercase select-none",
                { "ring-2": chipSelected(), "ring-blue-400": chipSelected() },
                kindTint(chipModel(shown().model)?.kind, chipModel(shown().model)?.interfaceMeta?.colour),
                kindRule(chipModel(shown().model)?.kind, chipModel(shown().model)?.interfaceMeta?.colour),
              ]}
            >
              {modelName(shown().model)}
            </span>
          )}
        </Show>
        <div class="relative h-full min-w-0 flex-1">
          <Show when={completion()}>
            <div
              data-testid="search-type-completion"
              aria-hidden="true"
              class="pointer-events-none absolute inset-0 flex items-center overflow-hidden px-3 text-xl whitespace-pre select-none"
            >
              <span class="invisible">{draft()}</span>
              <span class="text-slate-400">{completion()}</span>
            </div>
          </Show>
        <input
          type="search"
          ref={box}
          value={startingText}
          aria-label={t("search_everything", "Quick search")}
          placeholder={t("search_everything", "Quick search")}
          aria-autocomplete="both"
          aria-controls="search-type-options"
          aria-activedescendant={active() >= 0 ? `search-type-option-${active()}` : undefined}
          onInput={typed}
          onBlur={() => {
            showOffer(undefined);
            selectWhole(false);
            chooseResult(-1);
          }}
          onMouseDown={() => selectWhole(false)}
          onKeyDown={(event) => {
            const command = event.metaKey || event.ctrlKey;
            if (command && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "a") {
              // (the browser selects the text; the chip is ours to select)
              if (current) selectWhole(true);
            } else if (wholeSelected && (event.key === "Backspace" || event.key === "Delete")) {
              event.preventDefault();
              clearWhole();
              return;
            } else if (wholeSelected && !command && !["Meta", "Control", "Shift", "Alt"].includes(event.key) && event.key.length > 1) {
              // (an arrow, Escape and the like: the selection is gone. A character is dealt with where it is typed)
              selectWhole(false);
            }
            if (offered) {
              const count = offered.suggestions.length;
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                // (round the list, through "none chosen")
                const step = event.key === "ArrowDown" ? 1 : -1;
                choose(((chosen + 1 + step + count + 1) % (count + 1)) - 1);
                return;
              }
              const picked = offered.suggestions[chosen];
              if (event.key === "Tab" && !event.shiftKey) {
                event.preventDefault();
                takeSuggestion(picked ?? offered.suggestions[0]!);
                return;
              }
              if (event.key === "Enter" && picked) {
                event.preventDefault();
                takeSuggestion(picked);
                return;
              }
              if (event.key === "Escape") {
                // (the browser would empty the box)
                event.preventDefault();
                showOffer(undefined);
                return;
              }
            }
            if ((event.key === "ArrowDown" || event.key === "ArrowUp") && !pending()) {
              const rows = resultRows();
              if (rows.length > 0) {
                event.preventDefault();
                // (round the list, through "none chosen", as the types are)
                const step = event.key === "ArrowDown" ? 1 : -1;
                const next = ((chosenResult + 1 + step + rows.length + 1) % (rows.length + 1)) - 1;
                chooseResult(next);
                rows[next]?.scrollIntoView({ block: "nearest" });
                return;
              }
            }
            const atStart = event.currentTarget.selectionStart === 0 && event.currentTarget.selectionEnd === 0;
            if (event.key === "Backspace" && atStart && current) {
              event.preventDefault();
              turnBackChip();
            } else if (event.key === "Enter") {
              // (what was chosen, or the first of what is on show, once it is of what is in the box)
              if (pending()) return;
              const row = resultRows()[Math.max(chosenResult, 0)] as HTMLElement | undefined;
              if (row && onPick) {
                event.preventDefault();
                pick(row, command);
              } else row?.querySelector("a")?.click();
            }
          }}
          class="relative h-full w-full bg-transparent px-3 text-sm outline-none not-placeholder-shown:text-xl placeholder:text-sm placeholder:font-semibold placeholder:text-slate-500 placeholder:uppercase"
        />
        </div>
        {/* (reading this waits for the first answer, so it has a boundary of its own, or the box would wait with it) */}
        <Loading fallback={null}>
          <Show when={pending()}>
            <span class="pr-4">
              <Spinner />
            </span>
          </Show>
        </Loading>
        <Show when={offer()}>
          {(shown) => (
            <ul
              id="search-type-options"
              role="listbox"
              aria-label={t("search_type_options", "Types")}
              class="absolute top-full left-0 z-20 mt-1 flex w-96 max-w-full flex-col rounded-xs border-[0.5px] border-slate-400/70 bg-white py-1 shadow-[0_1px_3px_rgb(0_0_0/0.08)]"
            >
              <For each={shown().suggestions} keyed={(suggestion) => suggestion.model}>
                {(suggestion, index) => (
                  <li
                    id={`search-type-option-${index()}`}
                    role="option"
                    aria-selected={active() === index() ? "true" : "false"}
                    // (not a click: the box must not lose the focus first)
                    onMouseDown={(event) => {
                      event.preventDefault();
                      takeSuggestion(suggestion());
                    }}
                    onMouseEnter={() => choose(index())}
                    class={["cursor-pointer px-2 py-1", { "bg-slate-200": active() === index() }]}
                  >
                    <span
                      data-type-info={suggestion().model}
                      class={[
                        "inline-block rounded-xs border-[0.5px] px-2 py-0.5 text-xs font-semibold uppercase select-none",
                        kindTint(chipModel(suggestion().model)?.kind, chipModel(suggestion().model)?.interfaceMeta?.colour),
                        kindRule(chipModel(suggestion().model)?.kind, chipModel(suggestion().model)?.interfaceMeta?.colour),
                      ]}
                    >
                      {suggestion().name}
                    </span>
                  </li>
                )}
              </For>
            </ul>
          )}
        </Show>
      </div>
      {below()}
    </div>
  );
}
