import { For, Show } from "solid-js";
import { useNavExpanded } from "../context";
import { NavIconCell, NavRow, NavRowButton } from "../primitives";
import { NavModelList } from "./NavModelList";
import type { NavBarProps } from "../types";

// (emoji for now) English is shown with the UK flag, German with the Austrian one
const LANGUAGES = [
  { code: "en", name: "English", flag: "🇬🇧" },
  { code: "de", name: "Deutsch", flag: "🇦🇹" },
];

/**
 * The navigation bar down the left of every page: fixed, the full height of the screen,
 * with its own content scrolling inside it. Retracted, it is as wide as a square button
 * (`w-12`). It expands while hovered (or when the button is clicked, as on a touch screen);
 * the state is `useNavExpanded`, so anything can close it. Expanded, it lies over the page rather than pushing it, so that
 * opening it never reflows what is being read. The page is to be in an element with `pl-12`
 * to keep clear of the retracted bar.
 */
export function NavBar(props: NavBarProps) {
  const { navExpanded, setNavExpanded } = useNavExpanded();
  const selected = () =>
    LANGUAGES.find((language) => language.code === props.language) ?? LANGUAGES[0]!;
  return (
    <nav
      aria-label="Main"
      onMouseEnter={() => setNavExpanded(true)}
      onMouseLeave={() => setNavExpanded(false)}
      class={[
        "fixed inset-y-0 left-0 z-40 flex flex-col font-semibold uppercase overflow-hidden border-r border-slate-400/70 bg-slate-300/60 backdrop-blur-md transition-[width] duration-150",
        navExpanded() ? "w-72" : "w-12",
      ]}
    >
      {/* The way home (with room for it), and the button that expands the bar, on the right */}
      <NavRow ruled={false}>
        <Show when={navExpanded()}>
          <NavRowButton inRow href={props.homeHref ?? "/"}>
            Home
          </NavRowButton>
        </Show>
        <NavIconCell
          label={navExpanded() ? "Retract the navigation bar" : "Expand the navigation bar"}
          expanded={navExpanded()}
          onClick={() => setNavExpanded(!navExpanded())}
        >
          <svg
            viewBox="0 0 24 24"
            class={[
              "size-5 select-none fill-none stroke-slate-700 stroke-2 transition-transform duration-150",
              navExpanded() && "rotate-90",
            ]}
            stroke-linecap="round"
            aria-hidden="true"
          >
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </NavIconCell>
      </NavRow>
      {/* Who is logged in: the icon always, and (with room for it) the button to change that */}
      <NavRow>
        <Show when={navExpanded()}>
          <NavRowButton inRow onClick={() => (props.user ? props.onLogout?.() : props.onLogin?.())}>
            <svg
              viewBox="0 0 24 24"
              class="size-4 shrink-0 select-none fill-none stroke-current stroke-2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <Show
                when={props.user}
                fallback={<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" />}
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </Show>
            </svg>
            {props.user ? `Log out ${props.user}` : "Log in"}
          </NavRowButton>
        </Show>
        <NavIconCell label={props.user ? `Logged in as ${props.user}` : "Not logged in"}>
          <svg
            viewBox="0 0 24 24"
            class="size-5 select-none fill-none stroke-current stroke-2"
            stroke-linecap="round"
            stroke-linejoin="round"
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
            <For each={LANGUAGES.filter((language) => language.code !== selected().code)}>
              {(language) => (
                <NavRowButton inRow onClick={() => props.onLanguage?.(language.code)}>
                  <span aria-hidden="true">{language.flag}</span>
                  {language.name}
                </NavRowButton>
              )}
            </For>
          </div>
        </Show>
        <NavIconCell label={`Language: ${selected().name}`}>
          <span class="select-none text-xl">{selected().flag}</span>
        </NavIconCell>
      </NavRow>
      {/* (not rendered while retracted: there is no room for it to be read) */}
      <Show when={navExpanded()}>
        <div class="min-h-0 flex-1 overflow-y-auto border-t border-slate-400/70">
          <NavModelList />
          {props.children}
        </div>
      </Show>
    </nav>
  );
}
