/** A small spinner, in the colour of the text around it, for something that is loading */
export function Spinner() {
  return (
    <svg
      role="status"
      aria-label="Loading"
      viewBox="0 0 24 24"
      class="size-3.5 animate-spin select-none fill-none stroke-current stroke-[3]"
      stroke-linecap="round"
    >
      <circle cx="12" cy="12" r="9" class="opacity-25" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}
