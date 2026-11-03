import { createMemo, createSignal, createUniqueId, For, isPending, onCleanup, onSettled, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import { autocomplete } from "../../api";
import type { Summary } from "../../api";
import { useApi, useModels, useTranslations } from "../../context";
import { kindTint, Spinner } from "../../primitives";
import { getModel } from "../../schema";
import { matchingEntities, recentEntities, rememberEntity, stillThere } from "./recent";

// (how long after the last key the search is made)
const DEBOUNCE_MS = 250;
// (how many of those picked lately are offered, above what is found)
const RECENT_SHOWN = 5;
// (how many of the most used are offered before anything is typed)
const TOP_SHOWN = 10;

// What the API found for the words `q` (none for none); `failed` if it could not be asked
interface Found {
  q: string;
  results: Summary[];
  failed: boolean;
}

/**
 * A search box for an entity of one of `types`: what is typed is looked for in the labels (the
 * API's autocomplete), and the matches are listed under it, as wide as it, to choose from with
 * the mouse or with the arrow keys and Enter (Escape closes the list). Above the matches are the
 * entities of the types picked lately (in this browser) that match too, marked with a clock (each only
 * once the API has said it is still there: the browser outlives a database made again); before
 * anything is typed those are offered, and then the ones most used (asked for as soon as the box is
 * drawn). `children` are joined on to the right end of the box (the button to make a new one).
 */
export function EntityPicker(props: {
  types: string[];
  onPick: (entity: Summary) => void;
  children?: JSX.Element;
  /** What the box says before anything is typed (by default, the types it finds) */
  placeholder?: string;
}) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const listId = createUniqueId();
  const [text, setText] = createSignal("");
  // What is searched for: the words typed, a moment after the last key (or at once when there are none). Each time
  // is a search, the same words again too (as after one that failed)
  const [asked, setAsked] = createSignal("", { equals: false });
  // What was found for them. While the next are being asked for, the last answer stays (and `busy()` is true); one
  // superseded by newer words is never shown
  const found = createMemo((): Found | Promise<Found> => {
    const q = asked();
    if (q === "") return { q, results: [], failed: false };
    return autocomplete(api, { q, types: props.types, pageSize: 8 }).then(
      (page) => ({ q, results: page.results, failed: false }),
      () => ({ q, results: [], failed: true }),
    );
  });
  const busy = () => isPending(found);
  const failed = () => found().failed;
  // (the most used, offered before anything is typed; and those picked lately, of any type)
  const [top, setTop] = createSignal<Summary[]>([]);
  const [recent, setRecent] = createSignal<Summary[]>([]);
  // (the ids of those picked lately that are still in the database)
  const [alive, setAlive] = createSignal<Set<string>>(new Set());
  const [open, setOpen] = createSignal(false);
  const [active, setActive] = createSignal(0);
  let list: HTMLUListElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  // (those picked lately, and whether each of this field's types is still there; another field may have picked one since)
  const loadRecent = () => {
    const all = recentEntities();
    setRecent(all);
    for (const entity of matchingEntities(definitions, all, props.types, "")) {
      void stillThere(api, entity).then((there) => {
        if (there) setAlive((ids) => new Set(ids).add(entity.id));
        else setRecent((now) => now.filter((other) => other.id !== entity.id));
      });
    }
  };
  // (in the browser only: what was picked lately is in its storage)
  onSettled(() => {
    loadRecent();
    autocomplete(api, { types: props.types, pageSize: TOP_SHOWN })
      .then((page) => setTop(page.results))
      .catch(() => {
        // (nothing is offered until something is typed)
      });
  });
  const typed = (value: string) => {
    setText(value);
    setActive(0);
    setOpen(true);
    clearTimeout(timer);
    // (no words: what is offered before anything is typed is shown again, at once)
    if (value.trim() === "") setAsked("");
    else timer = setTimeout(() => setAsked(value.trim()), DEBOUNCE_MS);
  };
  const pick = (result: Summary) => {
    rememberEntity(result);
    clearTimeout(timer);
    setAsked("");
    setText("");
    setOpen(false);
    props.onPick(result);
  };
  const blank = () => text().trim() === "";
  const recentShown = () =>
    matchingEntities(
      definitions,
      recent().filter((entity) => alive().has(entity.id)),
      props.types,
      text(),
    ).slice(0, RECENT_SHOWN);
  // (what is listed: those picked lately first, then what was found, or the most used, without them)
  const options = () => {
    const first = recentShown();
    const ids = new Set(first.map((entity) => entity.id));
    // (the answer for what is typed: none while it is being asked for the first time)
    const answer = found();
    const rest = blank() ? top() : answer.q === text().trim() ? answer.results : [];
    return [...first, ...rest.filter((entity) => !ids.has(entity.id))];
  };
  const isRecent = (index: number) => index < recentShown().length;
  const showing = () => open() && !blank();
  const listed = () => open() && options().length > 0;
  // ("Nothing found" only once the search for what is typed has answered)
  const empty = () =>
    showing() && !busy() && !failed() && options().length === 0 && found().q === text().trim();
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
    props.placeholder ??
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
          onInput={(event) => typed(event.currentTarget.value)}
          onKeyDown={onKeyDown}
          onFocus={() => {
            loadRecent();
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
