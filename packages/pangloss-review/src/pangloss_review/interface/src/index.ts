import { defineModule } from "@pangloss/interface-core";

// The interface of review: a button in the console of a reviewed document (its status and the number of open
// comments), which opens a panel with the status and the comments; and a page with the queue of documents to check,
// /review. (docs/review-interface.md)
export default defineModule({
  name: "pangloss_review",
  requires: [],
  components: {
    ReviewQueue: () => import("./components/ReviewQueue"),
  },
  consoleActions: {
    Review: () => import("./components/ReviewAction"),
  },
  // (the queue of documents to check; the navigation bar links to it: pangloss_review/interface_config.py)
  routes: [{ path: "/review", component: "ReviewQueue" }],
});
