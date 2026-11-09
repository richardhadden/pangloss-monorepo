import { createSignal, For, onCleanup, onSettled, Show } from "solid-js";
import { useModels, useNavExpanded, useTranslations } from "../context";
import { NavIconCell, NavRow, NavRowButton } from "../primitives";
import { dialogIsOpen, isMac, isNavShortcut, isNewItemShortcut, isPlainEnter } from "./keys";
import { NavModelList } from "./NavModelList";
import type { NavListKey } from "./NavModelList";
import type { NavBarProps } from "../types";

// (emoji for now) a language has a flag only where it is chosen here; the others show their code. English is shown
// with the UK flag, German with the Austrian one, French with the French one
const FLAGS: Record<string, string> = { en: "🇬🇧", de: "🇦🇹", fr: "🇫🇷" };

/** A language is named in itself ("Deutsch"), not in the language of the page */
function languageName(code: string): string {
  try {
    const name = new Intl.DisplayNames([code], { type: "language" }).of(code);
    return name ? name.charAt(0).toLocaleUpperCase(code) + name.slice(1) : code;
  } catch {
    return code;
  }
}

/** A project's name as a person would write it: `my_project`, `my-project` and `myProject` are "my project" */
export function readableName(name: string): string {
  return name.replace(/[-_]+/g, " ").replace(/([\p{Ll}\d])(\p{Lu})/gu, "$1 $2").trim();
}

/**
 * The navigation bar down the left of every page: fixed, the full height of the screen,
 * with its own content scrolling inside it. Retracted, it is as wide as a square button
 * (`w-12`). It expands while hovered (or when the button is clicked, as on a touch screen);
 * the state is `useNavExpanded`, so anything can close it. Expanded, it lies over the page rather than pushing it, so that
 * opening it never reflows what is being read. While it is open the button is a pin: clicking
 * it pins the bar open, and the page moves across (`pl-72` rather than `pl-12`, from
 * `navPinned`) so that they do not overlap. The page is to be in an element with `pl-12`
 * to keep clear of the retracted bar.
 *
 * Above the types is a box that filters them (`NavModelList`'s `filter`); what is typed in it is
 * kept while the bar is retracted, until a type is gone to.
 *
 * Cmd+K (Ctrl+K off a Mac; `isNavShortcut`) opens the bar with the cursor in that box. Again, or Escape in the empty box,
 * closes it and gives the focus back; so does the focus leaving the bar, there being no mouse to leave it. While the
 * cursor is in the box, the arrows choose a type, Enter opens its list and Cmd/Ctrl+Enter makes a new one. Going to a type,
 * so or with the mouse, empties the box. The retracted bar shows the shortcut at its foot.
 */
export function NavBar(props: NavBarProps) {
  const { navExpanded, setNavExpanded, navPinned, setNavPinned } = useNavExpanded();
  const { t, language, languages, setLanguage } = useTranslations();
  const definitions = useModels();
  const flag = (code: string) => FLAGS[code] ?? code.toUpperCase();
  const [filter, setFilter] = createSignal("");
  // The scrollbar of the list floats over it, so the rows go to the edge of the bar (a native one takes room from them, and
  // has its own background). It is shown only while the list is scrolled, for a moment after, and while the pointer is on it.
  const [scrolling, setScrolling] = createSignal(false);
  const [thumb, setThumb] = createSignal({ top: 0, height: 0 });
  let scroller: HTMLDivElement | undefined;
  let thumbHeld = false;
  let dragFrom: { y: number; scrollTop: number } | undefined;
  let scrollTimer: ReturnType<typeof setTimeout> | undefined;
  const showScrollbar = () => {
    setScrolling(true);
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      if (!thumbHeld) setScrolling(false);
    }, 800);
  };
  const onListScroll = () => {
    if (!scroller) return;
    const { scrollTop, scrollHeight, clientHeight } = scroller;
    const height = Math.max(24, (clientHeight * clientHeight) / scrollHeight);
    setThumb({ top: (scrollTop / (scrollHeight - clientHeight)) * (clientHeight - height), height });
    showScrollbar();
  };
  const dragThumb = (event: PointerEvent) => {
    if (!scroller || !dragFrom) return;
    const { scrollHeight, clientHeight } = scroller;
    scroller.scrollTop =
      dragFrom.scrollTop + ((event.clientY - dragFrom.y) * (scrollHeight - clientHeight)) / (clientHeight - thumb().height);
  };
  onCleanup(() => clearTimeout(scrollTimer));
  let nav: HTMLElement | undefined;
  // (the box while it is there: it is made only when the bar is expanded, so it may have to be waited for)
  let filterBox: HTMLInputElement | undefined;
  let focusWhenShown = false;
  // (what had the focus before the shortcut)
  let returnTo: HTMLElement | null = null;
  const [filterFocused, setFilterFocused] = createSignal(false);
  // (not known until in the browser: the page is first made on the server)
  const [mac, setMac] = createSignal<boolean>();
  let listKey: NavListKey | undefined;
  // (what is left in it from the last time is selected, so that typing replaces it)
  const focusFilter = (box: HTMLInputElement) => {
    box.focus();
    box.select();
  };
  const dismiss = () => {
    setNavExpanded(false);
    returnTo?.focus();
  };
  onSettled(() => {
    setMac(isMac());
    const onKey = (event: KeyboardEvent) => {
      if (!isNavShortcut(event) || dialogIsOpen()) return;
      event.preventDefault();
      if (filterBox?.isConnected && document.activeElement === filterBox) return dismiss();
      returnTo = document.activeElement as HTMLElement | null;
      if (filterBox?.isConnected) return focusFilter(filterBox);
      focusWhenShown = true;
      setNavExpanded(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  return (
    <nav
      ref={nav}
      aria-label={t("nav_main", "Main")}
      onMouseEnter={() => setNavExpanded(true)}
      onMouseLeave={() => setNavExpanded(false)}
      onFocusOut={(event) => {
        if (!nav?.contains(event.relatedTarget as Node | null) && !nav?.matches(":hover")) setNavExpanded(false);
      }}
      class={[
        "fixed inset-y-0 left-0 z-40 flex flex-col font-semibold uppercase overflow-hidden border-r-[0.5px] border-slate-400/70 bg-slate-300/60 backdrop-blur-md transition-[width,box-shadow] duration-150",
        {
          "w-72": navExpanded(),
          "w-12": !navExpanded(),
          // (lying over the page, it has a shadow; pinned, it is beside the page)
          "shadow-[1px_0_3px_rgb(0_0_0/0.08)]": navExpanded() && !navPinned(),
        },
      ]}
    >
      {/* The way home, under the name of the project (with room for it), and the button that expands the bar, on the right */}
      <NavRow>
        <Show when={navExpanded()}>
          <NavRowButton inRow href={props.homeHref ?? "/"}>
            {definitions.projectName ? readableName(definitions.projectName) : t("home", "Home")}
          </NavRowButton>
        </Show>
        <NavIconCell
          label={
            navPinned()
              ? t("nav_unpin", "Unpin the navigation bar")
              : navExpanded()
                ? t("nav_pin", "Pin the navigation bar open")
                : t("nav_expand", "Expand the navigation bar")
          }
          expanded={navExpanded()}
          onClick={() => (navExpanded() ? setNavPinned(!navPinned()) : setNavExpanded(true))}
        >
          <Show
            when={navExpanded()}
            fallback={
              <svg
                viewBox="0 0 24 24"
                class="size-5 select-none fill-none stroke-slate-700 stroke-[1.5]"
                stroke-linecap="square"
                aria-hidden="true"
              >
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            }
          >
            {/* A pin: upright and filled while pinned, tilted and outlined while not */}
            <svg
              viewBox="0 0 24 24"
              class={[
                "size-5 select-none stroke-slate-700 stroke-[1.5] transition-transform duration-150",
                { "fill-slate-700 rotate-0": navPinned(), "fill-none rotate-45": !navPinned() },
              ]}
              stroke-linecap="square"
              aria-hidden="true"
            >
              <path d="M12 17v5M9 3h6l-1 7 3 3v2H7v-2l3-3z" />
            </svg>
          </Show>
        </NavIconCell>
      </NavRow>
      {/* Who is logged in: the icon always, and (with room for it) the button to change that */}
      <NavRow>
        <Show when={navExpanded()}>
          <NavRowButton inRow onClick={() => (props.user ? props.onLogout?.() : props.onLogin?.())}>
            <svg
              viewBox="0 0 24 24"
              class="size-4 shrink-0 select-none fill-none stroke-current stroke-[1.75]"
              stroke-linecap="square"
              aria-hidden="true"
            >
              <Show
                when={props.user}
                fallback={<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" />}
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </Show>
            </svg>
            <Show when={props.user} fallback={t("log_in", "Log in")}>
              {t("log_out_user", "Log out {user}", { user: props.user ?? "" })}
            </Show>
          </NavRowButton>
        </Show>
        <NavIconCell label={
            props.user
              ? t("status_logged_in_as", "Logged in as {user}", { user: props.user })
              : t("status_not_logged_in", "Not logged in")
          }>
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-[1.5]"
            stroke-linecap="square"
            aria-hidden="true"
          >
            <circle cx="10" cy="8" r="4" />
            <path d="M2 21a8 8 0 0 1 16 0" />
            <Show
              when={props.user}
              fallback={<path d="M17 8l5 5M22 8l-5 5" class="stroke-red-600" />}
            >
              <path d="M16 11l2 2 4-4" class="stroke-green-600" />
            </Show>
          </svg>
        </NavIconCell>
      </NavRow>
      {/* The language: the flag of the one selected, and (with room for them) the others */}
      <NavRow>
        <Show when={navExpanded()}>
          <div class="flex h-full min-w-0 flex-1">
            <For each={languages().filter((code) => code !== language())}>
              {(code) => (
                <NavRowButton
                  inRow
                  onClick={() => {
                    void setLanguage(code);
                    props.onLanguage?.(code);
                  }}
                >
                  <span aria-hidden="true" class="opacity-70">{flag(code)}</span>
                  {languageName(code)}
                </NavRowButton>
              )}
            </For>
          </div>
        </Show>
        <NavIconCell
          label={t("language_current", "Language: {language}", {
            language: languageName(language()),
          })}
        >
          <span class="select-none text-xl opacity-70">{flag(language())}</span>
        </NavIconCell>
      </NavRow>
      {/* (not rendered while retracted: there is no room for it to be read) */}
      <Show when={navExpanded()}>
        <NavFilter
          value={filter()}
          onInput={setFilter}
          onEscape={dismiss}
          onShown={(box) => {
            filterBox = box;
            if (focusWhenShown) focusFilter(box);
            focusWhenShown = false;
            setFilterFocused(document.activeElement === box);
          }}
          onFocusChange={setFilterFocused}
          onListKey={(key) => listKey?.(key)}
        />
        <div class="relative min-h-0 flex-1">
          {/* (room at the bottom so that the last item is not under the browser's preview of a hovered link) */}
          <div ref={scroller} onScroll={onListScroll} class="h-full overflow-y-auto pb-12 [scrollbar-width:none]">
            <NavModelList
              loggedIn={props.user !== undefined}
              filter={filter()}
              selecting={filterFocused()}
              keys={(key) => (listKey = key)}
              onFollow={() => setFilter("")}
              onNew={(type) => {
                setFilter("");
                props.onNavigate?.(`/${type}/new`);
                setNavExpanded(false);
              }}
            />
            {props.children}
          </div>
          {/* (wider than what is drawn, to be easier to take hold of) */}
          <div
            aria-hidden="true"
            onPointerEnter={() => (thumbHeld = true)}
            onPointerLeave={() => {
              thumbHeld = false;
              showScrollbar();
            }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              dragFrom = { y: event.clientY, scrollTop: scroller?.scrollTop ?? 0 };
            }}
            onPointerMove={dragThumb}
            onPointerUp={() => (dragFrom = undefined)}
            onPointerCancel={() => (dragFrom = undefined)}
            style={{ top: `${thumb().top}px`, height: `${thumb().height}px` }}
            class={[
              "absolute right-0 flex w-2.5 cursor-default touch-none justify-end pr-0.5 transition-opacity duration-150 select-none",
              { "opacity-0": !scrolling(), "pointer-events-none": !scrolling() },
            ]}
          >
            <div class="h-full w-1 rounded-xs bg-slate-600/45" />
          </div>
        </div>
      </Show>
      {/* (always there, so that it can fade as the bar opens; it is only a reminder, and the shortcut is described elsewhere) */}
      <kbd
        aria-hidden="true"
        class={[
          "pointer-events-none absolute bottom-2 left-0 w-12 text-center font-sans text-[10px] font-normal whitespace-nowrap normal-case text-slate-600 transition-opacity duration-150 select-none",
          { "opacity-0": navExpanded() || mac() === undefined },
        ]}
      >
        {mac() ? "⌘ + K" : `${t("key_ctrl", "Ctrl")} + K`}
      </kbd>
    </nav>
  );
}

/**
 * The box that filters the types of the navigation bar, above the list (which scrolls under it), with
 * a button that clears it (as Escape does; Escape with nothing to clear is `onEscape`).
 */
function NavFilter(props: {
  value: string;
  onInput: (value: string) => void;
  onEscape: () => void;
  onShown: (box: HTMLInputElement) => void;
  onFocusChange: (focused: boolean) => void;
  onListKey: NavListKey;
}) {
  const { t } = useTranslations();
  let input: HTMLInputElement | undefined;
  onSettled(() => {
    if (input) props.onShown(input);
  });
  const clear = () => {
    props.onInput("");
    input?.focus();
  };
  return (
    <div class="border-b-[0.5px] border-slate-400/70 bg-slate-300/80 p-2">
      <div class="flex h-8 items-center rounded-xs border-[0.5px] border-slate-400/70 bg-white/70 focus-within:border-slate-500 focus-within:bg-white">
        <svg
          viewBox="0 0 24 24"
          class="ml-2 size-4 shrink-0 select-none fill-none stroke-slate-500 stroke-[1.75]"
          stroke-linecap="square"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="6" />
          <path d="M20 20l-4.5-4.5" />
        </svg>
        <input
          ref={input}
          type="search"
          value={props.value}
          onInput={(event) => props.onInput(event.currentTarget.value)}
          onFocus={() => props.onFocusChange(true)}
          onBlur={() => props.onFocusChange(false)}
          onKeyDown={(event) => {
            const plain = !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
            if (plain && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
              event.preventDefault();
              props.onListKey(event.key === "ArrowDown" ? "next" : "previous");
            } else if (isPlainEnter(event)) {
              event.preventDefault();
              props.onListKey("open");
            } else if (isNewItemShortcut(event)) {
              event.preventDefault();
              props.onListKey("new");
            } else if (event.key === "Escape") {
              event.preventDefault();
              if (props.value !== "") props.onInput("");
              else props.onEscape();
            }
          }}
          placeholder={t("nav_filter", "Filter types")}
          aria-label={t("nav_filter", "Filter types")}
          class="h-full min-w-0 flex-1 bg-transparent px-2 text-sm font-normal normal-case text-slate-800 outline-none placeholder:text-slate-500 [&::-webkit-search-cancel-button]:hidden"
        />
        <Show when={props.value !== ""}>
          <button
            type="button"
            aria-label={t("nav_filter_clear", "Clear the filter")}
            title={t("nav_filter_clear", "Clear the filter")}
            onClick={clear}
            class="flex h-full w-8 shrink-0 cursor-pointer items-center justify-center text-slate-500 hover:text-slate-800"
          >
            <svg
              viewBox="0 0 24 24"
              class="size-4 select-none fill-none stroke-current stroke-[1.75]"
              stroke-linecap="square"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </Show>
      </div>
    </div>
  );
}
