import { createEffect, createSignal, For, onSettled, Show } from "solid-js";
import { useClipboard, useModels, useNavExpanded, useStash, useTranslations } from "../context";
import { getModel, outline } from "../schema";
import type { FormData } from "../schema";
import { ClipLabel, CutIcon, CopyIcon, StashIcon } from "./form/Clip";

/**
 * Whether the bar at the bottom is showing, and whether it is folded to its head line: for the page, which leaves room
 * for it
 */
export function useBottomBar() {
  const clipboard = useClipboard();
  const stash = useStash();
  const definitions = useModels();
  const clipShown = () => (clipboard?.entries().length ?? 0) > 0 && !!clipboard?.formShown();
  // (what is stashed of the types the page is about, or of their subtypes)
  const stashed = () => {
    const types = new Set(
      (stash?.shownTypes() ?? []).flatMap((type) => [type, ...(getModel(definitions, type)?.concreteTypes ?? [])]),
    );
    return (stash?.entries() ?? []).filter((entry) => types.has(entry.type));
  };
  return {
    clipShown,
    stashed,
    shown: () => clipShown() || stashed().length > 0,
    collapsed: () => clipboard?.collapsed() ?? false,
  };
}

/**
 * Fixed along the bottom of the page, inset as the console bar is at the top, and glassy as it is: what has been cut
 * or copied, and what is stashed, side by side, each a section of the same height. It slides in when there is
 * something to show: the clipboard on a page with a form (making an item, or changing one), the stashed items on a
 * page about their type (its list, or the form for a new one: `Stash.showFor`). The arrow at the left folds it to its
 * head line; clicking the name of a section shows all of it (it takes most of the width, and is taller), and the other
 * stays beside it. Each thing is a card: its type and label, and what is inside it, two levels down (all of it when
 * its section is opened out). Pasting is done in a form, at the place offered for it; a stashed item is opened by
 * its label, on the form of a new one. While it is there the page has room at the bottom as tall as it is, so the end
 * of the form can be scrolled clear of it (and what is scrolled into view stops above it).
 */
export function ClipboardBar() {
  const clipboard = useClipboard();
  const stash = useStash();
  const bar$ = useBottomBar();
  const { navPinned } = useNavExpanded();
  const { t } = useTranslations();
  // (the section shown in full, if one is)
  const [open, setOpen] = createSignal<"clipboard" | "stash">();
  const entries = () => clipboard?.entries() ?? [];
  const shown = bar$.shown;
  const collapsed = bar$.collapsed;
  const both = () => bar$.clipShown() && bar$.stashed().length > 0;
  const toggle = (section: "clipboard" | "stash") => {
    if (collapsed()) {
      clipboard?.setCollapsed(false);
      setOpen(section);
    } else setOpen(open() === section ? undefined : section);
  };
  // (how tall it is, followed as it folds, opens out and has more or fewer things)
  const [height, setHeight] = createSignal(0);
  let bar: HTMLElement | undefined;
  onSettled(() => {
    if (!bar || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeight(bar!.offsetHeight));
    observer.observe(bar);
    return () => observer.disconnect();
  });
  createEffect(
    () => (shown() ? height() : 0),
    (tall) => {
      // (with a little more, so the last thing is not flush against it)
      const room = tall > 0 ? `${tall + 16}px` : "";
      document.body.style.paddingBottom = room;
      document.documentElement.style.scrollPaddingBottom = room;
      return () => {
        document.body.style.paddingBottom = "";
        document.documentElement.style.scrollPaddingBottom = "";
      };
    },
  );
  const barButton =
    "flex cursor-pointer items-center px-3 text-xs font-semibold uppercase select-none hover:bg-slate-300/50";
  const sectionClass = (section: "clipboard" | "stash") => [
    "flex min-w-0 flex-col",
    {
      "flex-[3]": both() && open() === section,
      "flex-1": !both() || open() !== section,
    },
  ];
  const headClass = () => ["flex h-8 items-stretch", { "border-b-[0.5px] border-slate-400/50": !collapsed() }];
  const listClass = (section: "clipboard" | "stash") => [
    "gap-2 overflow-auto p-2",
    { hidden: collapsed(), flex: !collapsed() },
    { "max-h-[50vh] flex-wrap": open() === section, "max-h-36": open() !== section },
  ];
  return (
    <aside
      ref={bar}
      aria-label={t("bottom_bar", "Clipboard and stash")}
      aria-hidden={shown() ? undefined : "true"}
      class={[
        "fixed bottom-0 z-30 flex overflow-hidden rounded-t-xs border-[0.5px] border-b-0 border-slate-400/70 bg-slate-200/60 text-slate-700 backdrop-blur-md transition-[opacity,translate] duration-300",
        {
          "right-8 left-80": navPinned(),
          "right-20 left-32": !navPinned(),
          "translate-y-0 opacity-100": shown(),
          "pointer-events-none translate-y-full opacity-0": !shown(),
        },
      ]}
    >
      {/* (folds the whole bar to its head line) */}
      <div class="flex shrink-0 flex-col border-r-[0.5px] border-slate-400/50">
        <button
          type="button"
          class="flex h-8 w-8 cursor-pointer items-center justify-center text-xs select-none hover:bg-slate-300/50"
          aria-expanded={collapsed() ? "false" : "true"}
          aria-label={t("clipboard_fold", "Fold or unfold the clipboard")}
          title={t("clipboard_fold", "Fold or unfold the clipboard")}
          onClick={() => clipboard?.setCollapsed(!collapsed())}
        >
          <span aria-hidden="true">
            <Show when={collapsed()} fallback="▾">
              ▸
            </Show>
          </span>
        </button>
      </div>
      <Show when={bar$.clipShown()}>
        <section aria-label={t("clipboard", "Clipboard")} class={sectionClass("clipboard")}>
          <div class={headClass()}>
            <button
              type="button"
              class="flex flex-1 cursor-pointer items-center gap-2 px-3 text-xs font-semibold uppercase select-none hover:bg-slate-300/50"
              aria-expanded={open() === "clipboard" ? "true" : "false"}
              title={t("clipboard_more", "Show all")}
              onClick={() => toggle("clipboard")}
            >
              {t("clipboard_count", "Clipboard ({count})", { count: String(entries().length) })}
            </button>
            <button type="button" class={[barButton, "text-red-800 hover:bg-red-400/30"]} onClick={() => clipboard?.clear()}>
              {t("clipboard_clear", "Clear")}
            </button>
          </div>
          <ul class={listClass("clipboard")}>
            <For each={entries()}>
              {(entry) => (
                // (as tall as the row lets it be: what is inside it scrolls)
                <li class="flex min-h-0 w-72 shrink-0 flex-col gap-1 rounded-xs border-[0.5px] border-slate-400/70 bg-white/70 p-2">
                  <div class="flex min-w-0 shrink-0 items-center gap-1">
                    <span
                      class="shrink-0 text-slate-500"
                      title={entry.cut ? t("clip_cut", "Cut") : t("clip_copied", "Copied")}
                    >
                      <Show when={entry.cut} fallback={<CopyIcon />}>
                        <CutIcon />
                      </Show>
                    </span>
                    <ClipLabel value={entry.value} class="flex-1" />
                    <button
                      type="button"
                      class="shrink-0 cursor-pointer rounded-xs px-1.5 text-xs text-red-800 select-none hover:bg-red-400/30"
                      aria-label={t("clip_remove", "Take off the clipboard")}
                      title={t("clip_remove", "Take off the clipboard")}
                      onClick={() => clipboard?.remove(entry.key)}
                    >
                      ✕
                    </button>
                  </div>
                  <Outline value={entry.value} depth={open() === "clipboard" ? Infinity : 2} />
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
      <Show when={bar$.stashed().length > 0}>
        <section
          aria-label={t("stashed", "Stashed")}
          class={[sectionClass("stash"), { "border-l-[0.5px] border-slate-400/50": bar$.clipShown() }]}
        >
          <div class={headClass()}>
            <button
              type="button"
              class="flex flex-1 cursor-pointer items-center gap-2 px-3 text-xs font-semibold uppercase select-none hover:bg-slate-300/50"
              aria-expanded={open() === "stash" ? "true" : "false"}
              title={t("clipboard_more", "Show all")}
              onClick={() => toggle("stash")}
            >
              {t("stashed_count", "Stashed ({count})", { count: String(bar$.stashed().length) })}
            </button>
          </div>
          <ul class={listClass("stash")}>
            <For each={bar$.stashed()}>
              {(entry) => (
                <li
                  class={[
                    "flex min-h-0 w-72 shrink-0 flex-col gap-1 rounded-xs border-[0.5px] p-2",
                    {
                      "border-slate-400/70 bg-white/70": stash?.openKey() !== entry.key,
                      "border-green-700/60 bg-green-50/80": stash?.openKey() === entry.key,
                    },
                  ]}
                >
                  <div class="flex min-w-0 shrink-0 items-center gap-1">
                    <span class="shrink-0 text-slate-500" title={t("stashed", "Stashed")}>
                      <StashIcon />
                    </span>
                    <Show
                      when={stash?.openKey() !== entry.key}
                      fallback={
                        <span class="flex min-w-0 flex-1 items-center gap-1" title={t("stash_open_here", "Open in this form")}>
                          <ClipLabel value={entry.value} class="min-w-0" />
                        </span>
                      }
                    >
                      <a
                        href={`/${encodeURIComponent(entry.type)}/new?stash=${encodeURIComponent(entry.key)}`}
                        class="flex min-w-0 flex-1 hover:underline"
                        aria-label={t("stash_open", "Go on with {label}", { label: entry.label })}
                        title={t("stash_open", "Go on with {label}", { label: entry.label })}
                      >
                        <ClipLabel value={entry.value} class="min-w-0" />
                      </a>
                    </Show>
                    <button
                      type="button"
                      class="shrink-0 cursor-pointer rounded-xs px-1.5 text-xs text-red-800 select-none hover:bg-red-400/30"
                      aria-label={t("stash_remove", "Throw away {label}", { label: entry.label })}
                      title={t("stash_remove", "Throw away {label}", { label: entry.label })}
                      onClick={() => stash?.remove(entry.key)}
                    >
                      ✕
                    </button>
                  </div>
                  <span class="shrink-0 text-[0.65rem] text-slate-500">{new Date(entry.when).toLocaleString()}</span>
                  <Outline value={entry.value} depth={open() === "stash" ? Infinity : 2} />
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
    </aside>
  );
}

/**
 * What is inside something on the clipboard, a line for each thing, indented under what it is in:
 * an entity or a document as a chip, as the card's own head is; the rest (a reified relation, a
 * conjunction, an embedded model) by the name of its type. Scrolls when it is taller than the card.
 */
function Outline(props: { value: FormData; depth: number }) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  // (the top is the card's own head)
  const lines = () => outline(definitions, props.value, props.depth).slice(1);
  const chipped = (type: string) => {
    const kind = getModel(definitions, type)?.kind;
    return kind === "Entity" || kind === "Document" || kind === "ReifiedRelationDocument";
  };
  return (
    <Show when={lines().length > 0}>
      <ul class="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto text-xs text-slate-600">
        <For each={lines()}>
          {(line) => (
            <li
              class="flex min-w-0 shrink-0 items-center gap-1 whitespace-nowrap"
              style={{ "padding-left": `${(line.depth - 1) * 0.75}rem` }}
            >
              <span class="shrink-0 text-slate-400">{line.field} · </span>
              <Show
                when={chipped(line.type)}
                fallback={
                  <span class="min-w-0 truncate">
                    <span class="font-semibold uppercase">{modelName(line.type)}</span>
                    <Show when={line.label}>
                      <span> {line.label}</span>
                    </Show>
                  </span>
                }
              >
                <ClipLabel value={{ type: line.type, label: line.label }} />
              </Show>
            </li>
          )}
        </For>
      </ul>
    </Show>
  );
}
