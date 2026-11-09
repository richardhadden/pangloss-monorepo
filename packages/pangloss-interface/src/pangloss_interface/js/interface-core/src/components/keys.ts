/** Keyboard shortcuts of the whole page: what a key is, and whether the page may take it */

export const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform);

/** The Command key on a Mac, Control elsewhere, and no other modifier */
function commandHeld(event: KeyboardEvent, mac: boolean): boolean {
  if (event.altKey || event.shiftKey) return false;
  return mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

/**
 * Cmd+K on a Mac, Ctrl+K elsewhere: opens the navigation bar. Not Alt+Right, which is the browser's Forward on Windows
 * and Linux and moves by a word in a text box on a Mac; not Ctrl+K on a Mac, which deletes to the end of the line there.
 */
export function isNavShortcut(event: KeyboardEvent, mac = isMac()): boolean {
  return event.key.toLowerCase() === "k" && commandHeld(event, mac);
}

/**
 * Cmd+Enter on a Mac, Ctrl+Enter elsewhere: a new item of the type chosen in the navigation bar. Not Cmd/Ctrl+N: the
 * browsers keep that for a new window, and it never reaches the page.
 */
export function isNewItemShortcut(event: KeyboardEvent, mac = isMac()): boolean {
  return event.key === "Enter" && !event.isComposing && commandHeld(event, mac);
}

/**
 * `/`, outside anything that takes text and with no dialog open: the quick search. By the character, and Shift is allowed,
 * as on some layouts (German) it needs Shift. (No chord with Cmd or Ctrl was free: Spotlight, Siri and the web console have them.)
 */
export function isQuickSearchShortcut(event: KeyboardEvent): boolean {
  if (event.key !== "/" || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return false;
  return !isTextEntry(event.target) && !dialogIsOpen();
}

/** Cmd+S on a Mac, Ctrl+S elsewhere: saves the form on the page, in place of the browser's saving of the page */
export function isSaveShortcut(event: KeyboardEvent, mac = isMac()): boolean {
  return event.key.toLowerCase() === "s" && commandHeld(event, mac);
}

/** Cmd+E on a Mac, Ctrl+E elsewhere: goes to the form of the item on the page */
export function isEditShortcut(event: KeyboardEvent, mac = isMac()): boolean {
  return event.key.toLowerCase() === "e" && commandHeld(event, mac);
}

/** Enter with no modifier, and not the one that ends the composing of a character */
export function isPlainEnter(event: KeyboardEvent): boolean {
  return (
    event.key === "Enter" && !event.isComposing && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey
  );
}

function isTextEntry(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable]") !== null;
}

/**
 * Whether a key pressed on the page itself writes something: one character (or a dead key, the start of an accented
 * one), without a modifier, and not a space (which scrolls the page), outside anything that takes text.
 */
export function startsTyping(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return false;
  if (isTextEntry(event.target)) return false;
  return event.key === "Dead" || ([...event.key].length === 1 && event.key.trim() !== "");
}

/** Whether a dialog covers the page, so that what is behind it does not answer keys */
export function dialogIsOpen(): boolean {
  return document.querySelector('[role="dialog"][aria-modal="true"]') !== null;
}
