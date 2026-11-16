import { defineModule } from "@pangloss/interface-core";
import { SuggestionUris } from "./components/SuggestionUris";

export default defineModule({
  name: "pangloss_library",
  requires: [],
  components: {
    WeightedAlternativeCard: () => import("./components/WeightedAlternativeCard"),
  },
  // (in the form of an identification a toolchain suggested: its URIs, shown and not changed)
  partActions: { SuggestionUris },
  // (above an entity's contents: what it is said to be the same as, by statements with an `IdentityClaim()` relation)
  itemNotices: { Identity: () => import("./components/IdentitySection") },
  // (after them, if the page's address asks: what is said of the other entities of its cluster)
  itemSections: { IdentityIncluded: () => import("./components/IdentityIncluded") },
  routes: [],
});
