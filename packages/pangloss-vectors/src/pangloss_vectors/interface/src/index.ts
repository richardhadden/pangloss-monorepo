import { defineModule } from "@pangloss/interface-core";

// The interface of similarity: on the page of every document and entity, after its contents, the items most like it
// (`itemSections.Similar`); on /admin, the state of the vectors and a Rebuild button (`slots.admin`).
// (implementation_docs/vectors.md, "The interface")
export default defineModule({
  name: "pangloss_vectors",
  requires: [],
  components: {},
  itemSections: {
    Similar: () => import("./components/SimilarSection"),
  },
  // (a part of the page /admin, when pangloss_admin is installed)
  slots: {
    admin: { Vectors: () => import("./components/VectorsAdminSection") },
  },
});
