/**
 * The props of the components of the library, and the map of them that can be
 * overridden. This is the bottom layer: it imports nothing else of the library, so
 * that anything can use these types without a circular dependency.
 */
import type { JSX } from "@solidjs/web";
import type { Component } from "solid-js";

export interface ButtonProps {
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: (event: MouseEvent) => void;
  children?: JSX.Element;
}

export interface ErrorMessageProps {
  error: unknown;
}

export interface EntityCardProps {
  id: string;
  type: string;
  label: string;
}

export interface NavIconCellProps {
  /** What the icon means, for a screen reader (and the name of the button) */
  label: string;
  /** Makes the cell a button */
  onClick?: () => void;
  /** For a button that expands something: whether it is */
  expanded?: boolean;
  /** The icon */
  children?: JSX.Element;
}

export interface NavRowButtonProps {
  /** Makes it a link, rather than a button */
  href?: string;
  onClick?: () => void;
  /** Whether it is in a `NavRow`, filling the width that the icon cell leaves */
  inRow?: boolean;
  /** How many steps the text is moved in from the left */
  indent?: number;
  children?: JSX.Element;
}

export interface NavRowProps {
  /** Whether there is a rule above it (there is, unless false) */
  ruled?: boolean;
  children?: JSX.Element;
}

export type ConsoleButtonTone = "neutral" | "entity" | "document" | "danger";

export interface ConsoleButtonProps {
  /** What it does: the name for a screen reader, a tooltip, and the text when `text` */
  label: string;
  /** Makes it a link, rather than a button */
  href?: string;
  onClick?: () => void;
  /** Colour: `entity` and `document` match the tints of the console; `neutral` if not given */
  tone?: ConsoleButtonTone;
  disabled?: boolean;
  /** Makes it a toggle button: whether it is on */
  pressed?: boolean;
  /** Shows the label beside the icon (and so is wider than a square) */
  text?: boolean;
  /** The icon */
  children?: JSX.Element;
}

export interface ConsoleProps {
  /** The name of the type of what the page shows */
  type: string;
  /** The page is a list of the type (its name is shown in the plural) */
  list?: boolean;
  /** The label of the item, when the page is one */
  label?: string;
  /** The actions that can be taken, shown on the right */
  children?: JSX.Element;
}

export interface NavBarProps {
  /** Where the Home link goes (`/` if not given) */
  homeHref?: string;
  /** Who is logged in (a name to show), if anyone */
  user?: string;
  onLogin?: () => void;
  onLogout?: () => void;
  /** The code of the language selected (`en` or `de`); `en` if not given */
  language?: string;
  onLanguage?: (code: string) => void;
  /** What is shown in the bar while it is expanded */
  children?: JSX.Element;
}

export interface FieldListProps {
  /** The name of a model */
  model: string;
}

/**
 * Every component that an application can replace. A component of the library gets
 * the others it uses with `useComponent`, never by importing them, so that an
 * override is used everywhere.
 */
export interface ComponentMap {
  Button: Component<ButtonProps>;
  ErrorMessage: Component<ErrorMessageProps>;
  EntityCard: Component<EntityCardProps>;
  FieldList: Component<FieldListProps>;
  NavBar: Component<NavBarProps>;
  ConsoleBar: Component;
  Console: Component<ConsoleProps>;
}

export type ComponentName = keyof ComponentMap;
