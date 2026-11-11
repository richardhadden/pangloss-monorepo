import {
  ApiError,
  ConsoleButton,
  getItem,
  useApi,
  useCurrentUser,
  useModels,
  useSidePanel,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import { whileVisible } from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createMemo, createSignal, onSettled, Show, untrack } from "solid-js";
import { reviewFeed } from "../feed";
import { partsOf, referencedIds, showPart, tasksOf } from "../parts";
import type { DocumentTasks, Part } from "../parts";
import { createReview } from "../state";
import { ReviewPanel } from "./ReviewPanel";
import { STATUS_WORDS, StatusFlag, statusSlot } from "./StatusFlag";

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
    feed: (signal) => whileVisible((connection) => invoke(reviewFeed, { signal: connection }, id), signal),
    api,
    me: () => props.me,
  });
  // (one panel on the right at a time: opening this closes history's, and the other way round)
  const { open, setOpen } = useSidePanel("review");
  // The document as it is saved, read once the button is on the page: its parts (what a comment can be about, and
  // which parts that comments are about are no longer there), and the tasks in it, which the button counts and the
  // panel lists
  const [parts, setParts] = createSignal<Part[]>();
  const [tasks, setTasks] = createSignal<DocumentTasks>({ mentions: [], suggestions: [] });
  let partsAsked = false;
  const wantParts = () => {
    if (partsAsked) return;
    partsAsked = true;
    getItem(api, untrack(() => props.type), id)
      .then((item) => {
        setParts(partsOf(item as Record<string, unknown>, definitions));
        setTasks(tasksOf(item as Record<string, unknown>, definitions));
      })
      .catch(() => setParts([]));
  };
  // (in the browser, after the page is drawn: nothing is read while it is rendered)
  onSettled(wantParts);
  // What is outstanding: the open comments, and the tasks in the document (identifications a toolchain suggested,
  // not yet confirmed; mentions not yet reconciled)
  const outstanding = () => review.openComments + tasks().suggestions.length + tasks().mentions.length;
  // A part shown on the page; one that is not drawn (inside something folded) is asked for in the address, and the
  // page read again there: it unfolds what holds it and scrolls to it (`?show=`)
  const show = (partId: string) => {
    if (showPart(partId)) return;
    const address = new URL(window.location.href);
    address.searchParams.set("show", partId);
    window.location.assign(address);
  };
  const refused = (slot: string, words: string) => (error: unknown) => {
    console.error(error);
    toasts?.show(t(slot, words, { reason: reasonOf(error) }), "error");
  };
  const status = () => t(statusSlot(review.status), STATUS_WORDS[review.status]);
  const label = () =>
    outstanding() > review.openComments
      ? t(
          "review_button_outstanding",
          "Review: {status}; open comments: {comments}, identifications to confirm: {suggestions}, to reconcile: {mentions}",
          {
            status: status(),
            comments: String(review.openComments),
            suggestions: String(tasks().suggestions.length),
            mentions: String(tasks().mentions.length),
          },
        )
      : review.openComments > 0
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
          <Show when={outstanding() > 0}>
            <span
              class="absolute -top-1.5 -right-2.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[0.6rem] leading-none font-bold text-white"
              data-testid="review-count"
            >
              {outstanding()}
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
        mentions={tasks().mentions}
        onShowPart={show}
        onComment={(text) => {
          // (the API keeps one part a comment is about, with its label as it is now: the first it refers to)
          const first = referencedIds(text)[0];
          const sent = comment(text, parts()?.find((part) => part.id === first));
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
 * number of things outstanding (open comments, identifications a toolchain suggested, unreconciled mentions), which
 * opens the panel. Only for a document of a reviewed class, and someone logged in
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
