import { Portal } from "@solidjs/web";
import { Loading, onSettled, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import {
  useConsoleMount,
  useModels,
  useTranslations,
  userIsLoggedIn,
} from "../context";
import { ConsoleButton, kindTint, spaceTint } from "../primitives";
import { ConsoleSearch } from "./ConsoleSearch";
import { getModel } from "../schema";
import type { ConsoleProps } from "../types";

// (what the name of a model is when the translations have no plural for it: an English stand-in)
function pluralOf(name: string): string {
  if (/(s|x|ch|sh)$/.test(name)) return `${name}es`;
  if (/[^aeiou]y$/.test(name)) return `${name.slice(0, -1)}ies`;
  return `${name}s`;
}

/**
 * What is in the semantic spaces `spaces` (outermost first): each is a band round the next,
 * the height of the bar, with its name at its left. (The same look as the bands round a result.)
 */
function Wrapped(props: ParentProps<{ spaces: string[]; depth: number }>) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const tint = () =>
    spaceTint(
      getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour,
      props.depth,
    );
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <div
        class={[
          "flex shrink-0 items-stretch self-stretch border-slate-400/70",
          {
            "border-r-[0.5px]": props.depth === 0,
            "rounded-sm border-[0.5px]": props.depth > 0,
          },
          tint(),
        ]}
      >
        {/* (smaller than the type: the spaces are its context, the type is what the item is) */}
        <span class="flex items-center px-2.5 text-[0.6rem] font-semibold uppercase select-none">
          {modelName(props.spaces[0] ?? "")}
        </span>
        <div class="flex items-stretch py-1 pr-1">
          <Wrapped spaces={props.spaces.slice(1)} depth={props.depth + 1}>
            {props.children}
          </Wrapped>
        </div>
      </div>
    </Show>
  );
}

// (a time as the reader's locale says it; what cannot be read is left as it came)
function when(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

/**
 * A row of the history of an item in the console: an icon for what happened (the `children`, the
 * paths of a 24-unit SVG), who did it and when. What happened is said to a screen reader, and as
 * the tooltip, in words.
 */
function HistoryRow(
  props: ParentProps<{ what: string; who?: string | null; when: string }>,
) {
  return (
    <span class="flex items-center gap-1 truncate" title={props.what}>
      <svg
        viewBox="0 0 24 24"
        class="size-3 shrink-0 select-none fill-none stroke-current stroke-2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        {props.children}
      </svg>
      <span class="sr-only">{props.what} </span>
      <Show when={props.who}>
        <span>{props.who} </span>
      </Show>
      <span>· {when(props.when)}</span>
    </span>
  );
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
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  // (a model with no plural of its own in the translations gets the English stand-in, but only in English)
  const plural = () => {
    const named = modelName(props.type, true);
    return named !== props.type ? named : pluralOf(modelName(props.type));
  };
  const kind = () => model()?.kind;
  const wrapped = () => (props.spaces ?? []).length > 0;
  // (tells the bar there is something to show, for as long as the page has this)
  onSettled(() => register());
  return (
    <Show when={mount()}>
      {(element) => (
        <Portal mount={element()}>
          <div class="flex h-full min-w-0 flex-1 items-center justify-between gap-4">
            <div class="flex h-full min-w-0 items-center">
              {/* (the semantic spaces the item is in wrap its type, outermost first, as they wrap a result) */}
              <Wrapped spaces={props.spaces ?? []} depth={0}>
                {/* (the type fills the height of the bar, tinted by its kind; inside a space, a box in the band) */}
                <span
                  class={[
                    "flex shrink-0 items-center self-stretch border-slate-400/70 px-4",
                    {
                      "border-r-[0.5px]": !wrapped(),
                      "rounded-sm border-[0.5px]": wrapped(),
                    },
                    kindTint(kind(), model()?.interfaceMeta?.colour),
                  ]}
                >
                  <Show when={props.list} fallback={modelName(props.type)}>
                    {plural()}
                  </Show>
                </span>
              </Wrapped>
              <Show when={props.label}>
                <span class="truncate px-3 text-sm normal-case">
                  {props.label}
                </span>
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
                  truncated={props.truncated}
                  pending={props.pending}
                />
              </div>
            </Show>
            <div class="flex h-full shrink-0 items-center">
              {/* Who made the item and who last changed it, two light rows (a row only when it is known) */}
              <Show when={props.meta?.createdWhen || props.meta?.updatedWhen}>
                <div
                  class="flex flex-col px-3 text-[0.65rem] leading-tight font-normal text-slate-500 normal-case"
                  data-testid="console-meta"
                >
                  <Show when={props.meta?.createdWhen}>
                    <HistoryRow
                      what={t("created", "Created")}
                      who={props.meta?.createdBy}
                      when={props.meta!.createdWhen!}
                    >
                      {/* (a new page) */}
                      <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
                      <path d="M14 3v5h5M12 11v6M9 14h6" />
                    </HistoryRow>
                  </Show>
                  <Show when={props.meta?.updatedWhen}>
                    <HistoryRow
                      what={t("modified", "Modified")}
                      who={props.meta?.updatedBy}
                      when={props.meta!.updatedWhen!}
                    >
                      {/* (a pen) */}
                      <path d="M4 20h4L19 9l-4-4L4 16v4z" />
                    </HistoryRow>
                  </Show>
                </div>
              </Show>
              {props.children}
              {/* An item can be edited by someone who is logged in */}
              <Loading fallback={null}>
                <Show when={props.editHref && userIsLoggedIn()}>
                  <ConsoleButton label={t("edit", "Edit")} href={props.editHref}>
                    <svg
                      viewBox="0 0 24 24"
                      class="size-5 select-none fill-none stroke-current stroke-2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" />
                    </svg>
                  </ConsoleButton>
                </Show>
              </Loading>
              {/* A list can have a new item made, if the type is one that can be and someone is
                  logged in (reading who is may wait, so it has a boundary of its own) */}
              <Loading fallback={null}>
                <Show
                  when={
                    props.list &&
                    model() &&
                    !model()!.abstract &&
                    userIsLoggedIn()
                  }
                >
                  <ConsoleButton
                    label={t("new_item", "New {type}", {
                      type: modelName(props.type),
                    })}
                    href={`/${props.type}/new`}
                  >
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
              </Loading>
            </div>
          </div>
        </Portal>
      )}
    </Show>
  );
}
