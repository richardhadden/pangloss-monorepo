import type { ViewCardProps } from "@pangloss/interface-core";
import { MentionChip } from "./MentionChip";

/**
 * An unreconciled mention where it is read: its chip ("Unreconciled", then the type it would be and what the source
 * calls it). It is not reconciled from here: that is done in the form of its document (the spanner of
 * `UnreconciledEditor`), or from the page of reconciliations.
 */
export default function UnreconciledCard(props: ViewCardProps) {
  const id = () => (typeof props.item?.id === "string" ? props.item.id : props.id);
  // (what it would be, where the whole item is there to say; a bare reference to one has only its own type)
  const type = () =>
    typeof props.item?.unreconciledType === "string" ? props.item.unreconciledType : props.type;
  return (
    <span class="inline-flex min-w-0 items-stretch" data-item-id={id()} data-testid="unreconciled">
      <MentionChip type={type()} label={props.label} href={props.href} />
    </span>
  );
}
