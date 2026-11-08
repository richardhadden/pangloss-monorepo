import { createSignal, lazy, Loading, Show } from "solid-js";
import { useTranslations } from "../../context";
import { ConsoleButton } from "../../primitives";

// (only someone who presses Delete needs the dialog)
const DeleteDialog = lazy(() => import("./DeleteDialog"));

/**
 * Delete, for the right of the console (of an item's page, and of its edit form): a bin that opens the
 * `DeleteDialog`, which asks first, or says why the item cannot be deleted
 */
export function DeleteButton(props: { type: string; id: string; label: string | undefined; onDeleted: () => void }) {
  const { t } = useTranslations();
  const [asking, setAsking] = createSignal(false);
  return (
    <>
      <ConsoleButton label={t("delete", "Delete")} onClick={() => setAsking(true)} tone="danger">
        <svg
          viewBox="0 0 24 24"
          class="size-5 select-none fill-none stroke-current stroke-2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M4 7h16M10 11v6M14 11v6M5.5 7l1 12.5h11l1-12.5M9 7V4.5h6V7" />
        </svg>
      </ConsoleButton>
      <Show when={asking()}>
       <Loading fallback={null}>
        <DeleteDialog
          type={props.type}
          id={props.id}
          label={props.label}
          onDeleted={() => {
            setAsking(false);
            props.onDeleted();
          }}
          onClose={() => setAsking(false)}
        />
       </Loading>
      </Show>
    </>
  );
}
