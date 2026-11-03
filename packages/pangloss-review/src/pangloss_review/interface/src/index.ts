import { defineModule } from "@pangloss/interface-core";

// The interface of review: a button in the console of a reviewed document (its status and the number of open
// comments), which opens a panel with the status and the comments. (docs/review-interface.md)
export default defineModule({
  name: "pangloss_review",
  requires: [],
  components: {},
  consoleActions: {
    Review: () => import("./components/ReviewAction"),
  },
  routes: [],
});
