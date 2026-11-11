import { Modal, useApi, useTranslations } from "@pangloss/interface-core";
import { createMemo, Errored, Loading } from "solid-js";
import { getMention } from "../api";
import type { Reconciled } from "../api";
import { ReconcilePanel } from "./ReconcilePanel";
import type { DoneHere, StillThere } from "./ReconcilePanel";

interface DialogProps {
  id: string;
  onDone: (done: Reconciled, here: DoneHere) => void;
  onClose: () => void;
  /** It is in the form of its document, which puts the entity in its place and saves it (`ReconcilePanel`) */
  inForm?: boolean;
  stillThere?: StillThere;
}

function Contents(props: DialogProps) {
  const api = useApi();
  // (as it is saved: one that is not there has not been saved yet, or was reconciled meanwhile)
  const mention = createMemo(() => getMention(api, props.id));
  return (
    <ReconcilePanel
      mention={mention()}
      onDone={props.onDone}
      onCancel={props.onClose}
      inForm={props.inForm}
      stillThere={props.stillThere}
    />
  );
}

/** Reconciling one mention, in a dialog over the page it is on (the page of reconciliations, or the form that edits its document) */
export default function ReconcileDialog(props: DialogProps) {
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
            <Contents {...props} />
          </Loading>
        </Errored>
      </div>
    </Modal>
  );
}
