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
  /** Chosen with the keyboard: drawn as when the mouse is over it (a link) */
  selected?: boolean;
  /** Given the element of a link */
  linkRef?: (element: HTMLAnchorElement) => void;
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
  /** Gives the search a button for the search form of the list, beside Deep search, which calls this */
  onToggleForm?: () => void;
  /** Whether the search form is open (the button is pressed) */
  formOpen?: boolean;
  /** Gives the search a button that shows the whole list or only what something refers to, which calls this */
  onToggleUsed?: () => void;
  /** Whether the whole list is on show (the button offers the used ones), not only what something refers to */
  showingAll?: boolean;
  /** Whether a search by fields is in use: what is typed narrows it, and Deep search cannot be used */
  structured?: boolean;
  /** Gives the box's arrows and Enter to a list on the page: to move what is selected in it, and to open that */
  onListKey?: (key: "next" | "previous" | "open") => void;
  /** Called when the box takes or loses the focus */
  onFocusChange?: (focused: boolean) => void;
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
  /** Who made the item and who changed it last, and when: two light rows on the right */
  meta?: {
    createdBy?: string | null;
    createdWhen?: string | null;
    updatedBy?: string | null;
    updatedWhen?: string | null;
  };
  /** Where the item can be edited: an Edit button, for someone who is logged in */
  editHref?: string;
  /** Called once the item (`item`) has been deleted: with it, a Delete button for someone who is logged in, which asks first */
  onDeleted?: () => void;
  /** A list whose page makes a new item itself (a dialog): the New button calls this, and is no link to `/<type>/new` */
  onNew?: () => void;
  /**
   * The item the page is about (its own type and id), and which page it is: the `consoleActions` of the interface
   * modules are shown for it. Without it (a list, a new item) there are none.
   */
  item?: { type: string; id: string };
  page?: "item" | "edit";
  /** The actions that can be taken, shown on the right */
  children?: JSX.Element;
}

export interface ItemFormProps {
  /** The type of the item (not abstract); a new item is made of this type */
  type: string;
  /** What to edit: the edit view of an item, or `{ type }` for a new one */
  initial: Record<string, unknown>;
  /** The `meta.version` the item was loaded at (an update is based on it); without one, the form makes a new item */
  version?: number;
  /** The meta of the item, for the console */
  meta?: ConsoleProps["meta"];
  /** Called with the summary the API answers when the item is saved */
  onSaved: (saved: { id: string; type: string; label: string }) => void;
  onCancel: () => void;
  /** Called once the item has been deleted; with it, an item being edited has a Delete button */
  onDeleted?: () => void;
  /** Called to load the item again, after it was found to have been changed by someone else */
  onReload?: () => void;
  /** The id of a document inside the item that the page is to show: a block nested deep enough to start folded opens if it is inside */
  show?: string;
  /**
   * What the item is when there is nothing to save, if not `initial`: a new item opened from the stash starts as the
   * stashed item, and can be saved at once
   */
  baseline?: Record<string, unknown>;
  /**
   * The stashed item the form was opened from (`initial` is it): stashing again replaces it, and saving removes it.
   * `gone`: the entities it referred to that are no longer there, which were taken out (shown above the form)
   */
  stashed?: { key: string; gone: { type: string; id: string; label?: string }[] };
  /**
   * Called once the form is shown, with what the page calls before it is left: given how to leave, it says whether the
   * page may go now (true: nothing to lose). If not, the form asks (stay, leave without saving, or stash and leave),
   * and leaves itself if told to. What it gives back is called when the form is gone
   */
  guardLeaving?: (guard: (leave: () => void) => boolean) => (() => void) | void;
  /**
   * With it, a new head document (not an entity) has a Stash button beside Save (where there is a stash); called once
   * it is stashed
   */
  onStashed?: () => void;
}

export interface ModalProps {
  /** The heading of the dialog, which names it for a screen reader */
  title: string;
  /** Called when Escape or the close button is used: the dialog does not close itself */
  onClose: () => void;
  /** The name of the close button (`Close` if not given) */
  closeLabel?: string;
  /**
   * How wide it is: `sm` for a short form such as the login (the default), `lg` for a form with many fields, `xl` for
   * a search with long results over another dialog
   */
  size?: "sm" | "lg" | "xl";
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
  /** Chosen with the keyboard: drawn as when the mouse is over it */
  selected?: boolean;
  /** How many things refer to the item: a small bubble at the right, if it is given */
  useCount?: number;
}

export interface ReferenceChipProps {
  /** The type of what is referred to (its own, which can be a subtype of the field's) */
  type: string;
  label: string;
  /** Where it goes (if it is not given, the chip is not a link) */
  href?: string;
  /** The properties of the edge to it (`{ level: 3 }`), shown at the end of the chip */
  edgeProperties?: Record<string, unknown>;
  /** The model of those properties: their names, and how each is written (`Slider(unit="%")`: "19%") */
  edgeModel?: string | null;
  /** The semantic spaces what is referred to is in, outermost first: the chip is wrapped in a band for each */
  spaces?: string[];
  /** Gives the chip a remove button at its end (a form's): the chip is then always the default one */
  onRemove?: () => void;
  /** The name of that button for a screen reader */
  removeLabel?: string;
  /** Gives the chip a copy button, in a form (the reference goes on the clipboard) */
  onCopy?: () => void;
  /** Gives the chip a cut button, in a form */
  onCut?: () => void;
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
  /** Goes to a page of the application (the keyboard's way to a new item needs it; the library has no router) */
  onNavigate?: (href: string) => void;
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
  ClipboardBar: Component;
  Toasts: Component;
  Console: Component<ConsoleProps>;
  ItemForm: Component<ItemFormProps>;
}

export type ComponentName = keyof ComponentMap;
