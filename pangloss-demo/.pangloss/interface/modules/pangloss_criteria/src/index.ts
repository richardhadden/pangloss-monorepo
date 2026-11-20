import { defineModule } from "@pangloss/interface-core";

// The interface of descriptions (`MatchesCriteria`): on the page of a document, a card with the summary of the
// criteria and the candidates, which follows the worker until they are found; in a form, a card whose pencil opens
// the criteria in a dialog, with the search form of the class described and what the criteria find as they are
// written. The page of the descriptions that are out of date after a migration (/criteria/broken, for someone logged
// in), and how many are on /admin, with the link to it. A shared description (`Description`) has a page of its own,
// and its criteria are edited in its form with the same search form. (implementation_docs/matches-criteria.md, "The
// interface", "Shared descriptions")
export default defineModule({
  name: "pangloss_criteria",
  requires: [],
  components: {
    // (what `MatchesCriteria` of `pangloss_criteria.models` names for itself: on an item's page, and in a form)
    CriteriaCard: () => import("./components/CriteriaCard"),
    CriteriaEditor: () => import("./components/CriteriaEditor"),
    BrokenPage: () => import("./components/BrokenPage"),
    // (what `Description` names for itself: `item_page`)
    DescriptionPage: () => import("./components/DescriptionPage"),
  },
  // (the criteria of a shared description in its form: a row of its own, for that class only)
  newItemFields: { DescriptionCriteria: () => import("./components/DescriptionCriteria") },
  editItemFields: { DescriptionCriteria: () => import("./components/DescriptionCriteria") },
  routes: [{ path: "/criteria/broken", component: "BrokenPage" }],
  // (a part of the page /admin, when pangloss_admin is installed: the page is linked from there)
  slots: {
    admin: { BrokenDescriptions: () => import("./components/BrokenAdminSection") },
  },
});
