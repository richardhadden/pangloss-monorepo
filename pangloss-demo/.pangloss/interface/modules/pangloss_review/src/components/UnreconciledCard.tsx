import { DefaultReferenceChip, userIsLoggedIn } from "@pangloss/interface-core";
import type { ViewCardProps } from "@pangloss/interface-core";
import { Loading, Show } from "solid-js";
import { ReconcileButton } from "./ReconcileButton";

/**
 * An unreconciled mention where a document shows it: the usual chip (its type at the left), and for someone logged
 * in a spanner at its right that reconciles it. Where it is only referred to (a list, a search), the chip alone.
 */
export default function UnreconciledCard(props: ViewCardProps) {
  const id = () => (typeof props.item?.id === "string" ? props.item.id : props.id);
  const inDocument = () => props.context === "embedded" || props.context === "page";
  return (
    <span class="inline-flex min-w-0 items-stretch" data-item-id={id()} data-testid="unreconciled">
      <DefaultReferenceChip type={props.type} label={props.label} href={props.href} />
      <Show when={inDocument() && id()}>
        {(found) => (
          // (who is logged in may still be being read)
          <Loading fallback={null}>
            <Show when={userIsLoggedIn()}>
              <ReconcileButton
                id={found()}
                label={props.label}
                class="-ml-px flex w-7 cursor-pointer items-center justify-center rounded-r-xs border-[0.5px] border-slate-400/70 bg-white text-slate-600 hover:bg-slate-200"
              />
            </Show>
          </Loading>
        )}
      </Show>
    </span>
  );
}
