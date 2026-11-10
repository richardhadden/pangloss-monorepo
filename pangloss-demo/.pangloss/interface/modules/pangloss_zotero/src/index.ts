import { defineModule } from "@pangloss/interface-core";

// The interface of Zotero: a person makes an item of the library one of the project's classes (a Book), and undoes it.
// On the form of a new Book, a row (*Zotero item*) bases it on an item; on a Book's page, *Link to Zotero* makes a Book
// made by hand an item (merging it with the item's node), and *Unlink* takes the item off. (implementation_docs/zotero-sources.md)
export default defineModule({
  name: "pangloss_zotero",
  requires: [],
  components: {
    ZoteroItemPage: () => import("./components/ZoteroItemPage"),
  },
  newItemFields: {
    FromZotero: () => import("./components/FromZotero"),
  },
  editItemFields: {
    ZoteroFormRows: () => import("./components/ZoteroFormRows"),
  },
  consoleActions: {
    Link: { loggedIn: true, load: () => import("./components/ZoteroLinkAction") },
  },
});
