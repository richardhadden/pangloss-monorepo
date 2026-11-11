import { buttonClass, userIsLoggedIn, useToasts, useTranslations } from "@pangloss/interface-core";
import type { PartActionProps } from "@pangloss/interface-core";
import { createSignal, lazy, Loading, Show } from "solid-js";
import { reloadSoon, TickIcon } from "./taskIcons";

// (the dialog's code is fetched when it is first opened)
const ConfirmDialog = lazy(() => import("./ConfirmDialog"));

/** The class of `pangloss-library` whose parts are tasks: an identification that a toolchain suggested */
export const SUGGESTED = "IdentificationByToolchain";

function ConfirmButton(props: { id: string; onDone?: () => void; changed?: () => boolean }) {
  const toasts = useToasts();
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  return (
    <>
      <button
        type="button"
        class={buttonClass("ordinary", "sm")}
        aria-haspopup="dialog"
        data-testid="confirm-button"
        onClick={() => {
          if (props.changed?.()) {
            toasts?.show(t("review_save_first", "Save your changes first: this is done to the saved document"), "error");
            return;
          }
          setOpen(true);
        }}
      >
        <TickIcon />
        {t("review_confirm", "Confirm")}
      </button>
      <Show when={open()}>
        <Loading fallback={null}>
          <ConfirmDialog
            id={props.id}
            onClose={() => setOpen(false)}
            onDone={(done) => {
              setOpen(false);
              // (the document has a new version: the page is read again, unless whoever shows the button does it)
              if (props.onDone) props.onDone();
              else reloadSoon(done.urisTaken.length > 0);
            }}
          />
        </Loading>
      </Show>
    </>
  );
}

/**
 * Beside an identification that a toolchain suggested (`partActions`), on the item's page and in the form, for
 * someone logged in: a button that confirms it. What is confirmed is the saved document, so a form with changes asks
 * for a save first.
 */
export function SuggestionAction(props: PartActionProps) {
  const id = () => (props.type === SUGGESTED && typeof props.item.id === "string" ? props.item.id : undefined);
  return (
    <Show when={id()}>
      {(found) => (
        // (who is logged in may still be being read)
        <Loading fallback={null}>
          <Show when={userIsLoggedIn()}>
            <ConfirmButton id={found()} changed={props.changed} />
          </Show>
        </Loading>
      )}
    </Show>
  );
}

export { ConfirmButton };
