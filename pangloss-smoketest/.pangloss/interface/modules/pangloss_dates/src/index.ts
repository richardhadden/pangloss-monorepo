import { defineModule } from "@pangloss/interface-core";
import { isDateable } from "./dating";

// The interface of the dates (the Embedded models of `pangloss_dates`): a card that says a date as a
// person would, instead of listing the calendar, the bounds and the sort days. `pangloss_dates` points
// `Date` at it in its `InterfaceMeta`, and the other dates have it from `Date`. And its editor in a form,
// which asks only what a person says of a date (the bounds and sort days are the server's to work out).
// On an item's page, what refers to it and can have a date (`Dateable`) can be sorted by date, with a timeline: a view
// of it (`ByDate`), and the button in the console that chooses it (`SortByDate`). (docs/interface-hooks-plan.md)
export default defineModule({
  name: "pangloss_dates",
  requires: [],
  components: {
    DateCard: () => import("./components/DateCard"),
    DateEditor: () => import("./components/DateEditor"),
  },
  consoleActions: {
    SortByDate: () => import("./components/SortByDate"),
  },
  incomingViews: {
    ByDate: { takes: (item, definitions) => isDateable(definitions, item.type), component: () => import("./components/ByDate") },
  },
  routes: [],
});
