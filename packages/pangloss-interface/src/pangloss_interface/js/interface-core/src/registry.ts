/**
 * The default component map, and how to make one with overrides. This is above the
 * components: it is the only place that names all of them, so nothing below imports it.
 */
import { Console, ConsoleBar, EntityCard, FieldList, LoginForm, NavBar, ResultButton } from "./components";
import { Button, ErrorMessage, Modal } from "./primitives";
import type { ComponentMap } from "./types";

export const defaultComponents: ComponentMap = {
  Button,
  ErrorMessage,
  EntityCard,
  FieldList,
  NavBar,
  ResultButton,
  LoginForm,
  Modal,
  ConsoleBar,
  Console,
};

/** The default components, with any replaced by `overrides` */
export function createComponentMap(overrides: Partial<ComponentMap> = {}): ComponentMap {
  return { ...defaultComponents, ...overrides };
}
