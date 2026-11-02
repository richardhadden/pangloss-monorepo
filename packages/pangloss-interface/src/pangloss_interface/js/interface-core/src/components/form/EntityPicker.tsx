import { createSignal, createUniqueId, For, onCleanup, onSettled, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import { autocomplete } from "../../api";
import type { Summary } from "../../api";
import { useApi, useModels, useTranslations } from "../../context";
import { kindTint, Spinner } from "../../primitives";
import { getModel } from "../../schema";
import { matchingEntities, recentEntities, rememberEntity } from "./recent";

// (how long after the last key the search is made)
const DEBOUNCE_MS = 250;
// (how many of those picked lately are offered, above what is found)
const RECENT_SHOWN = 5;
// (how many of the most used are offered before anything is typed)
const TOP_SHOWN = 10;

/**
 * A search box for an entity of one of `types`: what is typed is looked for in the labels (the
 * API's autocomplete), and the matches are listed under it, as wide as it, to choose from with
 * the mouse or with the arrow keys and Enter (Escape closes the list). Above the matches are the
 * entities of the types picked lately (in this browser) that match too, marked with a clock; before
 * anything is typed those are offered, and then the ones most used (asked for as soon as the box is
 * drawn). `children` are joined on to the right end of the box (the button to make a new one).
 */
export function EntityPicker(props: {
  types: string[];
  onPick: (entity: Summary) => void;
  children?: JSX.Element;
}) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const listId = createUniqueId();
  const [text, setText] = createSignal("");
  const [results, setResults] = createSignal<Summary[]>([]);
  // (the most used, offered before anything is typed; and those picked lately, of any type)
  const [top, setTop] = createSignal<Summary[]>([]);
  const [recent, setRecent] = createSignal<Summary[]>([]);
  const [busy, setBusy] = createSignal(false);
  const [failed, setFailed] = createSignal(false);
  const [open, setOpen] = createSignal(false);
  const [active, setActive] = createSignal(0);
  // (what the results are for: "Nothing found" only once the search for what is typed has answered)
  const [searched, setSearched] = createSignal("");
  let list: HTMLUListElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ticket = 0;
  onCleanup(() => clearTimeout(timer));
  // (in the browser only: what was picked lately is in its storage)
  onSettled(() => {
    setRecent(recentEntities());
    autocomplete(api, { types: props.types, pageSize: TOP_SHOWN })
      .then((page) => setTop(page.results))
      .catch(() => {
        // (nothing is offered until something is typed)
      });
  });
  const look = (q: string) => {
    const mine = ++ticket;
    setBusy(true);
    setFailed(false);
    autocomplete(api, { q, types: props.types, pageSize: 8 })
      .then((page) => {
        if (mine !== ticket) return;
        setResults(page.results);
        setSearched(q);
        setActive(0);
        setOpen(true);
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
      // (what is offered before anything is typed is shown again)
      ticket += 1;
      setResults([]);
      setBusy(false);
      return;
    }
    timer = setTimeout(() => look(value.trim()), DEBOUNCE_MS);
  };
  const pick = (result: Summary) => {
    rememberEntity(result);
    setResults([]);
    setText("");
    setOpen(false);
    props.onPick(result);
  };
  const blank = () => text().trim() === "";
  const recentShown = () =>
    matchingEntities(definitions, recent(), props.types, text()).slice(0, RECENT_SHOWN);
  // (what is listed: those picked lately first, then what was found, or the most used, without them)
  const options = () => {
    const first = recentShown();
    const ids = new Set(first.map((entity) => entity.id));
    const rest = blank() ? top() : searched() === text().trim() ? results() : [];
    return [...first, ...rest.filter((entity) => !ids.has(entity.id))];
  };
  const isRecent = (index: number) => index < recentShown().length;
  const showing = () => open() && !blank();
  const listed = () => open() && options().length > 0;
  const empty = () =>
    showing() && !busy() && !failed() && options().length === 0 && searched() === text().trim();
  const panel = () => (showing() && failed()) || listed() || empty();
  const optionId = (index: number) => `${listId}-${index}`;
  const move = (by: number) => {
    const count = options().length;
    if (count === 0) return;
    // (a closed list opens again where it was)
    if (!listed()) return setOpen(true);
    const next = (active() + by + count) % count;
    setActive(next);
    list?.querySelector(`#${CSS.escape(optionId(next))}`)?.scrollIntoView({ block: "nearest" });
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      move(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Enter") {
      // (never the form's submit: Enter in the search chooses, or does nothing)
      event.preventDefault();
      const chosen = options()[active()];
      if (listed() && chosen) pick(chosen);
    } else if (event.key === "Escape" && showing()) {
      // (only the list: a dialog the form is in stays open)
      event.stopPropagation();
      setOpen(false);
    }
  };
  const tintOf = (type: string) => {
    const model = getModel(definitions, type);
    return kindTint(model?.kind, model?.interfaceMeta?.colour);
  };
  const placeholder = () =>
    t("find_entity", "Find {type}…", {
      type: props.types.map((type) => modelName(type)).join(", "),
    });
  return (
    <div class="relative w-full min-w-0">
      <div
        class={[
          "flex w-full items-stretch border-[0.5px] border-slate-400/70 bg-white/80 focus-within:border-slate-600",
          { "rounded-sm": !panel() },
          { "rounded-t-sm": panel() },
        ]}
      >
        <span class="flex shrink-0 items-center pl-2.5 text-slate-400 select-none" aria-hidden="true">
          <Show when={busy()} fallback={<SearchIcon />}>
            <Spinner />
          </Show>
        </span>
        <input
          type="text"
          role="combobox"
          class="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm focus:outline-none"
          value={text()}
          placeholder={placeholder()}
          aria-label={placeholder()}
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={listed() ? "true" : "false"}
          aria-activedescendant={listed() ? optionId(active()) : undefined}
          onInput={(event) => {
            setActive(0);
            typed(event.currentTarget.value);
          }}
          onKeyDown={onKeyDown}
          onFocus={() => {
            // (another field may have picked one since)
            setRecent(recentEntities());
            setOpen(true);
          }}
          onBlur={() => setOpen(false)}
        />
        {props.children}
      </div>
      <Show when={panel()}>
        <div class="absolute inset-x-0 top-full z-20 -mt-px overflow-hidden rounded-b-sm border-[0.5px] border-slate-600 bg-white shadow-lg">
          <Show when={failed()}>
            <p class="px-3 py-2 text-sm text-red-800" role="alert">
              {t("search_failed", "The search failed")}
            </p>
          </Show>
          <Show when={empty()}>
            <p class="px-3 py-2 text-sm text-slate-500 italic">{t("nothing_found", "Nothing found")}</p>
          </Show>
          <ul id={listId} ref={list} class="max-h-72 overflow-y-auto" role="listbox">
            <Show when={!failed()}>
              <For each={options()}>
                {(result, index) => (
                  <li
                    id={optionId(index())}
                    role="option"
                    aria-selected={active() === index() ? "true" : "false"}
                    class={[
                      "flex cursor-pointer items-center gap-3 border-t-[0.5px] border-slate-400/30 px-3 py-1.5 text-sm first:border-t-0",
                      { "bg-slate-400/25": active() === index() },
                    ]}
                    // (the box keeps the focus, so the list is not closed before the click)
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseMove={() => setActive(index())}
                    onClick={() => pick(result)}
                  >
                    <span
                      class={[
                        "shrink-0 rounded-sm px-1.5 py-0.5 text-xs font-semibold uppercase select-none",
                        tintOf(result.type),
                      ]}
                    >
                      {modelName(result.type)}
                    </span>
                    <span class="min-w-0 flex-1 truncate">{result.label}</span>
                    <Show when={isRecent(index())}>
                      <span class="shrink-0 text-slate-400" title={t("picked_lately", "Used recently")}>
                        <ClockIcon />
                      </span>
                    </Show>
                  </li>
                )}
              </For>
            </Show>
          </ul>
        </div>
      </Show>
    </div>
  );
}

function ClockIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      class="size-3.5 select-none fill-none stroke-current stroke-2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      class="size-3.5 select-none fill-none stroke-current stroke-[2.5]"
      stroke-linecap="round"
    >
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </svg>
  );
}
