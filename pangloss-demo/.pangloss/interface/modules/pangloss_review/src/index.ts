import { defineModule } from "@pangloss/interface-core";
import { ListStatusFlag } from "./components/ListStatusFlag";
import { SuggestionAction } from "./components/SuggestionAction";

// The interface of review: a button in the console of a reviewed document (its status and the number of open
// comments), which opens a panel with the status and the comments; a flag on each reviewed row of a list; the pages of
// tasks (/review: documents to check, mentions to reconcile, identifications to confirm); an unreconciled mention as a
// chip with a spanner that reconciles it; and a button that confirms an identification a toolchain suggested.
// (implementation_docs/review.md)
export default defineModule({
  name: "pangloss_review",
  requires: [],
  components: {
    ReviewQueue: () => import("./components/ReviewQueue"),
    Reconciliations: () => import("./components/Reconciliations"),
    Identifications: () => import("./components/Identifications"),
    // (what `Unreconciled` of `pangloss_review.models` names for itself: on an item's page, and in a form)
    UnreconciledCard: () => import("./components/UnreconciledCard"),
    UnreconciledEditor: () => import("./components/UnreconciledEditor"),
  },
  consoleActions: {
    Review: { loggedIn: true, load: () => import("./components/ReviewAction") },
  },
  resultMarks: { StatusFlag: ListStatusFlag },
  // (beside a part of a document: an identification that a toolchain suggested has a button that confirms it)
  partActions: { ConfirmSuggestion: SuggestionAction },
  // (the tasks; the navigation bar links to the first: pangloss_review/interface_config.py)
  routes: [
    { path: "/review/reconciliations", component: "Reconciliations" },
    { path: "/review/identifications", component: "Identifications" },
    { path: "/review", component: "ReviewQueue" },
  ],
});
