/**
 * The default component map, and how to make one with overrides. This is above the
 * components: it is the only place that names all of them, so nothing below imports it.
 */
import { EntityCard, FieldList } from "./components";
import { Button, ErrorMessage } from "./primitives";
import type { ComponentMap } from "./types";

export const defaultComponents: ComponentMap = {
  Button,
  ErrorMessage,
  EntityCard,
  FieldList,
};

/** The default components, with any replaced by `overrides` */
export function createComponentMap(overrides: Partial<ComponentMap> = {}): ComponentMap {
  return { ...defaultComponents, ...overrides };
}
