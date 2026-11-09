/**
 * The default component map, and how to make one with overrides. This is above the
 * components: it is the only place that names all of them, so nothing below imports it.
 */
import { lazy } from "solid-js";
import {
  ClipboardBarWhenNeeded as ClipboardBar,
  Console,
  ConsoleBar,
  EntityCard,
  FieldList,
  LoginForm,
  NavBar,
  ReferenceChip,
  ResultButton,
  Toasts,
} from "./components";
import { Button, ErrorMessage, Modal } from "./primitives";
import type { ComponentMap } from "./types";

// What most pages never show is fetched when it is first shown, not with every page: the form and all it brings with
// it, and the contents of an item
const ItemForm = lazy(() => import("./components/form/ItemForm"));
const ItemContents = lazy(() => import("./components/ItemContents"));

export const defaultComponents: ComponentMap = {
  Button,
  ErrorMessage,
  EntityCard,
  FieldList,
  NavBar,
  ResultButton,
  ReferenceChip,
  ItemContents,
  ItemForm,
  LoginForm,
  Modal,
  ConsoleBar,
  ClipboardBar,
  Toasts,
  Console,
};

/** The default components, with any replaced by `overrides` */
export function createComponentMap(overrides: Partial<ComponentMap> = {}): ComponentMap {
  return { ...defaultComponents, ...overrides };
}

/** Start loading a component that is `lazy` (one of the map's may be, an override may not): before it is needed */
export function preload(component: unknown): void {
  // (what fails to load says so where it is shown, not here)
  void (component as { preload?: () => Promise<unknown> }).preload?.()?.catch(() => {});
}
