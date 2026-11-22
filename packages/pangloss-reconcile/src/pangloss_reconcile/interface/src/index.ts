import { defineModule } from "@pangloss/interface-core";

// The interface of reconciliation: in review's reconcile dialog, above its picker, the entities the mention may be,
// each with its score and its reasons, and a button that chooses it (`slots.reconcileCandidates`, a place that
// pangloss_review offers). (implementation_docs/reconcile.md, "The interface")
export default defineModule({
  name: "pangloss_reconcile",
  requires: [],
  components: {},
  slots: {
    reconcileCandidates: { Candidates: () => import("./components/ReconcileCandidates") },
  },
});
