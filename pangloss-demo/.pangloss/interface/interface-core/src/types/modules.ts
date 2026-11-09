/**
 * Interface modules: the manifest an app's module exports, and the props of the components it
 * provides for a model's page or card. (docs/interface-modules-implementation.md)
 */
import type { Component } from "solid-js";
import type { EmbeddedField, ModelDefinition, ModelDefinitions } from "./models";
import type { Search } from "./components";

/** The four things a model can name a component for (`list_page` ... in Python) */
export type CustomSlot = "listPage" | "itemPage" | "viewCard" | "editCard";

export interface ListPageProps {
  /** The type in the address; may be a parent of what the model is */
  type: string;
  model: ModelDefinition;
  /** `?q=` and `?deep=` as the generic page reads them */
  search: Search;
  /** Writes them back to the address */
  onSearch: (search: Search) => void;
}

export interface ItemPageProps {
  /** The item's own type */
  type: string;
  id: string;
  /** The item as the API sends it (already read: the page's `preload` has fetched it) */
  item: Record<string, unknown>;
  model: ModelDefinition;
}

export interface ViewCardProps {
  /** The type of the item (its own, which can be a subtype of the list's) */
  type: string;
  id?: string;
  label: string;
  /** Where the card goes, if it is a link */
  href?: string;
  /** The semantic spaces the item is in, outermost first */
  spaces?: string[];
  /** The item's data, where the item is part of what is shown (an embedded item) */
  item?: Record<string, unknown>;
  /** Where it is shown */
  context: "result" | "reference" | "embedded" | "page";
  /** In a list (`context: "result"`): the keyboard has it selected. A card may draw that as it does being hovered */
  selected?: boolean;
}

/**
 * An embedded value in a form (a date, ...), under the menu of its types: what the model's own editor is
 * given instead of the rows of its fields. `value` and `onChange` are the whole value; for its parts,
 * `path` is where it is in the form (`useItemForm().get/set`), and `ModelFields` (with `skip`) edits
 * any of its fields as the form would, an embedded one with its own editor again.
 */
export interface EditCardProps {
  /** The type of the value (chosen in the menu above the card) */
  type: string;
  model: ModelDefinition;
  /** The name of the field, for the labels of inputs */
  label: string;
  /** Where the value is in the form */
  path: (string | number)[];
  /** The field the value is in (its markers say what the server does when the value does not say) */
  field?: EmbeddedField;
  value: Record<string, unknown>;
  /**
   * Replaces the whole value (keep its `type`). To change one part, set it by its path instead: a
   * copy of `value` taken before an earlier change has been applied would undo that change.
   */
  onChange: (value: Record<string, unknown>) => void;
}

export interface CustomProps {
  listPage: ListPageProps;
  itemPage: ItemPageProps;
  viewCard: ViewCardProps;
  editCard: EditCardProps;
}

/**
 * Whether a reified relation or a conjunction is shown folded into the one thing it holds (`InterfaceMeta(collapse=
 * "app:name")`): given the item as the API sends it, and its model. It is only asked when it holds exactly one.
 */
export type CollapseRule = (item: Record<string, unknown>, model: ModelDefinition) => boolean;

/**
 * What a component a module adds to the console of an item (`consoleActions`) is given. It decides itself whether
 * to show anything (a button, usually a `ConsoleButton`).
 */
export interface ConsoleActionProps {
  /** The item's own type */
  type: string;
  id: string;
  model: ModelDefinition;
  /** The item's page, or the form that edits it */
  page: "item" | "edit";
}

/**
 * The form of a new item, as a component a module adds to its console (`newItemActions`) or its fields
 * (`newItemFields`) is given it.
 */
export interface NewItemForm {
  /** The value at a path of the form (`["label"]`, `["writtenBy", 0]`) */
  get: (path: (string | number)[]) => unknown;
  /** Sets the value at a path, as a field of the form does */
  set: (path: (string | number)[], value: unknown) => void;
  /**
   * How Save sends the form from now on, instead of making a new item: given what would be sent (checked, as for a
   * create), it gives what was saved. `undefined` puts back the usual way. What it refuses is shown as a refused
   * create is.
   */
  sendBy: (
    sender: ((body: Record<string, unknown>) => Promise<{ id: string; type: string; label: string }>) | undefined,
  ) => void;
}

/**
 * What a component a module adds to the console of the form that makes a new item (`newItemActions`), or to its fields
 * (`newItemFields`), is given. It decides itself whether to show anything (usually a `ConsoleButton`, or a `FieldRow`).
 */
export interface NewItemActionProps {
  /** The type of what is made */
  type: string;
  model: ModelDefinition;
  form: NewItemForm;
}

/**
 * What a component a module adds after the contents of an item's page (`itemSections`) is given. It decides itself
 * whether to show anything (a section, usually under a `SectionBar`). It is rendered in a `Loading` of its own (no
 * fallback), after what refers to the item: what it reads for itself it reads directly, with no boundary of its own.
 */
export interface ItemSectionProps {
  /** The item's own type */
  type: string;
  id: string;
  /** The item as the API sends it */
  item: Record<string, unknown>;
  model: ModelDefinition;
}

/**
 * What a component a module adds to the rows of a list (`resultMarks`) is given. It decides itself whether to show
 * anything, and draws something small: it is inside the row's link, at its right end, with its own space on the right.
 */
export interface ResultMarkProps {
  /** The item's own type */
  type: string;
  /** The item as the list sends it (`id`, `label`, `meta`, and the literal fields of the node) */
  item: Record<string, unknown>;
}

/** One item that refers to the item of the page, with the name of the field (as the page says it) it is in */
export interface IncomingEntry {
  key: string;
  name: string;
  item: Record<string, unknown>;
}

/**
 * Another way of showing what refers to an item than by the field it is in (`incomingViews`): it takes some of it,
 * and shows that in a section of its own after the item's fields; the rest stays by field. A button the module adds to
 * the console (`consoleActions`) chooses it, with `useIncomingView()`, while the page offers it.
 */
export interface IncomingView {
  /** Whether it shows this item that refers to the item of the page (not loaded lazily: it is small) */
  takes: (item: Record<string, unknown>, definitions: ModelDefinitions) => boolean;
  /** Shows what it takes (given `IncomingViewProps`; loaded when it is first chosen) */
  component: ComponentLoader;
}

export interface IncomingViewProps {
  /** The item's own type */
  type: string;
  id: string;
  model: ModelDefinition;
  /** What it takes, in the order of the model's incoming fields */
  entries: IncomingEntry[];
}

/** What a loader gives: a module with a component as its default export */
export type ComponentLoader = () => Promise<{ default: Component<any> }>;

/** A console action: its loader, or with `loggedIn`, one shown only to someone logged in, whose code no one else fetches */
export type ConsoleAction = ComponentLoader | { loggedIn: true; load: ComponentLoader };

export interface ModuleRoute {
  /** (inside the interface; it comes before `/:type`, so it may not be the name of a model) */
  path: string;
  /** A key of `components` */
  component: string;
  /** Called to start what the page reads, as the routes of the application do */
  preload?: (args: { params: Record<string, string>; location: { query: Record<string, unknown> } }) => void;
}

/** What an app's interface module provides (`defineModule`) */
export interface ModuleManifest {
  /** The name of the Python app: checked */
  name: string;
  /** Other modules this one uses, by app name: they must be installed, with no cycles */
  requires?: string[];
  /** Every component a model or a route can name: each loaded when a page that uses it is */
  components: Record<string, ComponentLoader>;
  routes?: ModuleRoute[];
  /** The rules a model can name with `InterfaceMeta(collapse="app:name")` (not loaded lazily: they are small) */
  collapseRules?: Record<string, CollapseRule>;
  /**
   * Components for the console of every item page and of the form that edits an item, at its right, before the page's
   * own buttons (each loaded when the console is first shown)
   */
  consoleActions?: Record<string, ConsoleAction>;
  /**
   * Components for the console of the form that makes a new item, before its own buttons (`NewItemActionProps`: they
   * can fill the form in, and change how it is sent)
   */
  newItemActions?: Record<string, ComponentLoader>;
  /**
   * Components first among the fields of the form that makes a new item, on its page and in the dialog of a relation
   * (`NewItemActionProps`, as `newItemActions`): rows of the form, usually a `FieldRow`
   */
  newItemFields?: Record<string, ComponentLoader>;
  /** Components after the contents of every item's page, in the order of the modules (each loaded when first shown) */
  itemSections?: Record<string, ComponentLoader>;
  /**
   * Components at the right end of each row of a list (`ResultMarkProps`), in the order of the modules. Not loaded
   * lazily, as `collapseRules` are not: they are small, and every row of every list is drawn with them
   */
  resultMarks?: Record<string, Component<ResultMarkProps>>;
  /** Other ways of showing what refers to an item (`IncomingView`): by its name `app:key` */
  incomingViews?: Record<string, IncomingView>;
}
