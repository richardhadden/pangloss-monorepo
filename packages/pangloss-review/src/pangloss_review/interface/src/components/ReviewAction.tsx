import {
  ApiError,
  ConsoleButton,
  getItem,
  useApi,
  useCurrentUser,
  useModels,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createMemo, createSignal, Show, untrack } from "solid-js";
import { reviewFeed } from "../feed";
import { partsOf } from "../parts";
import type { Part } from "../parts";
import { createReview } from "../state";
import { ReviewPanel, STATUS_WORDS, statusSlot } from "./ReviewPanel";
import { StatusFlag } from "./StatusFlag";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

/** The button and the panel of one document: one connection to the feed, read by both */
function Review(props: { type: string; id: string; me?: string }) {
  const api = useApi();
  const definitions = useModels();
  const toasts = useToasts();
  const { t } = useTranslations();
  const id = untrack(() => props.id);
  const { review, changeStatus, comment, resolve } = createReview({
    id,
    feed: (signal) => invoke(reviewFeed, { signal }, id),
    api,
    me: () => props.me,
  });
  const [open, setOpen] = createSignal(false);
  // The parts of the document, read (as saved) when the panel is first opened: what a comment can be about, and which
  // parts that comments are about are no longer there
  const [parts, setParts] = createSignal<Part[]>();
  let partsAsked = false;
  const wantParts = () => {
    if (partsAsked) return;
    partsAsked = true;
    getItem(api, untrack(() => props.type), id)
      .then((item) => setParts(partsOf(item as Record<string, unknown>, definitions)))
      .catch(() => setParts([]));
  };
  const refused = (slot: string, words: string) => (error: unknown) => {
    console.error(error);
    toasts?.show(t(slot, words, { reason: reasonOf(error) }), "error");
  };
  const status = () => t(statusSlot(review.status), STATUS_WORDS[review.status]);
  const label = () =>
    review.openComments > 0
      ? t("review_button_comments", "Review: {status}, open comments: {count}", {
          status: status(),
          count: String(review.openComments),
        })
      : t("review_button", "Review: {status}", { status: status() });
  return (
    // (nothing for a document that has no review, or until the feed has said)
    <Show when={review.state === "ready"}>
      <ConsoleButton
        label={label()}
        pressed={open()}
        onClick={() => {
          wantParts();
          setOpen((was) => !was);
        }}
      >
        <span class="relative flex" data-testid="review-button" data-status={review.status}>
          <StatusFlag status={review.status} class="size-5" />
          <Show when={review.openComments > 0}>
            <span
              class="absolute -top-1.5 -right-2.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[0.6rem] leading-none font-bold text-white"
              data-testid="review-count"
            >
              {review.openComments}
            </span>
          </Show>
        </span>
      </ConsoleButton>
      <ReviewPanel
        review={review}
        me={props.me}
        open={open()}
        onClose={() => setOpen(false)}
        onStatus={(next) => {
          changeStatus(next).catch(refused("review_status_refused", "The status was not changed: {reason}"));
        }}
        parts={parts()}
        onWantParts={wantParts}
        onComment={(text, part) => {
          const sent = comment(text, part);
          sent.catch(refused("review_comment_refused", "The comment was not sent: {reason}"));
          return sent;
        }}
        onResolve={(commentId) => {
          resolve(commentId).catch(refused("review_resolve_refused", "The comment was not resolved: {reason}"));
        }}
      />
    </Show>
  );
}

/**
 * The review button in the console of an item (a `consoleActions` entry): a flag coloured by the status, with the
 * number of open comments, which opens the panel. Only for a document of a reviewed class, and someone logged in
 * (the review API needs a login).
 */
export default function ReviewAction(props: ConsoleActionProps) {
  // (read here, where the session is in reach: a prop is read when it is used, which for the writes is in an action)
  const me = createMemo(() => useCurrentUser()?.username);
  return (
    <Show when={props.model.kind === "Document" && me() !== undefined}>
      <Show when={props.id} keyed>
        {(id) => <Review type={props.type} id={id} me={me()} />}
      </Show>
    </Show>
  );
}
