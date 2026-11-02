import { defineModule } from "@pangloss/interface-core";

// The interface of the dates (the Embedded models of `pangloss_dates`): a card that says a date as a
// person would, instead of listing the calendar, the bounds and the sort days. `pangloss_dates` points
// `Date` at it in its `InterfaceMeta`, and the other dates have it from `Date`.
export default defineModule({
  name: "pangloss_dates",
  requires: [],
  components: {
    DateCard: () => import("./components/DateCard"),
  },
  routes: [],
});
