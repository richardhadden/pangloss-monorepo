import { createEffect, createSignal, Errored, Loading, onCleanup, Show } from "solid-js";
import { ConsoleButton, Spinner } from "../primitives";
import type { ConsoleSearchProps } from "../types";

// (how long after the last key the search is made)
const DEBOUNCE_MS = 250;

/**
 * The text search of a list, for the middle of the console: it fills the height of the bar,
 * with a toggle for Deep Search at its right. It does not search: it says what to search for
 * (`onSearch`), and shows what it is given (`query`, `deep`), so the page can keep them in
 * the address. An ordinary search is made a moment after the last key, or at once on Enter. A
 * Deep Search is slow, so turning it on makes none: it is made on Enter, or by the run
 * button that appears with it. With `count`, it says how many were found: in red if none.
 */
export function ConsoleSearch(props: ConsoleSearchProps) {
  // What is typed, which is ahead of `props.query` until the search is made
  const [draft, setDraft] = createSignal(props.query ?? "");
  // Whether Deep Search is on: ahead of `props.deep` until a deep search is made
  const [deepOn, setDeepOn] = createSignal(props.deep ?? false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  // (the address changed otherwise, such as by going back: show it)
  createEffect(
    () => props.query ?? "",
    (query) => {
      if (query !== draft()) setDraft(query);
    },
  );
  createEffect(
    () => props.deep ?? false,
    (deep) => {
      setDeepOn(deep);
    },
  );
  const search = (deep: boolean) => {
    clearTimeout(timer);
    props.onSearch?.({ query: draft(), deep });
  };
  const typed = (text: string) => {
    setDraft(text);
    clearTimeout(timer);
    // (not a deep one: that waits to be asked for)
    if (!deepOn()) timer = setTimeout(() => search(false), DEBOUNCE_MS);
  };
  const toggleDeep = () => {
    const on = !deepOn();
    setDeepOn(on);
    // (turning it off goes back to the ordinary search of what is typed; turning it on makes none)
    if (!on) search(false);
  };
  // Run only changes anything if it is not what is on show already
  const upToDate = () => draft() === (props.query ?? "") && (props.deep ?? false) === deepOn();
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
        aria-label="Search"
        placeholder="Search"
        value={draft()}
        onInput={(event) => typed(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") search(deepOn());
        }}
        class="h-full min-w-0 flex-1 bg-transparent px-3 text-sm font-normal normal-case outline-none placeholder:text-xs placeholder:font-semibold placeholder:text-slate-500 placeholder:uppercase"
      />
      {/* (`count` may be a read that waits for the result, so it has a boundary of its own here,
          or the whole page would wait with it. A spinner stands in for it while it loads) */}
      <span class="flex items-center pr-3 pl-2 text-xs font-semibold text-slate-500 tabular-nums select-none">
        <Show when={!props.pending} fallback={<Spinner />}>
          <Errored fallback="–">
            <Loading fallback={<Spinner />}>
              <span title="Found" class={props.count === 0 ? "text-red-800" : undefined}>
                {props.count}
              </span>
            </Loading>
          </Errored>
        </Show>
      </span>
      <Show when={deepOn()}>
        <ConsoleButton label="Run deep search (Enter)" disabled={upToDate()} onClick={() => search(true)}>
          <svg viewBox="0 0 24 24" class="size-5 select-none fill-current" aria-hidden="true">
            <path d="M8 5.5v13l11-6.5z" />
          </svg>
        </ConsoleButton>
      </Show>
      <ConsoleButton label="Deep search" pressed={deepOn()} onClick={toggleDeep}>
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
    </div>
  );
}
