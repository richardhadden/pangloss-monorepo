import { defineModule } from "@pangloss/interface-core";

// A link to an item as RDF, for anyone who can see the item
export default defineModule({
  name: "pangloss_rdf",
  requires: [],
  consoleActions: {
    ViewRdf: () => import("./components/ViewRdf"),
  },
  // (its menu has the item's JSON too: the console has no button for it)
  jsonLinkIn: "ViewRdf",
});
