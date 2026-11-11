// (thin and sharp, as the icons of the interface are: square caps, mitred joins, `stroke-2` at this size)
const ICON = "size-3.5 shrink-0 select-none fill-none stroke-current stroke-2";

/** A spanner: reconcile an unreconciled mention */
export function SpannerIcon() {
  return (
    <svg viewBox="0 0 24 24" class={ICON} stroke-linecap="square" aria-hidden="true">
      <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-.5-.5-2.5z" />
    </svg>
  );
}

/** A tick: confirm */
export function TickIcon() {
  return (
    <svg viewBox="0 0 24 24" class={ICON} stroke-linecap="square" aria-hidden="true">
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

export const reasonOf = (error: unknown): string =>
  typeof error === "object" && error !== null && "detail" in error && typeof error.detail === "string"
    ? error.detail
    : error instanceof Error
      ? error.message
      : String(error);

/** Where an item's own page is */
export const hrefOf = (item: { type: string; id: string }) => `/${item.type}/${encodeURIComponent(item.id)}`;

