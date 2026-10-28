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

export interface Search {
  query: string;
  deep: boolean;
}

export interface ConsoleSearchProps {
  /** What is searched for now */
  query?: string;
  /** Whether it is a Deep Search that is shown */
  deep?: boolean;
  /**
   * Called when a search is to be made: a moment after the last key (an ordinary search),
   * or at once when Enter is pressed. A Deep Search is made only on Enter or the run
   * button, as it is slow.
   */
  onSearch?: (search: Search) => void;
  /** How many were found (shown beside the search; its read may wait for the result) */
  count?: number;
  /** Whether there are more than `count`: a word had more hits than the search looks at (shown as `count+`) */
  truncated?: boolean;
  /** Whether the result is being fetched again: a spinner is shown in place of the count */
  pending?: boolean;
}

export interface ConsoleProps extends ConsoleSearchProps {
  /** The name of the type of what the page shows */
  type: string;
  /** The page is a list of the type (its name is shown in the plural) */
  list?: boolean;
  /** The label of the item, when the page is one */
  label?: string;
  /** The semantic spaces the item is in, outermost first: a cell for each, left of the type */
  spaces?: string[];
  /** The actions that can be taken, shown on the right */
  children?: JSX.Element;
}

export interface ModalProps {
  /** The heading of the dialog, which names it for a screen reader */
  title: string;
  /** Called when Escape or the close button is used: the dialog does not close itself */
  onClose: () => void;
  /** The name of the close button (`Close` if not given) */
  closeLabel?: string;
  children?: JSX.Element;
}

export interface LoginFormProps {
  /** Called with what was entered */
  onSubmit: (username: string, password: string) => void;
  /** Why the last try failed, if it did */
  error?: unknown;
  /** Whether a try is being made */
  busy?: boolean;
}

export interface ResultButtonProps {
  /** Where it goes */
  href: string;
  /** The type of the item (its own, which can be a subtype of the list's) */
  type: string;
  label: string;
  /** The semantic spaces the item is in, outermost first: each wraps it in a band of its own */
  spaces?: string[];
  /** The head node of an item that is inside another document: a button to it on the left */
  head?: { type: string; id: string };
}

export interface ReferenceChipProps {
  /** The type of what is referred to (its own, which can be a subtype of the field's) */
  type: string;
  label: string;
  /** Where it goes (if it is not given, the chip is not a link) */
  href?: string;
  /** The properties of the edge to it (`{ level: 3 }`), shown after the label */
  edgeProperties?: Record<string, unknown>;
}

export interface ItemContentsProps {
  /** One Document or Entity as the API sends it: its fields are laid out by its model */
  item: Record<string, unknown>;
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
  ResultButton: Component<ResultButtonProps>;
  ReferenceChip: Component<ReferenceChipProps>;
  ItemContents: Component<ItemContentsProps>;
  LoginForm: Component<LoginFormProps>;
  Modal: Component<ModalProps>;
  ConsoleBar: Component;
  Console: Component<ConsoleProps>;
}

export type ComponentName = keyof ComponentMap;
