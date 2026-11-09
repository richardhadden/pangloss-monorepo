import { defineModule } from "@pangloss/interface-core";

// The page /admin (nothing links to it), made of the parts that modules add to the place `admin`; the jobs are one
export default defineModule({
  name: "pangloss_admin",
  requires: [],
  components: {
    AdminPage: () => import("./components/AdminPage"),
  },
  routes: [{ path: "/admin", component: "AdminPage" }],
  slots: {
    admin: { Jobs: () => import("./components/JobsSection") },
  },
});
