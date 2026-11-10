import { defineModule } from "@pangloss/interface-core";

// The interface of derived facts: on an item's page, after its contents, what the rules derive about it, apart from
// what its documents say (`_derived` of its view), each fact with the rules and documents it rests on.
// (implementation_docs/interface-features.md)
export default defineModule({
  name: "pangloss_derived",
  requires: [],
  components: {},
  itemSections: {
    Derived: () => import("./components/DerivedSection"),
  },
  routes: [],
});
