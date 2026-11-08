import { defineModule } from "@pangloss/interface-core";

// The interface of history: a button in the console of an item that has history, which opens a panel of its versions;
// a version slides out beside it, and can be restored; and a page that shows every version side by side, with what
// changed marked, /<type>/<id>/history. (docs/history-interface.md)
export default defineModule({
  name: "pangloss_history",
  requires: [],
  components: {
    HistoryPage: () => import("./components/HistoryPage"),
  },
  consoleActions: {
    History: { loggedIn: true, load: () => import("./components/HistoryAction") },
  },
  routes: [{ path: "/:type/:id/history", component: "HistoryPage" }],
});
