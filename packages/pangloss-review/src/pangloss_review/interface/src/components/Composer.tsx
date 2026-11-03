import { useTranslations } from "@pangloss/interface-core";
import { createMemo, createSignal, For, Show } from "solid-js";
import { matchParts, mentionAt, shorten, showPart, withoutMention } from "../parts";
import type { Part } from "../parts";

export interface ComposerProps {
  /** The parts of the document a comment can be about; undefined while they are being read */
  parts?: Part[];
  /** Asks for the parts (the first time the list is opened) */
  onWantParts?: () => void;
  /** Sends a comment, about a part or not; rejects if it was not made (what was written is put back) */
  onSend: (text: string, part?: Part) => Promise<unknown>;
}

// (the list of parts: open while a `#` before the caret, at `start`, is being typed)
interface Mention {
  start: number;
  query: string;
}

/**
 * The box to write a comment. Typing `#` (at the start, or after a space) opens a list of the parts of the document
 * (type and label, shortened), filtered by what is typed after it; ↑/↓ and Enter or Tab (or a click) choose one, which
 * takes the `#word` out of the text and becomes the chip "About: …" over the box (a comment is about one part: another
 * replaces it). The button beside Send opens the same list. Send, or Ctrl/Cmd+Enter, sends.
 */
export function Composer(props: ComposerProps) {
  const { t, modelName } = useTranslations();
  const [draft, setDraft] = createSignal("");
  const [part, setPart] = createSignal<Part>();
  const [mention, setMention] = createSignal<Mention>();
  const [active, setActive] = createSignal(0);
  let box: HTMLTextAreaElement | undefined;
  const choices = createMemo(() => {
    const open = mention();
    return open ? matchParts(props.parts ?? [], open.query, (type) => modelName(type)) : [];
  });
  const partName = (p: Part) => `${modelName(p.type)} · ${shorten(p.label ?? p.id)}`;

  function follow() {
    if (!box) return;
    const found = mentionAt(box.value, box.selectionStart ?? box.value.length);
    if (found) props.onWantParts?.();
    // (words after the `#` keep the list open while a part matches them; once none does after a space, the text has
    // moved on, and it closes)
    const moved =
      found !== undefined &&
      props.parts !== undefined &&
      /\s/.test(found.query) &&
      matchParts(props.parts, found.query, (type) => modelName(type)).length === 0;
    setMention(moved ? undefined : found);
    setActive(0);
  }

  function choose(chosen: Part) {
    const open = mention();
    if (box && open) {
      const { text, caret } = withoutMention(box.value, box.selectionStart ?? box.value.length, open.start);
      box.value = text;
      setDraft(text);
      box.setSelectionRange(caret, caret);
    }
    setPart(chosen);
    setMention(undefined);
    showPart(chosen.id);
    box?.focus();
  }

  function send() {
    // (the box itself: a key pressed at once after typing comes before the signal has the text)
    const text = (box?.value ?? draft()).trim();
    if (!text) return;
    const about = part();
    setDraft("");
    if (box) box.value = "";
    setPart(undefined);
    setMention(undefined);
    props.onSend(text, about).catch(() => {
      // (put back what was written, unless something new has been)
      if (draft() === "") {
        setDraft(text);
        if (box) box.value = text;
        setPart(about);
      }
    });
    box?.focus();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (mention()) {
      const count = choices().length;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (count) setActive((i) => (i + (event.key === "ArrowDown" ? 1 : count - 1)) % count);
        return;
      }
      if ((event.key === "Enter" || event.key === "Tab") && !event.metaKey && !event.ctrlKey) {
        const chosen = choices()[active()];
        if (chosen) {
          event.preventDefault();
          choose(chosen);
          return;
        }
      }
      if (event.key === "Escape") {
        // (closes the list, not the panel)
        event.preventDefault();
        setMention(undefined);
        return;
      }
    }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      send();
    }
  }

  return (
    <form
      class="relative flex shrink-0 flex-col gap-2 border-t-[0.5px] border-slate-400/70 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      {/* The parts to choose from, over the box */}
      <Show when={mention()}>
        <ul
          id="review-parts"
          role="listbox"
          aria-label={t("review_parts", "Parts of the document")}
          class="absolute right-3 bottom-full left-3 z-10 mb-1 max-h-64 overflow-y-auto rounded-sm border-[0.5px] border-slate-400/70 bg-white py-1 text-sm shadow-lg"
        >
          <For
            each={choices()}
            fallback={
              <li class="px-3 py-1.5 text-slate-500">
                <Show when={props.parts} fallback={t("loading", "Loading…")}>
                  {t("review_part_none", "No parts match")}
                </Show>
              </li>
            }
          >
            {(choice, index) => (
              <li
                id={`review-part-${choice.id}`}
                role="option"
                aria-selected={index() === active() ? "true" : "false"}
                class={[
                  "flex cursor-pointer items-baseline gap-2 px-3 py-1.5",
                  { "bg-sky-100": index() === active() },
                ]}
                // (not a blur of the box before the click)
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(index())}
                onClick={() => choose(choice)}
              >
                <span class="shrink-0 text-[0.65rem] font-semibold text-slate-500 uppercase">
                  {modelName(choice.type)}
                </span>
                <span class="truncate">{shorten(choice.label ?? choice.id)}</span>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <Show when={part()}>
        {(about) => (
          <span
            class="flex items-center gap-1 self-start rounded-sm bg-slate-200 py-0.5 pr-0.5 pl-2 text-xs text-slate-700"
            data-testid="review-about"
          >
            {t("review_about", "About: {part}", { part: partName(about()) })}
            <button
              type="button"
              class="flex size-5 cursor-pointer items-center justify-center rounded-sm hover:bg-slate-300"
              aria-label={t("review_part_clear", "Not about a part")}
              title={t("review_part_clear", "Not about a part")}
              onClick={() => setPart(undefined)}
            >
              <svg
                viewBox="0 0 24 24"
                class="size-3 select-none fill-none stroke-current stroke-2"
                stroke-linecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </span>
        )}
      </Show>
      <textarea
        ref={box}
        rows={3}
        value={draft()}
        role="combobox"
        aria-expanded={mention() ? "true" : "false"}
        aria-controls="review-parts"
        aria-autocomplete="list"
        aria-activedescendant={choices()[active()] ? `review-part-${choices()[active()]!.id}` : undefined}
        onInput={(event) => {
          setDraft(event.currentTarget.value);
          follow();
        }}
        onClick={follow}
        onBlur={() => setMention(undefined)}
        onKeyDown={onKeyDown}
        aria-label={t("review_comment_label", "Comment")}
        placeholder={t("review_comment_placeholder", "Write a comment (# for a part)")}
        class="w-full resize-none rounded-sm border-[0.5px] border-slate-400/70 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
      />
      <div class="flex items-center justify-between">
        <button
          type="button"
          class="flex h-7 cursor-pointer items-center gap-1 rounded-sm px-2 text-xs font-semibold text-slate-600 uppercase select-none hover:bg-slate-200"
          title={t("review_part_choose", "About a part…")}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            // (a `#` where the caret is, as if typed, so what is typed next filters the list)
            if (!box) return;
            const at = box.selectionStart ?? box.value.length;
            const before = box.value.slice(0, at);
            const hash = before === "" || /\s$/.test(before) ? "#" : " #";
            box.value = before + hash + box.value.slice(at);
            setDraft(box.value);
            box.focus();
            box.setSelectionRange(at + hash.length, at + hash.length);
            follow();
          }}
        >
          <span aria-hidden="true">#</span>
          {t("review_part_choose", "About a part…")}
        </button>
        <button
          type="submit"
          disabled={draft().trim() === ""}
          class="rounded-sm bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white uppercase select-none hover:bg-sky-700 disabled:cursor-default disabled:opacity-40 enabled:cursor-pointer"
        >
          {t("review_send", "Send")}
        </button>
      </div>
    </form>
  );
}
