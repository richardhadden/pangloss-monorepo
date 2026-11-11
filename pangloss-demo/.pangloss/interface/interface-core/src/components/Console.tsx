import { Portal } from "@solidjs/web";
import { Errored, For, Loading, onSettled, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import {
  useConsoleMount,
  useModels,
  useModules,
  useTranslations,
  userIsLoggedIn,
} from "../context";
import { DeleteButton } from "./form/DeleteButton";
import { ConsoleButton, kindRule, kindTint, spaceTint } from "../primitives";
import { ConsoleSearch } from "./ConsoleSearch";
import { canCreate, getModel, pluralNameOf, readableTime } from "../schema";
import { dialogIsOpen, isEditShortcut, isNewItemShortcut } from "./keys";
import type { ConsoleProps, Creator } from "../types";

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
          <span data-type-info={props.spaces[0]} class="opacity-70">{modelName(props.spaces[0] ?? "")}</span>
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

/**
 * A row of the history of an item in the console: an icon for what happened (the `children`, the
 * paths of a 24-unit SVG), who did it (a link to their page, if there is one) and when. What happened is said to a screen reader, and as
 * the tooltip, in words.
 */
function HistoryRow(
  props: ParentProps<{ what: string; who?: Creator[] | string | null; when: string; note?: string }>,
) {
  const { language } = useTranslations();
  // (those who made it are several; who changed it last is one name)
  const people = (): Creator[] =>
    typeof props.who === "string" ? [{ username: props.who, kind: "user" }] : (props.who ?? []);
  return (
    <span class="flex items-center gap-1 truncate" title={props.note ? `${props.what} (${props.note})` : props.what}>
      <svg
        viewBox="0 0 24 24"
        class="size-3 shrink-0 select-none fill-none stroke-current stroke-2"
        stroke-linecap="square"
        aria-hidden="true"
      >
        {props.children}
      </svg>
      <span class="sr-only">{props.what} </span>
      <For each={people()}>
        {(person, index) => (
          <span data-testid="console-person" data-kind={person.kind}>
            <PersonName username={person.username} />
            {/* (a toolchain: which version of it) */}
            <Show when={person.version}>
              <span class="text-slate-400"> {person.version}</span>
            </Show>
            <Show when={index() < people().length - 1} fallback=" ">
              {", "}
            </Show>
          </span>
        )}
      </For>
      <span>· {readableTime(props.when, language())}</span>
    </span>
  );
}

/** A user's name in the console: a link to their page for someone logged in, if a module gives one */
function PersonName(props: { username: string }) {
  const { userHref } = useModules();
  return (
    // (reading who is logged in may wait, so it has a boundary of its own)
    <Loading fallback={<span>{props.username}</span>}>
      <Show when={userIsLoggedIn() && userHref(props.username)} fallback={<span>{props.username}</span>}>
        {(href) => (
          <a href={href()} class="underline-offset-2 hover:text-slate-800 hover:underline">
            {props.username}
          </a>
        )}
      </Show>
    </Loading>
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
              {(action) => (
                <Show when={!action.loggedIn || userIsLoggedIn()}>
                <Errored
                  fallback={(error) => {
                    // (said in the browser's console, so that a module's author sees why there is nothing)
                    console.error("A console action of an interface module failed:", error());
                    return null;
                  }}
                >
                  <Loading fallback={null}>
                    <action.component type={item().type} id={item().id} model={model()} page={props.page} />
                  </Loading>
                </Errored>
                </Show>
              )}
            </For>
          )}
        </Show>
      )}
    </Show>
  );
}

/**
 * A keyboard shortcut that clicks a button of the console: made only where the button is, so what it does and who may
 * are the button's. (What took the key first, the navigation bar's filter, has dealt with it.)
 */
function ButtonKey(props: { matches: (event: KeyboardEvent) => boolean; button: () => HTMLElement | undefined }) {
  onSettled(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!props.matches(event) || event.defaultPrevented || event.repeat || dialogIsOpen()) return;
      event.preventDefault();
      props.button()?.click();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  return null;
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
  const { jsonLinkTaken } = useModules();
  const model = () => getModel(definitions, props.type);
  // (a model with no plural of its own in the translations gets the English stand-in, but only in English)
  const plural = () => pluralNameOf(modelName, props.type);
  const kind = () => model()?.kind;
  const wrapped = () => (props.spaces ?? []).length > 0;
  let newButton: HTMLElement | undefined;
  let editButton: HTMLElement | undefined;
  // (tells the bar there is something to show, for as long as the page has this)
  onSettled(() => register());
  return (
    <Show when={mount()}>
      {(element) => (
        <Portal mount={element()}>
          <div class="flex h-full min-w-0 flex-1 items-center justify-between gap-4">
            <div class="flex h-full min-w-0 items-center">
              <Show when={props.formMode}>
                {(mode) => (
                  <span class="flex shrink-0 items-center self-stretch border-r-[0.5px] border-slate-400/70 bg-slate-300/70 px-3 select-none">
                    <Show when={mode() === "new"} fallback={t("edit", "Edit")}>
                      {t("new", "New")}
                    </Show>
                  </span>
                )}
              </Show>
              {/* (the semantic spaces the item is in come before its type, outermost first, as they do before a chip) */}
              <Wrapped spaces={props.spaces ?? []} depth={0}>
                {/* (the type fills the height of the bar, tinted by its kind, its sides in that colour as a chip's type is
                     framed; inside a space, rounded on its left, as a tab in one is) */}
                <span
                  data-type-info={props.type}
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
                  onToggleUsed={props.onToggleUsed}
                  showingAll={props.showingAll}
                  structured={props.structured}
                  onListKey={props.onListKey}
                  onFocusChange={props.onFocusChange}
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
                      <HistoryRow
                        what={t("created", "Created")}
                        who={props.meta?.createdBy}
                        when={created()}
                        note={props.meta?.uploadedBy ? `${t("uploaded_by", "uploaded by")} ${props.meta.uploadedBy}` : undefined}
                      >
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
              <ModuleActions item={props.item} page={props.page ?? "item"} />
              {props.children}
              {/* An item's HeadView as the API gives it, for anyone who can see the item (a new tab: not a page of the interface) */}
              <Show when={props.page === "item" && !jsonLinkTaken() && props.item}>
                {(item) => (
                  <ConsoleButton
                    label={t("view_json", "View as JSON")}
                    href={`/api/${encodeURIComponent(item().type)}/${encodeURIComponent(item().id)}`}
                    newTab
                  >
                    <svg
                      viewBox="0 0 24 24"
                      class="size-5 select-none fill-none stroke-current stroke-[1.5]"
                      aria-hidden="true"
                    >
                      <path d="M9 4H8a2 2 0 0 0-2 2v4l-2 2 2 2v4a2 2 0 0 0 2 2h1M15 4h1a2 2 0 0 1 2 2v4l2 2-2 2v4a2 2 0 0 1-2 2h-1" />
                    </svg>
                  </ConsoleButton>
                )}
              </Show>
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
                  <ButtonKey matches={isEditShortcut} button={() => editButton} />
                  <ConsoleButton label={t("edit", "Edit")} href={props.editHref} elementRef={(element) => (editButton = element)}>
                    <svg
                      viewBox="0 0 24 24"
                      class="size-5 select-none fill-none stroke-current stroke-[1.5]"
                      stroke-linecap="square"
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
                  <ButtonKey matches={isNewItemShortcut} button={() => newButton} />
                  <ConsoleButton
                    elementRef={(element) => (newButton = element)}
                    label={t("new_item", "New {type}", {
                      type: modelName(props.type),
                    })}
                    href={props.onNew ? undefined : `/${props.type}/new`}
                    onClick={props.onNew ? () => props.onNew?.() : undefined}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      class="size-5 select-none fill-none stroke-current stroke-[1.5]"
                      stroke-linecap="square"
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
