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
  routes: [],
});
