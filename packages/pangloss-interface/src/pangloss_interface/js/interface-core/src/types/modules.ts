/**
 * Interface modules: the manifest an app's module exports, and the props of the components it
 * provides for a model's page or card. (docs/interface-modules-implementation.md)
 */
import type { Component } from "solid-js";
import type { ModelDefinition } from "./models";
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
}

/** Provisional: fixed when the forms are built */
export interface EditCardProps {
  /** undefined: a new one */
  item?: Record<string, unknown>;
  model: ModelDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
  errors?: { path: string[]; message: string }[];
  disabled?: boolean;
}

export interface CustomProps {
  listPage: ListPageProps;
  itemPage: ItemPageProps;
  viewCard: ViewCardProps;
  editCard: EditCardProps;
}

/** What a loader gives: a module with a component as its default export */
export type ComponentLoader = () => Promise<{ default: Component<any> }>;

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
}
