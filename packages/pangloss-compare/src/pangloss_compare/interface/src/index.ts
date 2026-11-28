import { defineModule } from "@pangloss/interface-core";

// The interface of comparison: on the page of a statement of a compared class, after its contents, how it stands to
// the statements it is paired with (`itemSections.Compared`; "Carried out?" where it prescribes); and the page of two
// statements side by side, to which each row links (`pairHref`), where a person records a judgement of the pair; and
// on the same pages, each statement `pangloss_vectors`' "Similar" lists labelled with its relation to this one, with
// two filters (`listLabels.Similar`, for the list "similar"). (implementation_docs/compare.md, "The interface")
export default defineModule({
  name: "pangloss_compare",
  requires: [],
  components: {
    PairPage: () => import("./components/PairPage"),
  },
  routes: [{ path: "/compare/:type/:a/:b", component: "PairPage" }],
  itemSections: {
    Compared: () => import("./components/ComparedSection"),
  },
  listLabels: {
    Similar: {
      lists: ["similar"],
      // (`isCompared`, written here so that every page does not load `compared.ts` for it)
      applies: (model) => model.extras?.compared === true,
      component: () => import("./components/SimilarLabels"),
    },
  },
});
