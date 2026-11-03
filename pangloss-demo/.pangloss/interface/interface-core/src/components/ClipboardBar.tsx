import { createEffect, createSignal, For, onSettled, Show } from "solid-js";
import { useClipboard, useModels, useNavExpanded, useTranslations } from "../context";
import { getModel, outline } from "../schema";
import type { FormData } from "../schema";
import { ClipLabel, CutIcon, CopyIcon } from "./form/Clip";

/**
 * What has been cut or copied, fixed along the bottom of the page, inset as the console bar is
 * at the top, and glassy as it is. It slides in when there is something on the clipboard and the
 * page has a form (making an item, or changing one), and can
 * be folded to its head line. Each thing is a card: its type and label, and what is inside it, two
 * levels down (all of it when the bar is opened out). Pasting is done in a form, at the place
 * offered for it. While it is there the page has room at the bottom as tall as it is, so the end of
 * the form can be scrolled clear of it (and what is scrolled into view stops above it).
 */
export function ClipboardBar() {
  const clipboard = useClipboard();
  const { navPinned } = useNavExpanded();
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  const entries = () => clipboard?.entries() ?? [];
  // (only where something can be pasted: on a page with a form)
  const shown = () => entries().length > 0 && !!clipboard?.formShown();
  const collapsed = () => clipboard?.collapsed() ?? false;
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
  return (
    <aside
      ref={bar}
      aria-label={t("clipboard", "Clipboard")}
      aria-hidden={shown() ? undefined : "true"}
      class={[
        "fixed bottom-0 z-30 flex flex-col overflow-hidden rounded-t-sm border-[0.5px] border-b-0 border-slate-400/70 bg-slate-200/60 text-slate-700 backdrop-blur-md transition-[opacity,translate] duration-300",
        {
          "right-8 left-80": navPinned(),
          "right-20 left-32": !navPinned(),
          "translate-y-0 opacity-100": shown(),
          "pointer-events-none translate-y-full opacity-0": !shown(),
        },
      ]}
    >
      <div class={["flex h-8 items-stretch", { "border-b-[0.5px] border-slate-400/50": !collapsed() }]}>
        {/* (the whole head line folds it) */}
        <button
          type="button"
          class="flex flex-1 cursor-pointer items-center gap-2 px-3 text-xs font-semibold uppercase select-none hover:bg-slate-300/50"
          aria-expanded={collapsed() ? "false" : "true"}
          aria-label={t("clipboard_fold", "Fold or unfold the clipboard")}
          onClick={() => clipboard?.setCollapsed(!collapsed())}
        >
          <span aria-hidden="true">
            <Show when={collapsed()} fallback="▾">
              ▸
            </Show>
          </span>
          {t("clipboard_count", "Clipboard ({count})", { count: String(entries().length) })}
        </button>
        <Show when={!collapsed()}>
          <button
            type="button"
            class={barButton}
            aria-expanded={open() ? "true" : "false"}
            onClick={() => setOpen(!open())}
          >
            <Show when={open()} fallback={t("clipboard_more", "Show all")}>
              {t("clipboard_less", "Show less")}
            </Show>
          </button>
        </Show>
        <button type="button" class={[barButton, "text-red-800 hover:bg-red-400/30"]} onClick={() => clipboard?.clear()}>
          {t("clipboard_clear", "Clear")}
        </button>
      </div>
      <ul
        class={[
          "gap-2 overflow-auto p-2",
          { hidden: collapsed(), flex: !collapsed() },
          { "max-h-[50vh] flex-wrap": open(), "max-h-36": !open() },
        ]}
      >
        <For each={entries()}>
          {(entry) => (
            // (as tall as the row lets it be: what is inside it scrolls)
            <li class="flex min-h-0 w-72 shrink-0 flex-col gap-1 rounded-sm border-[0.5px] border-slate-400/70 bg-white/70 p-2">
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
                  class="shrink-0 cursor-pointer rounded-sm px-1.5 text-xs text-red-800 select-none hover:bg-red-400/30"
                  aria-label={t("clip_remove", "Take off the clipboard")}
                  title={t("clip_remove", "Take off the clipboard")}
                  onClick={() => clipboard?.remove(entry.key)}
                >
                  ✕
                </button>
              </div>
              <Outline value={entry.value} depth={open() ? Infinity : 2} />
            </li>
          )}
        </For>
      </ul>
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
