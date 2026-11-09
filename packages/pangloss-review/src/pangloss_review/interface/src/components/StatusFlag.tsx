import type { ReviewStatus } from "../api";

// (whole class names, so that Tailwind finds them)
const TONES: Record<ReviewStatus, string> = {
  unchecked: "fill-none stroke-slate-600",
  errors_found: "fill-red-500 stroke-red-700",
  checked: "fill-green-500 stroke-green-700",
};

// (the words of a status; here, not in the panel, because every list draws a flag and must not bring the panel's code)
export const statusSlot = (status: ReviewStatus) => `review_status_${status}`;
export const STATUS_WORDS: Record<ReviewStatus, string> = {
  unchecked: "Unchecked",
  errors_found: "Errors found",
  checked: "Checked",
};

/** A flag for the review status: an outline for unchecked, red for errors found, green for checked */
export function StatusFlag(props: { status: ReviewStatus; class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none stroke-[1.75]", TONES[props.status], props.class ?? "size-4"]}
      stroke-linecap="square"
      aria-hidden="true"
      data-status={props.status}
    >
      <path d="M5 21V4" class="fill-none" />
      <path d="M5 4h12l-2.5 4.5L17 13H5z" />
    </svg>
  );
}
