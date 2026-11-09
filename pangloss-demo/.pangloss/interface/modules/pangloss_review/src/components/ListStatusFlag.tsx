import { userIsLoggedIn, useTranslations } from "@pangloss/interface-core";
import type { ResultMarkProps } from "@pangloss/interface-core";
import { Show } from "solid-js";
import type { ReviewStatus } from "../api";
import { STATUS_WORDS, StatusFlag, statusSlot } from "./StatusFlag";

/** The status the list sends for an item: of a reviewed document, or of the one it is inside */
function statusOf(item: Record<string, unknown>): ReviewStatus | undefined {
  const status = (item.meta as { reviewStatus?: unknown } | null | undefined)?.reviewStatus;
  return typeof status === "string" && Object.hasOwn(STATUS_WORDS, status) ? (status as ReviewStatus) : undefined;
}

/**
 * The review status at the right of a row of a list (a `resultMarks` entry). Only for someone logged in, as the rest of
 * review is: a reader who is not logged in is only ever shown what is checked.
 */
export function ListStatusFlag(props: ResultMarkProps) {
  const { t } = useTranslations();
  const shown = () => (userIsLoggedIn() ? statusOf(props.item) : undefined);
  return (
    <Show when={shown()}>
      {(status) => (
        <span
          role="img"
          aria-label={t(statusSlot(status()), STATUS_WORDS[status()])}
          title={t(statusSlot(status()), STATUS_WORDS[status()])}
          data-testid="list-review-status"
          data-status={status()}
          class="mr-3 flex select-none"
        >
          <StatusFlag status={status()} />
        </span>
      )}
    </Show>
  );
}
