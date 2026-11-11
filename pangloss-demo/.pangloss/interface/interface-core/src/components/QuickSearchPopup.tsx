import { Portal } from "@solidjs/web";
import { createEffect, createMemo, createSignal, Errored, For, Loading, onSettled, Reveal } from "solid-js";
import type { JSX } from "@solidjs/web";
import { getItem } from "../api";
import { useApi, useComponent, useModules, useTranslations } from "../context";
import { buttonClass, Spinner } from "../primitives";
import { GlobalSearch } from "./GlobalSearch";
import { ItemSections } from "./ItemSections";

export interface QuickSearchPopupProps {
  onNavigate: (href: string) => void;
  onClose: () => void;
}

interface Picked {
  type: string;
  id: string;
  label: string;
}

const hrefOf = (item: Picked) => `/${encodeURIComponent(item.type)}/${encodeURIComponent(item.id)}`;

// (what the panes' padding adds to what is in them, and what is left under the box with nothing in them)
const PANE_PADDING = 28;
const EMPTY_HEIGHT = 12;

function PickedItem(props: { item: Picked }) {
  const api = useApi();
  const modules = useModules();
  const ItemContents = useComponent("ItemContents");
  const ErrorMessage = useComponent("ErrorMessage");
  const item = createMemo(() => {
    modules.preloadItemPage(props.item.type);
    return getItem(api, props.item.type, props.item.id, { incomingLimit: 0, extras: false });
  });
  return (
    <Errored fallback={(error) => <ErrorMessage error={error()} />}>
      <Loading
        fallback={
          <div data-quick-search-loading>
            <Spinner class="size-5 text-slate-500" />
          </div>
        }
      >
        <Reveal>
          <ItemContents item={item()} />
          <ItemSections item={item()} />
        </Reveal>
      </Loading>
    </Errored>
  );
}

/** The panel of the quick search: the search, and an item from it, which the list slides away for and the panel grows round */
export default function QuickSearchPopup(props: QuickSearchPopupProps) {
  const { t } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const [picked, setPicked] = createSignal<Picked>();
  const [showing, setShowing] = createSignal<"results" | "item">("results");
  const [height, setHeight] = createSignal(EMPTY_HEIGHT);
  const isItem = () => showing() === "item";
  const opener = document.activeElement as HTMLElement | null;
  let panel: HTMLDivElement | undefined;
  let resultsContent: HTMLDivElement | undefined;
  let itemContent: HTMLDivElement | undefined;
  let itemPane: HTMLDivElement | undefined;
  // (as signals are: a key can come before the flush)
  let view: "results" | "item" = "results";
  let shown: Picked | undefined;
  let applied = EMPTY_HEIGHT;

  const show = (next: "results" | "item") => {
    view = next;
    setShowing(next);
  };
  const measure = () => {
    const content = view === "item" ? itemContent : resultsContent;
    const inside = content?.offsetHeight ?? 0;
    // (the transition of the height needs a number: `auto` cannot be animated in every browser)
    const next = inside > 0 ? Math.min(inside + PANE_PADDING, window.innerHeight * 0.72) : EMPTY_HEIGHT;
    // (not down to the size of the spinner, and up again when the item comes)
    if (next < applied && content?.querySelector("[data-quick-search-loading]")) return;
    applied = next;
    setHeight(next);
  };
  createEffect(showing, measure);

  const follow = (item: Picked) => {
    props.onNavigate(hrefOf(item));
    props.onClose();
  };
  const pick = (item: Picked, command: boolean) => {
    if (command) return follow(item);
    shown = item;
    setPicked(item);
    show("item");
  };

  const keyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      // (the types on offer are closed first, by the box)
      if (panel?.querySelector("#search-type-options")) return;
      event.preventDefault();
      event.stopPropagation();
      if (view === "item") show("results");
      else props.onClose();
    } else if (view === "item" && event.key === "Enter") {
      // (the box would take it for a result on the list that has gone)
      event.preventDefault();
      event.stopPropagation();
      if ((event.metaKey || event.ctrlKey) && shown) follow(shown);
    } else if (view === "item" && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      event.stopPropagation();
      itemPane?.scrollBy({ top: event.key === "ArrowDown" ? 80 : -80 });
    }
  };
  // (a link in the panel goes to another page, so the panel goes; Cmd and the like leave this page where it is)
  const clicked = (event: MouseEvent) => {
    const link = (event.target as Element).closest("a");
    if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey) props.onClose();
  };

  onSettled(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panes = new ResizeObserver(measure);
    if (resultsContent) panes.observe(resultsContent);
    if (itemContent) panes.observe(itemContent);
    return () => {
      panes.disconnect();
      document.body.style.overflow = overflow;
      opener?.focus?.({ preventScroll: true });
    };
  });

  const focusBox = () => panel?.querySelector("input")?.focus();
  const arrange = (results: () => JSX.Element) => (
    <div
      class="-mx-3 -mt-4 -mb-3 overflow-hidden transition-[height] duration-300 ease-out motion-reduce:transition-none"
      style={{ height: `${height()}px` }}
    >
      <div
        class={[
          "flex h-full items-stretch transition-transform duration-300 ease-out motion-reduce:transition-none",
          { "-translate-x-[min(40rem,calc(100vw-2rem))]": isItem() },
        ]}
      >
        <div
          data-testid="quick-search-results"
          inert={isItem()}
          class="h-full w-[min(40rem,calc(100vw-2rem))] shrink-0 overflow-y-auto px-3 pt-4 pb-3"
        >
          <div ref={resultsContent}>{results()}</div>
        </div>
        <div
          ref={itemPane}
          data-testid="quick-search-item"
          inert={!isItem()}
          class="h-full w-[min(64rem,calc(100vw-2rem))] shrink-0 overflow-y-auto px-3 pt-4 pb-3"
        >
          <div ref={itemContent}>
            <For each={picked() ? [picked()!] : []} keyed={(item) => item.id}>
              {(item) => (
                <>
                  <div class="mb-4 flex items-center gap-3">
                    <button
                      type="button"
                      data-testid="quick-search-back"
                      class={buttonClass("ordinary")}
                      onClick={() => {
                        show("results");
                        focusBox();
                      }}
                    >
                      {t("quick_search_results", "Results")}
                    </button>
                    <ReferenceChip type={item().type} label={item().label} href={hrefOf(item())} />
                  </div>
                  <PickedItem item={item()} />
                </>
              )}
            </For>
          </div>
        </div>
      </div>
    </div>
  );

  // (the keyboard stays in the panel: these are the two ends of it)
  const wrap = (toLast: boolean) => {
    const focusable = [...(panel?.querySelectorAll<HTMLElement>("input, button, a[href]") ?? [])].filter(
      (element) => element.offsetParent !== null && !element.closest("[inert]"),
    );
    (toLast ? focusable[focusable.length - 1] : focusable[0])?.focus();
  };

  return (
    <Portal>
      <div
        class="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 pt-[10vh] backdrop-blur-[1px]"
        onClick={(event) => {
          if (event.target === event.currentTarget) props.onClose();
        }}
      >
        <div
          ref={(element) => {
            panel = element;
            element.addEventListener("keydown", keyDown, true);
            element.addEventListener("click", clicked);
          }}
          role="dialog"
          aria-modal="true"
          aria-label={t("search_everything", "Quick search")}
          data-testid="quick-search"
          class={[
            "overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100 p-3 shadow-lg transition-[width] duration-300 ease-out motion-reduce:transition-none",
            {
              "w-[min(40rem,calc(100vw-2rem))]": !isItem(),
              "w-[min(64rem,calc(100vw-2rem))]": isItem(),
            },
          ]}
        >
          <span tabindex="0" onFocus={() => wrap(true)} />
          <GlobalSearch
            limit={12}
            onPick={pick}
            onTyped={() => {
              if (view === "item") show("results");
            }}
            arrange={arrange}
          />
          <span tabindex="0" onFocus={() => wrap(false)} />
        </div>
      </div>
    </Portal>
  );
}
