import { defineModule } from "@pangloss/interface-core";

// The interface of comparison: on the page of a statement of a compared class, after its contents, how it stands to
// the statements it is paired with (`itemSections.Compared`; "Carried out?" where it prescribes). The page of two
// statements side by side, to which each row links (`pairHref`), is step 7.5's and not here yet.
// (implementation_docs/compare.md, "The interface")
export default defineModule({
  name: "pangloss_compare",
  requires: [],
  components: {},
  itemSections: {
    Compared: () => import("./components/ComparedSection"),
  },
});
