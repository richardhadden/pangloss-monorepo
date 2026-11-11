import { useToasts, useTranslations } from "@pangloss/interface-core";
import { createSignal, lazy, Loading, Show } from "solid-js";
import { reloadSoon, SpannerIcon } from "./taskIcons";

// (the dialog's code is fetched when it is first opened)
const ReconcileDialog = lazy(() => import("./ReconcileDialog"));

/**
 * The spanner at the right of an unreconciled mention: opens the dialog that reconciles it. What is reconciled is the
 * saved document, so in a form with changes (`changed`) it asks for a save first; once it is done the page is read
 * again, as the document has a new version.
 */
export function ReconcileButton(props: { id: string; label: string; class: string; changed?: () => boolean }) {
  const toasts = useToasts();
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
        onClick={() => {
          if (props.changed?.()) {
            toasts?.show(t("review_save_first", "Save your changes first: this is done to the saved document"), "error");
            return;
          }
          setOpen(true);
        }}
      >
        <SpannerIcon />
      </button>
      <Show when={open()}>
        <Loading fallback={null}>
          <ReconcileDialog
            id={props.id}
            onClose={() => setOpen(false)}
            onDone={(done) => {
              setOpen(false);
              reloadSoon(done.urisTaken.length > 0);
            }}
          />
        </Loading>
      </Show>
    </>
  );
}
