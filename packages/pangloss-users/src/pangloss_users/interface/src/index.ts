import { defineModule } from "@pangloss/interface-core";

// The interface of users: a page listing them (linked from the navigation bar: pangloss_users/interface_config.py), a
// page for each with what they have made or changed, and the link to it from a name in the console.
export default defineModule({
  name: "pangloss_users",
  requires: [],
  components: {
    UsersPage: () => import("./components/UsersPage"),
    UserPage: () => import("./components/UserPage"),
  },
  routes: [
    { path: "/users", component: "UsersPage" },
    { path: "/users/:username", component: "UserPage" },
  ],
  userHref: (username) => `/users/${encodeURIComponent(username)}`,
  // (a part of the page /admin, when pangloss_admin is installed)
  slots: {
    admin: { Users: () => import("./components/UsersAdminSection") },
  },
});
