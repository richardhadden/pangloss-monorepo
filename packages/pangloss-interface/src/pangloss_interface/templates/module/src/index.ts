import { defineModule } from "@pangloss/interface-core";

// What this module provides. A model names a component as "{{app}}:<key>" in its
// `InterfaceMeta` (list_page, item_page, view_card, edit_card); a route puts a page at an address.
export default defineModule({
  name: "{{app}}",
  requires: [],
  components: {
    // Each is loaded when a page that uses it is (a chunk of its own). A component is the
    // default export of its file.
    ExampleCard: () => import("./components/ExampleCard"),
  },
  routes: [
    // { path: "/{{app}}/example", component: "ExamplePage" },
  ],
});
