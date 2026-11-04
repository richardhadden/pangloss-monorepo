import { useTranslations } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { createEffect, createMemo, createSignal, For, onSettled, Show } from "solid-js";
import { STATUSES } from "../api";
import type { ReviewStatus } from "../api";
import type { Part } from "../parts";
import { visibleComments } from "../state";
import type { ReviewView, ShownComment } from "../state";
import { CommentText } from "./CommentText";
import { Composer } from "./Composer";
import { StatusFlag } from "./StatusFlag";

export interface ReviewPanelProps {
  review: ReviewView;
  /** The reader's username: their comments are on the right */
  me?: string;
  open: boolean;
  onClose: () => void;
  onStatus: (status: ReviewStatus) => void;
  /** Sends a comment (references to parts are `#<id>` in its text); rejects if it was not made (the text is put back) */
  onComment: (text: string) => Promise<unknown>;
  /** The parts of the document a comment can refer to (undefined until they have been read) */
  parts?: Part[];
  /** Asks for the parts, when the list of them is first opened */
  onWantParts?: () => void;
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
function CommentBubble(props: {
  comment: ShownComment;
  mine: boolean;
  onResolve: (id: string) => void;
  parts?: Part[];
}) {
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
            "rounded-br-xs bg-sky-600 text-white": props.mine,
            "rounded-bl-xs border-[0.5px] border-slate-400/70 bg-white text-slate-800": !props.mine,
            "opacity-50": props.comment.resolved || props.comment.pending,
          },
        ]}
      >
        <CommentText
          text={props.comment.text}
          parts={props.parts}
          targetId={props.comment.targetId}
          targetLabel={props.comment.targetLabel}
        />
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
  const shown = createMemo(() => visibleComments(props.review.comments, showResolved()));
  const resolvedCount = () => props.review.comments.filter((c) => c.resolved).length;
  let list: HTMLOListElement | undefined;

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
      // (not an Escape that something in the panel has used: the list of parts)
      if (event.key === "Escape" && props.open && !event.defaultPrevented) props.onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  return (
    <Portal>
      <aside
        aria-label={t("review_panel", "Review")}
        aria-hidden={props.open ? undefined : "true"}
        inert={!props.open}
        data-testid="review-panel"
        data-open={props.open ? "true" : "false"}
        class={[
          "fixed top-14 right-0 bottom-0 z-20 flex w-96 max-w-full flex-col rounded-tl-xs border-[0.5px] border-r-0 border-slate-400/70 bg-slate-100/95 text-slate-800 shadow-lg backdrop-blur-md transition-transform duration-200",
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
            class="flex size-8 cursor-pointer items-center justify-center rounded-xs hover:bg-slate-400/40"
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
          <p class="mb-2 text-xs font-semibold text-slate-700 uppercase" aria-hidden="true">
            {t("review_set_status", "Set review status")}
          </p>
          <div
            role="group"
            aria-label={t("review_status", "Status")}
            class="grid grid-cols-3 overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white text-xs font-semibold uppercase"
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
                parts={props.parts}
              />
            )}
          </For>
        </ol>

        {/* A new comment: Send, or Ctrl/Cmd+Enter; # refers to a part */}
        <Composer parts={props.parts} onWantParts={props.onWantParts} onSend={props.onComment} />
      </aside>
    </Portal>
  );
}
