import { defineModule } from "@pangloss/interface-core";

export default defineModule({
  name: "pangloss_library",
  requires: [],
  components: {
    WeightedAlternativeCard: () => import("./components/WeightedAlternativeCard"),
  },
  routes: [],
});
