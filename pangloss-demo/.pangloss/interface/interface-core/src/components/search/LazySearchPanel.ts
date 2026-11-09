import { lazy } from "solid-js";

// (most visits to a list never open the form, and it brings the type menus and pickers with it)
export const SearchPanel = lazy(() => import("./SearchPanel"));
