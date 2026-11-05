import { Portal } from "@solidjs/web";
import { Errored, For, Loading, onSettled, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import {
  useConsoleMount,
  useIncomingOrder,
  useModels,
  useModules,
  useTranslations,
  userIsLoggedIn,
} from "../context";
import { DeleteButton } from "./form/DeleteButton";
import { ConsoleButton, kindRule, kindTint, spaceTint } from "../primitives";
import { ConsoleSearch } from "./ConsoleSearch";
import { canCreate, getModel } from "../schema";
import type { ConsoleProps } from "../types";

// (what the name of a model is when the translations have no plural for it: an English stand-in)
function pluralOf(name: string): string {
  if (/(s|x|ch|sh)$/.test(name)) return `${name}es`;
  if (/[^aeiou]y$/.test(name)) return `${name.slice(0, -1)}ies`;
  return `${name}s`;
}

/**
 * What is in the semantic spaces `spaces` (outermost first), as they are beside a chip: the name of
 * each a muted tab before what is in it, the height of the bar, each a box of its colour that the
 * next is inside, rounded on its left with a hairline, on a base the colour of the bar (so the
 * colours of the spaces round it do not show through, but at its rounded corners). The top and
 * bottom are the bar's own edges.
 */
function Wrapped(props: ParentProps<{ spaces: string[]; depth: number }>) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <div
        class={[
          "relative isolate flex shrink-0 items-stretch self-stretch",
          // (quieter than the type: a veil over the tint, under what is in it)
          "before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:bg-white/30",
          // (the outermost is at the left end of the bar; the others are in the one before)
          { "rounded-l-xs border-l-[0.5px] border-slate-400/70 before:rounded-l-xs": props.depth > 0 },
          spaceTint(getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour, props.depth),
        ]}
      >
        <span class="flex items-center px-2.5 font-medium select-none">
          <span class="opacity-70">{modelName(props.spaces[0] ?? "")}</span>
        </span>
        <div class="flex items-stretch rounded-l-xs bg-slate-100 text-slate-700">
          <Wrapped spaces={props.spaces.slice(1)} depth={props.depth + 1}>
            {props.children}
          </Wrapped>
        </div>
      </div>
    </Show>
  );
}

// (a time as it is said in the language of the page; what cannot be read is left as it came)
function when(value: string, language: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(language, {
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
  const { language } = useTranslations();
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
      <span>· {when(props.when, language())}</span>
    </span>
  );
}

/**
 * What the interface modules add to the console of an item (their `consoleActions`), each given the item. One that
 * fails, or is still loading, shows nothing, and the rest of the console is unaffected.
 */
function ModuleActions(props: { item: ConsoleProps["item"]; page: "item" | "edit" }) {
  const definitions = useModels();
  const actions = useModules().consoleActions();
  return (
    <Show when={actions.length > 0 && props.item}>
      {(item) => (
        <Show when={getModel(definitions, item().type)}>
          {(model) => (
            <For each={actions}>
              {(Action) => (
                <Errored
                  fallback={(error) => {
                    // (said in the browser's console, so that a module's author sees why there is nothing)
                    console.error("A console action of an interface module failed:", error());
                    return null;
                  }}
                >
                  <Loading fallback={null}>
                    <Action type={item().type} id={item().id} model={model()} page={props.page} />
                  </Loading>
                </Errored>
              )}
            </For>
          )}
        </Show>
      )}
    </Show>
  );
}

/**
 * A toggle, while the page offers it (it has something that refers to its item that can be dated): pressed, what refers
 * to the item is sorted by date; not pressed, grouped by the relation it is in
 */
function IncomingOrderToggle() {
  const { t } = useTranslations();
  const incoming = useIncomingOrder();
  return (
    <Show when={incoming.offered()}>
      <ConsoleButton
        label={t("incoming_sort_by_date", "Sort by date")}
        pressed={incoming.order() === "date"}
        onClick={() => incoming.setOrder(incoming.order() === "date" ? "field" : "date")}
      >
        {/* (a calendar) */}
        <svg
          viewBox="0 0 24 24"
          class="size-5 select-none fill-none stroke-current stroke-2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM4 10.5h16M8.5 3.5v4M15.5 3.5v4" />
        </svg>
      </ConsoleButton>
    </Show>
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
              {/* (the semantic spaces the item is in come before its type, outermost first, as they do before a chip) */}
              <Wrapped spaces={props.spaces ?? []} depth={0}>
                {/* (the type fills the height of the bar, tinted by its kind, its sides in that colour as a chip's type is
                     framed; inside a space, rounded on its left, as a tab in one is) */}
                <span
                  class={[
                    "flex shrink-0 items-center self-stretch border-r-[0.5px] px-4",
                    { "rounded-l-xs border-l-[0.5px]": wrapped() },
                    kindTint(kind(), model()?.interfaceMeta?.colour),
                    kindRule(kind(), model()?.interfaceMeta?.colour),
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
                  onToggleForm={props.onToggleForm}
                  formOpen={props.formOpen}
                  structured={props.structured}
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
                    {(created) => (
                      <HistoryRow what={t("created", "Created")} who={props.meta?.createdBy} when={created()}>
                        {/* (a new page) */}
                        <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
                        <path d="M14 3v5h5M12 11v6M9 14h6" />
                      </HistoryRow>
                    )}
                  </Show>
                  <Show when={props.meta?.updatedWhen}>
                    {(updated) => (
                      <HistoryRow what={t("modified", "Modified")} who={props.meta?.updatedBy} when={updated()}>
                        {/* (a pen) */}
                        <path d="M4 20h4L19 9l-4-4L4 16v4z" />
                      </HistoryRow>
                    )}
                  </Show>
                </div>
              </Show>
              <Show when={(props.page ?? "item") === "item"}>
                <IncomingOrderToggle />
              </Show>
              <ModuleActions item={props.item} page={props.page ?? "item"} />
              {props.children}
              {/* An item can be deleted and edited by someone who is logged in */}
              <Loading fallback={null}>
                <Show when={props.item && props.onDeleted && userIsLoggedIn()}>
                  <DeleteButton
                    type={props.item!.type}
                    id={props.item!.id}
                    label={props.label}
                    onDeleted={() => props.onDeleted?.()}
                  />
                </Show>
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
                    canCreate(model()!) &&
                    userIsLoggedIn()
                  }
                >
                  <ConsoleButton
                    label={t("new_item", "New {type}", {
                      type: modelName(props.type),
                    })}
                    href={props.onNew ? undefined : `/${props.type}/new`}
                    onClick={props.onNew ? () => props.onNew?.() : undefined}
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
