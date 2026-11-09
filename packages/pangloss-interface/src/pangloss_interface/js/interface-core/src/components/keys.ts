/** Keyboard shortcuts of the whole page: what a key is, and whether the page may take it */

const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform);

/**
 * Cmd+K on a Mac, Ctrl+K elsewhere: opens the navigation bar. Not Alt+Right, which is the browser's Forward on Windows
 * and Linux and moves by a word in a text box on a Mac; not Ctrl+K on a Mac, which deletes to the end of the line there.
 */
export function isNavShortcut(event: KeyboardEvent, mac = isMac()): boolean {
  if (event.key.toLowerCase() !== "k" || event.altKey || event.shiftKey) return false;
  return mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
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
