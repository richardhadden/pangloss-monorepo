import { useTranslations } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { createEffect, createMemo, createSignal, For, onSettled, Show } from "solid-js";
import { STATUSES } from "../api";
import type { ReviewStatus } from "../api";
import { visibleComments } from "../state";
import type { ReviewView, ShownComment } from "../state";
import { StatusFlag } from "./StatusFlag";

export interface ReviewPanelProps {
  review: ReviewView;
  /** The reader's username: their comments are on the right */
  me?: string;
  open: boolean;
  onClose: () => void;
  onStatus: (status: ReviewStatus) => void;
  /** Sends a comment; rejects if it was not made (the text is put back) */
  onComment: (text: string) => Promise<unknown>;
  onResolve: (commentId: string) => void;
}

// (whole class names, so that Tailwind finds them)
const STATUS_TONES: Record<ReviewStatus, string> = {
  unchecked: "aria-pressed:bg-slate-600 aria-pressed:text-white",
  errors_found: "aria-pressed:bg-red-600 aria-pressed:text-white",
  checked: "aria-pressed:bg-green-600 aria-pressed:text-white",
};

export const statusSlot = (status: ReviewStatus) => `review_status_${status}`;
export const STATUS_WORDS: Record<ReviewStatus, string> = {
  unchecked: "Unchecked",
  errors_found: "Errors found",
  checked: "Checked",
};

function when(value: string | null | undefined, language: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(language, { dateStyle: "medium", timeStyle: "short" });
}

/** One comment, as a bubble: the reader's own on the right, others' on the left */
function CommentBubble(props: { comment: ShownComment; mine: boolean; onResolve: (id: string) => void }) {
  const { t, language } = useTranslations();
  return (
    <li
      class={[
        "flex max-w-[85%] flex-col gap-1",
        { "self-end items-end": props.mine, "self-start items-start": !props.mine },
      ]}
      data-testid="review-comment"
      data-mine={props.mine ? "true" : "false"}
      data-resolved={props.comment.resolved ? "true" : "false"}
    >
      <div class="flex items-baseline gap-2 px-1 text-[0.65rem] text-slate-500">
        <span class="font-semibold uppercase">
          <Show when={props.mine} fallback={props.comment.username}>
            {t("review_you", "You")}
          </Show>
        </span>
        <span>
          <Show when={props.comment.pending} fallback={when(props.comment.at, language())}>
            {t("review_sending", "Sending…")}
          </Show>
        </span>
      </div>
      <div
        class={[
          "rounded-lg px-3 py-2 text-sm whitespace-pre-wrap break-words",
          {
            "rounded-br-sm bg-sky-600 text-white": props.mine,
            "rounded-bl-sm border-[0.5px] border-slate-400/70 bg-white text-slate-800": !props.mine,
            "opacity-50": props.comment.resolved || props.comment.pending,
          },
        ]}
      >
        <Show when={props.comment.targetLabel}>
          {(part) => (
            <span
              class={[
                "mb-1 block text-[0.65rem] font-semibold uppercase",
                { "text-sky-100": props.mine, "text-slate-500": !props.mine },
              ]}
            >
              {t("review_about", "About: {part}", { part: part() })}
            </span>
          )}
        </Show>
        {props.comment.text}
      </div>
      <div class="px-1 text-[0.65rem] text-slate-500">
        <Show
          when={props.comment.resolved}
          fallback={
            <Show when={!props.comment.pending}>
              <button
                type="button"
                class="cursor-pointer font-semibold uppercase hover:text-slate-800"
                onClick={() => props.onResolve(props.comment.id)}
              >
                {t("review_resolve", "Resolve")}
              </button>
            </Show>
          }
        >
          <span>
            {t("review_resolved_by", "Resolved by {user}", { user: props.comment.resolvedBy ?? "" })}
          </span>
        </Show>
      </div>
    </li>
  );
}

/**
 * The review of a document, in a panel that slides out from the right (below the console bar): the status at the
 * top (three buttons), the comments as a conversation, and a box to write one. It is always in the page, off to
 * the right and inert while it is closed, so that it slides.
 */
export function ReviewPanel(props: ReviewPanelProps) {
  const { t, language } = useTranslations();
  const [showResolved, setShowResolved] = createSignal(false);
  const [draft, setDraft] = createSignal("");
  const shown = createMemo(() => visibleComments(props.review.comments, showResolved()));
  const resolvedCount = () => props.review.comments.filter((c) => c.resolved).length;
  let list: HTMLOListElement | undefined;
  let box: HTMLTextAreaElement | undefined;

  // (the newest comment in view as one arrives, or as the panel opens)
  createEffect(
    () => [shown().length, props.open] as const,
    ([, open]) => {
      if (open && list) list.scrollTop = list.scrollHeight;
    },
  );

  // Escape closes it
  onSettled(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && props.open) props.onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function send() {
    // (the box itself: a key pressed at once after typing comes before the signal has the text)
    const text = (box?.value ?? draft()).trim();
    if (!text) return;
    setDraft("");
    props.onComment(text).catch(() => {
      // (put back what was written, unless something new has been)
      if (draft() === "") setDraft(text);
    });
    box?.focus();
  }

  return (
    <Portal>
      <aside
        aria-label={t("review_panel", "Review")}
        aria-hidden={props.open ? undefined : "true"}
        inert={!props.open}
        data-testid="review-panel"
        data-open={props.open ? "true" : "false"}
        class={[
          "fixed top-14 right-0 bottom-0 z-20 flex w-96 max-w-full flex-col rounded-tl-sm border-[0.5px] border-r-0 border-slate-400/70 bg-slate-100/95 text-slate-800 shadow-lg backdrop-blur-md transition-transform duration-200",
          { "translate-x-0": props.open, "translate-x-full": !props.open },
        ]}
      >
        <header class="flex h-10 shrink-0 items-center justify-between border-b-[0.5px] border-slate-400/70 pr-1 pl-3 text-xs font-semibold text-slate-700 uppercase">
          <span class="flex items-center gap-2">
            <StatusFlag status={props.review.status} />
            {t("review_panel", "Review")}
          </span>
          <button
            type="button"
            class="flex size-8 cursor-pointer items-center justify-center rounded-sm hover:bg-slate-400/40"
            aria-label={t("review_close", "Close the review")}
            title={t("review_close", "Close the review")}
            onClick={() => props.onClose()}
          >
            <svg
              viewBox="0 0 24 24"
              class="size-4 select-none fill-none stroke-current stroke-2"
              stroke-linecap="round"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        {/* The status: the current one is pressed; another is a change at once (its own API, not the form's Save) */}
        <section class="shrink-0 border-b-[0.5px] border-slate-400/70 p-3">
          <div
            role="group"
            aria-label={t("review_status", "Status")}
            class="grid grid-cols-3 overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-white text-xs font-semibold uppercase"
          >
            <For each={STATUSES}>
              {(status) => (
                <button
                  type="button"
                  aria-pressed={props.review.status === status ? "true" : "false"}
                  class={[
                    "flex cursor-pointer items-center justify-center gap-1.5 border-l-[0.5px] border-slate-400/70 px-2 py-2 select-none first:border-l-0 hover:bg-slate-200",
                    STATUS_TONES[status],
                  ]}
                  onClick={() => {
                    if (props.review.status !== status) props.onStatus(status);
                  }}
                >
                  {t(statusSlot(status), STATUS_WORDS[status])}
                </button>
              )}
            </For>
          </div>
          <Show when={props.review.reviewedBy}>
            {(user) => (
              <p class="mt-2 text-[0.65rem] text-slate-500" data-testid="review-reviewed-by">
                {t("review_reviewed_by", "Reviewed by {user}, {when}", {
                  user: user(),
                  when: when(props.review.reviewedAt, language()),
                })}
              </p>
            )}
          </Show>
        </section>

        {/* The comments, oldest first */}
        <div class="flex shrink-0 items-center justify-between px-3 pt-3 text-xs font-semibold text-slate-700 uppercase">
          <span>{t("review_comments", "Comments")}</span>
          <Show when={resolvedCount() > 0}>
            <label class="flex cursor-pointer items-center gap-1.5 font-normal normal-case select-none">
              <input
                type="checkbox"
                checked={showResolved()}
                onChange={(event) => setShowResolved(event.currentTarget.checked)}
              />
              {t("review_show_resolved", "Show resolved ({count})", { count: String(resolvedCount()) })}
            </label>
          </Show>
        </div>
        <ol
          ref={list}
          class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3"
          aria-label={t("review_comments", "Comments")}
          aria-live="polite"
        >
          <For
            each={shown()}
            fallback={
              <li class="my-auto text-center text-sm text-slate-500">
                {t("review_no_comments", "No comments")}
              </li>
            }
          >
            {(comment) => (
              <CommentBubble
                comment={comment}
                mine={props.me !== undefined && comment.username === props.me}
                onResolve={props.onResolve}
              />
            )}
          </For>
        </ol>

        {/* A new comment: Send, or Ctrl/Cmd+Enter */}
        <form
          class="flex shrink-0 flex-col gap-2 border-t-[0.5px] border-slate-400/70 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <textarea
            ref={box}
            rows={3}
            value={draft()}
            onInput={(event) => setDraft(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                send();
              }
            }}
            aria-label={t("review_comment_label", "Comment")}
            placeholder={t("review_comment_placeholder", "Write a comment")}
            class="w-full resize-none rounded-sm border-[0.5px] border-slate-400/70 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={draft().trim() === ""}
            class="self-end rounded-sm bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white uppercase select-none hover:bg-sky-700 disabled:cursor-default disabled:opacity-40 enabled:cursor-pointer"
          >
            {t("review_send", "Send")}
          </button>
        </form>
      </aside>
    </Portal>
  );
}
