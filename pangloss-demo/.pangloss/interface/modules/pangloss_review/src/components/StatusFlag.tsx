import type { ReviewStatus } from "../api";

// (whole class names, so that Tailwind finds them)
const TONES: Record<ReviewStatus, string> = {
  unchecked: "fill-none stroke-slate-600",
  errors_found: "fill-red-500 stroke-red-700",
  checked: "fill-green-500 stroke-green-700",
};

/** A flag for the review status: an outline for unchecked, red for errors found, green for checked */
export function StatusFlag(props: { status: ReviewStatus; class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none stroke-2", TONES[props.status], props.class ?? "size-4"]}
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      data-status={props.status}
    >
      <path d="M5 21V4" class="fill-none" />
      <path d="M5 4h12l-2.5 4.5L17 13H5z" />
    </svg>
  );
}
