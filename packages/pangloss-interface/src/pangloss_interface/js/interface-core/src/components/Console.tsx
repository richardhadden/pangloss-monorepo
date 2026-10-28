import { Portal } from "@solidjs/web";
import { onSettled, Show } from "solid-js";
import { useConsoleMount, useModels } from "../context";
import { ConsoleButton, kindTint } from "../primitives";
import { ConsoleSearch } from "./ConsoleSearch";
import { getModel } from "../schema";
import type { ConsoleProps } from "../types";

// (a stand-in until the translations are connected: they will have the plural of each name)
function pluralOf(name: string): string {
  if (/(s|x|ch|sh)$/.test(name)) return `${name}es`;
  if (/[^aeiou]y$/.test(name)) return `${name.slice(0, -1)}ies`;
  return `${name}s`;
}

/**
 * What a page says about itself in the console bar: on the left the type (in the plural
 * for a list) and, for one item, its label; on the right the actions that can be taken
 * (the `children`). It renders into the bar by a portal, so a page puts it anywhere in its
 * own markup. The server renders nothing for a portal: it appears when the page is
 * hydrated. A page without a `Console` has no console: the bar is hidden.
 */
export function Console(props: ConsoleProps) {
  const { mount, register } = useConsoleMount();
  const definitions = useModels();
  const model = () => getModel(definitions, props.type);
  const kind = () => model()?.kind;
  // (tells the bar there is something to show, for as long as the page has this)
  onSettled(() => register());
  return (
    <Show when={mount()}>
      {(element) => (
        <Portal mount={element()}>
          <div class="flex h-full min-w-0 flex-1 items-center justify-between gap-4">
            <div class="flex h-full min-w-0 items-center">
              {/* (the type fills the height of the bar, tinted by its kind) */}
              <span class={["flex h-full shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-4", kindTint(kind())]}>
                {props.list ? pluralOf(props.type) : props.type}
              </span>
              <Show when={props.label}>
                <span class="truncate px-3 text-sm normal-case">{props.label}</span>
              </Show>
            </div>
            {/* A list has a search, in the middle */}
            <Show when={props.list}>
              <div class="flex h-full min-w-0 flex-1 items-center justify-center">
                <ConsoleSearch
                  query={props.query}
                  onSearch={props.onSearch}
                  deep={props.deep}
                  count={props.count}
                  pending={props.pending}
                />
              </div>
            </Show>
            <div class="flex h-full shrink-0 items-center">
              {props.children}
              {/* A list can have a new item made, if the type is one that can be */}
              <Show when={props.list && model() && !model()!.abstract}>
                <ConsoleButton label={`New ${props.type}`} href={`/${props.type}/new`}>
                  <svg
                    viewBox="0 0 24 24"
                    class="size-5 select-none fill-none stroke-current stroke-2"
                    stroke-linecap="round"
                    aria-hidden="true"
                  >
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </ConsoleButton>
              </Show>
            </div>
          </div>
        </Portal>
      )}
    </Show>
  );
}
