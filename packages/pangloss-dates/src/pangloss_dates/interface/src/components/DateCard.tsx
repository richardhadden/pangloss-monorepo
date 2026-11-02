import type { ViewCardProps } from "@pangloss/interface-core";
import { formatDate } from "../format";

// A date wherever it is part of something else: only the date, said as a person would, not the bounds
// and sort days that are worked out for searching.
export default function DateCard(props: ViewCardProps) {
  return <span class="text-sm">{formatDate(props.item) ?? props.label}</span>;
}
