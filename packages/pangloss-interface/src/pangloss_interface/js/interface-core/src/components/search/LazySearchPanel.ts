import { lazy } from "solid-js";

// (most visits to a list never open the form, and it brings the type menus and pickers with it)
export const SearchPanel = lazy(() => import("./SearchPanel"));

// (the fields of the search form alone, for a module's dialog that holds them: loaded when first drawn, as the panel is)
export const SearchFields = lazy(() => import("./SearchFields"));
export type { SearchFieldsControl } from "./SearchFields";
