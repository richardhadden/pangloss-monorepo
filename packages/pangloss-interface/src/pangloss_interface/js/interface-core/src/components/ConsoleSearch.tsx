import {
  createEffect,
  createSignal,
  Errored,
  Loading,
  onCleanup,
  onSettled,
  Show,
  untrack,
} from "solid-js";
import { useTranslations } from "../context";
import { ConsoleButton, Spinner } from "../primitives";
import type { ConsoleSearchProps } from "../types";
import { dialogIsOpen, startsTyping } from "./keys";

// (how long after the last key the search is made)
const DEBOUNCE_MS = 250;

/**
 * The text search of a list, for the middle of the console: it fills the height of the bar,
 * with a toggle for Deep Search at its right (and the search form's beyond it). It does not search: it says what to search for
 * (`onSearch`), and shows what it is given (`query`, `deep`), so the page can keep them in
 * the address. An ordinary search is made a moment after the last key, or at once on Enter. A
 * Deep Search is slow, so turning it on makes none: it is made on Enter, or by the run
 * button that appears with it. With `onListKey`, the arrows choose an item of the list, and Enter, once the list on show
 * is of what is in the box, opens it. With `count`, it says how many were found: in red if none.
 *
 * The box's value is never bound to `query`: what is typed is the box's own, and a search the
 * page is answering (the address changed, and the list is being asked again) cannot hold it up or
 * put back what it was when that search was made. Only a `query` that is not the last one asked
 * for (the address changed otherwise, as by going back) is written into it.
 */
export function ConsoleSearch(props: ConsoleSearchProps) {
  const { t } = useTranslations();
  // What the page was opened with (in the box from the server's render on, not followed)
  const initial = untrack(() => props.query ?? "");
  // What is typed, which is ahead of `props.query` until the search is made (for the run button)
  const [draft, setDraft] = createSignal(initial);
  // (the last search asked for: `props.query` coming back as it is not a change to show)
  let asked = initial;
  let box: HTMLInputElement | undefined;
  // Whether Deep Search is on: ahead of `props.deep` until a deep search is made (and `props.deep` again when it changes)
  const [deepOn, setDeepOn] = createSignal(() => props.deep ?? false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  // (the address changed otherwise, such as by going back: show it)
  createEffect(
    () => props.query ?? "",
    (query) => {
      if (query === asked) return;
      asked = query;
      setDraft(query);
      if (box) box.value = query;
    },
  );
  const search = (deep: boolean) => {
    clearTimeout(timer);
    // (the box, not `draft`: a write is not read back until the next flush)
    asked = box?.value ?? untrack(draft);
    props.onSearch?.({ query: asked, deep });
  };
  const typed = (text: string) => {
    setDraft(text);
    clearTimeout(timer);
    // (not a deep one: that waits to be asked for)
    if (!deepOn() || props.structured) timer = setTimeout(() => search(false), DEBOUNCE_MS);
  };
  const toggleDeep = () => {
    const on = !deepOn();
    setDeepOn(on);
    // (turning it off goes back to the ordinary search of what is typed; turning it on makes none)
    if (!on) search(false);
  };
  // A character typed on the page starts or goes on with the search. Only the focus is moved: the browser then writes
  // the key into the box itself, accents and all
  onSettled(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!box || !startsTyping(event) || dialogIsOpen()) return;
      box.setSelectionRange(box.value.length, box.value.length);
      box.focus({ preventScroll: true });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  // Run only changes anything if it is not what is on show already
  const upToDate = () =>
    draft() === (props.query ?? "") && (props.deep ?? false) === deepOn();
  // (Enter opens an item only of the list that is what the box asks for; the box, not `draft`, as in `search`)
  const listIsOfTheBox = () =>
    !props.pending &&
    box?.value === (props.query ?? "") &&
    (props.structured || (props.deep ?? false) === deepOn());
  // (a count that is not all there is says so: the search has to be narrowed)
  const foundTitle = () => {
    if (props.truncated)
      return t("found_more", "Found, and more: narrow the search");
    return t("found", "Found");
  };

  return (
    <div class="flex h-full w-full max-w-xl items-center border-x-[0.5px] border-slate-400/70 bg-white/30 focus-within:bg-white/50">
      <svg
        viewBox="0 0 24 24"
        class="ml-3 size-4 shrink-0 select-none fill-none stroke-slate-500 stroke-2"
        stroke-linecap="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-4-4" />
      </svg>
      <input
        type="search"
        aria-label={t("search", "Search")}
        placeholder={t("search", "Search")}
        ref={box}
        value={initial}
        onInput={(event) => typed(event.currentTarget.value)}
        onFocus={() => props.onFocusChange?.(true)}
        onBlur={() => props.onFocusChange?.(false)}
        onKeyDown={(event) => {
          const plain = !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
          if (props.onListKey && plain && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
            event.preventDefault();
            props.onListKey(event.key === "ArrowDown" ? "next" : "previous");
          } else if (event.key === "Enter") {
            if (props.onListKey && listIsOfTheBox()) props.onListKey("open");
            else search(deepOn() && !props.structured);
          }
        }}
        class="h-full min-w-0 flex-1 bg-transparent px-3 text-sm font-normal normal-case outline-none placeholder:text-xs placeholder:font-semibold placeholder:text-slate-500 placeholder:uppercase"
      />
      {/* (`count` may be a read that waits for the result, so it has a boundary of its own here,
          or the whole page would wait with it. A spinner stands in for it while it loads) */}
      <span class="flex items-center pr-3 pl-2 text-xs font-semibold text-slate-500 tabular-nums select-none">
        <Show when={!props.pending} fallback={<Spinner />}>
          <Errored fallback="–">
            <Loading fallback={<Spinner />}>
              <span
                title={foundTitle()}
                class={{ "text-red-800": props.count === 0 }}
              >
                {props.count}
                <Show when={props.truncated}>+</Show>
              </span>
            </Loading>
          </Errored>
        </Show>
      </span>
      <Show when={deepOn() && !props.structured}>
        <ConsoleButton
          label={t("deep_search_run", "Run deep search (Enter)")}
          disabled={upToDate()}
          onClick={() => search(true)}
        >
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-current"
            aria-hidden="true"
          >
            <path d="M8 5.5v13l11-6.5z" />
          </svg>
        </ConsoleButton>
      </Show>
      <ConsoleButton
        label={t("deep_search", "Deep search")}
        pressed={deepOn() && !props.structured}
        disabled={props.structured}
        onClick={toggleDeep}
      >
        <svg
          viewBox="0 0 24 24"
          class="size-5 select-none fill-none stroke-current stroke-2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5" />
        </svg>
      </ConsoleButton>
      <Show when={props.onToggleForm}>
        <ConsoleButton
          label={
            props.structured
              ? t("search_form_in_use", "Search by fields (in use)")
              : t("search_form", "Search by fields")
          }
          pressed={!!props.formOpen}
          onClick={() => props.onToggleForm?.()}
        >
          {/* (a form: names, and the boxes beside them; a dot while it is in use) */}
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M4 7.5h3M4 14.5h3" />
            <rect x="10" y="5" width="10" height="5" rx="1" />
            <rect x="10" y="12" width="10" height="5" rx="1" />
            <path d="M4 20.5h16" />
            <Show when={props.structured}>
              <circle cx="20.5" cy="3.5" r="2.5" class="fill-current stroke-none" data-in-use="" />
            </Show>
          </svg>
        </ConsoleButton>
      </Show>
    </div>
  );
}
