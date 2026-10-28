import { createSignal } from "solid-js";
import { ConsoleButton } from "../primitives";

/**
 * The text search of a list, for the middle of the console: it fills the height of the bar,
 * with a toggle for Deep Search at its right. (Not connected to anything yet.)
 */
export function ConsoleSearch() {
  const [query, setQuery] = createSignal("");
  const [deep, setDeep] = createSignal(false);
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
        value={query()}
        onInput={(event) => setQuery(event.currentTarget.value)}
        class="h-full min-w-0 flex-1 bg-transparent px-3 text-sm font-normal normal-case outline-none placeholder:text-xs placeholder:font-semibold placeholder:text-slate-500 placeholder:uppercase"
      />
      <ConsoleButton label="Deep search" pressed={deep()} onClick={() => setDeep(!deep())}>
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
