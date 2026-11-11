import { Modal, useApi, useTranslations } from "@pangloss/interface-core";
import { createMemo, Errored, Loading } from "solid-js";
import { getMention } from "../api";
import type { Reconciled } from "../api";
import { ReconcilePanel } from "./ReconcilePanel";

function Contents(props: { id: string; onDone: (done: Reconciled) => void; onClose: () => void }) {
  const api = useApi();
  // (as it is saved: one that is not there has not been saved yet, or was reconciled meanwhile)
  const mention = createMemo(() => getMention(api, props.id));
  return <ReconcilePanel mention={mention()} onDone={props.onDone} onCancel={props.onClose} />;
}

/** Reconciling one mention, in a dialog over the page it is on (the item's page, or the form that edits it) */
export default function ReconcileDialog(props: { id: string; onDone: (done: Reconciled) => void; onClose: () => void }) {
  const { t } = useTranslations();
  return (
    <Modal title={t("review_reconcile_title", "Reconcile")} onClose={props.onClose} size="lg">
      <div class="overflow-y-auto p-4" data-testid="reconcile-dialog">
        <Errored
          fallback={() => (
            <p class="text-sm text-slate-700" data-testid="reconcile-not-saved">
              {t("review_not_saved", "This is not in the saved document (any more). Save the document first.")}
            </p>
          )}
        >
          <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
            <Contents id={props.id} onDone={props.onDone} onClose={props.onClose} />
          </Loading>
        </Errored>
      </div>
    </Modal>
  );
}
