import { useTranslations } from "@pangloss/interface-core";
import { createSignal, lazy, Loading, Show } from "solid-js";
import type { Ref } from "../api";
import type { DoneHere, StillThere } from "./ReconcilePanel";
import { SpannerIcon } from "./taskIcons";

// (the dialog's code is fetched when it is first opened)
const ReconcileDialog = lazy(() => import("./ReconcileDialog"));

/**
 * The spanner at the right of an unreconciled mention in the form of its document: opens the dialog that reconciles
 * it. The entity chosen is given to the form (`onReconciled`), which puts it in the mention's place as one more
 * change, saved with the rest: so it works in a form that holds other changes, and someone working through a
 * document reconciles each mention as they reach it.
 */
export function ReconcileButton(props: {
  id: string;
  label: string;
  class: string;
  /** The entity chosen, and what else of this document was ticked to be done with it */
  onReconciled: (entity: Ref, here: DoneHere) => void;
  stillThere: StillThere;
}) {
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  const name = () => t("review_reconcile_named", "Reconcile {label}", { label: props.label });
  return (
    <>
      <button
        type="button"
        class={props.class}
        aria-label={name()}
        title={name()}
        aria-haspopup="dialog"
        data-testid="reconcile-button"
        onClick={() => setOpen(true)}
      >
        <SpannerIcon />
      </button>
      <Show when={open()}>
        <Loading fallback={null}>
          <ReconcileDialog
            id={props.id}
            inForm
            stillThere={props.stillThere}
            onClose={() => setOpen(false)}
            onDone={(done, here) => {
              setOpen(false);
              props.onReconciled(done.entity, here);
            }}
          />
        </Loading>
      </Show>
    </>
  );
}
