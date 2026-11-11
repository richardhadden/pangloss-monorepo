import { inputClass, MenuSelect } from "@pangloss/interface-core";
import type { MenuOption } from "@pangloss/interface-core";
import { onCleanup } from "solid-js";

/** How long after the last key the table is read again */
const TYPING_MS = 250;

/**
 * A box that filters a table as it is typed in: a moment after the last key, `onSearch` is given the words (the page
 * puts them in its address, and reads the table again). No button: there is nothing to send.
 */
export function LiveSearch(props: {
  /** What it searches: its name for a screen reader, and what it says while empty */
  label: string;
  /** What it holds when the page is made (the reader's own after that) */
  starting: string;
  onSearch: (words: string) => void;
  testid: string;
}) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  const say = (words: string, wait: number) => {
    clearTimeout(timer);
    timer = setTimeout(() => props.onSearch(words.trim()), wait);
  };
  return (
    <div role="search" class="w-64 max-w-full">
      <input
        type="search"
        class={inputClass}
        aria-label={props.label}
        placeholder={props.label}
        data-testid={props.testid}
        value={props.starting}
        onInput={(event) => say(event.currentTarget.value, TYPING_MS)}
        // (Enter does not wait)
        onKeyDown={(event) => {
          if (event.key === "Enter") say(event.currentTarget.value, 0);
        }}
      />
    </div>
  );
}

/** A choice that filters a table, named at its left: the menu of the search form */
export function ChoiceFilter(props: {
  label: string;
  value: string;
  options: MenuOption[];
  onChoose: (value: string) => void;
  /** Classes of the menu's width */
  class?: string;
}) {
  return (
    <div class="flex items-center gap-2">
      <span class="text-xs font-semibold text-slate-600 uppercase" aria-hidden="true">
        {props.label}
      </span>
      <MenuSelect
        label={props.label}
        value={props.value}
        options={props.options}
        class={props.class ?? "w-44"}
        onChoose={props.onChoose}
      />
    </div>
  );
}
