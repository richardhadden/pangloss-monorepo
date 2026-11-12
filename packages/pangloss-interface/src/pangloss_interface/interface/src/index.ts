import { defineModule } from "@pangloss/interface-core";

// The pages for merging two entities that are one, and for undoing a merge (implementation_docs/entity-identity.md):
// a button in the console of an entity, the comparison of the two, the page of a merge (to verify, reject or undo
// it), the list of merges, notices above an entity that a merge waits on, and the merges made lately on /admin.
export default defineModule({
  name: "pangloss_interface",
  requires: [],
  components: {
    ComparePage: () => import("./components/ComparePage"),
    MergePage: () => import("./components/MergePage"),
    MergesPage: () => import("./components/MergesPage"),
  },
  routes: [
    { path: "/merges", component: "MergesPage" },
    { path: "/merges/:merge", component: "MergePage" },
    { path: "/:type/:id/merge/:other", component: "ComparePage" },
  ],
  consoleActions: {
    Merge: { loggedIn: true, load: () => import("./components/MergeAction") },
  },
  itemNotices: {
    Merges: () => import("./components/MergeNotices"),
  },
  // (a part of the page /admin, when pangloss_admin is installed)
  slots: {
    admin: { Merges: () => import("./components/MergesAdminSection") },
  },
});
