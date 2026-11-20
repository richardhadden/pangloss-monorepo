import { defineModule } from "@pangloss/interface-core";

// The interface of descriptions (`MatchesCriteria`): on the page of a document, a card with the summary of the
// criteria and the candidates, which follows the worker until they are found; in a form, a card whose pencil opens
// the criteria in a dialog, with the search form of the class described and what the criteria find as they are
// written. (implementation_docs/matches-criteria.md, "The interface")
export default defineModule({
  name: "pangloss_criteria",
  requires: [],
  components: {
    // (what `MatchesCriteria` of `pangloss_criteria.models` names for itself: on an item's page, and in a form)
    CriteriaCard: () => import("./components/CriteriaCard"),
    CriteriaEditor: () => import("./components/CriteriaEditor"),
  },
});
