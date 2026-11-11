/** A time as it is said in the language of the page; what cannot be read is left as it came */
export { readableTime as when } from "@pangloss/interface-core";

// The colours of a change, the same in the panel, the drawer, the dialog and the page (whole class names, so that
// Tailwind finds them): green put in, red taken out, amber changed
export const CHANGE_TAG: Record<"added" | "removed" | "changed", string> = {
  added: "bg-green-100 text-green-800 ring-green-600/30",
  removed: "bg-red-100 text-red-800 ring-red-600/30",
  changed: "bg-amber-100 text-amber-900 ring-amber-600/30",
};
