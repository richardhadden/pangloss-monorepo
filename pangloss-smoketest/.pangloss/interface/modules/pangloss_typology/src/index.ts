import { defineModule } from "@pangloss/interface-core";

// The interface of a typology (an entity made by `class RoleTypology(Typology)`): its list page is the
// hierarchy as a tree, its item page shows where a type sits and what has it, and its card marks it as a
// type. `pangloss_typology` points the generated entity at these in its `InterfaceMeta`.
export default defineModule({
  name: "pangloss_typology",
  requires: [],
  components: {
    TypeTree: () => import("./components/TypeTree"),
    TypeItem: () => import("./components/TypeItem"),
    TypeCard: () => import("./components/TypeCard"),
  },
  routes: [],
});
