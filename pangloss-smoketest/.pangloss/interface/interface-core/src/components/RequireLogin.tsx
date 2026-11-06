import { createEffect, createMemo, onCleanup, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useLoginDialog, userIsLoggedIn } from "../context";

/**
 * Wraps a page (or part of one) that needs a login. While no one is logged in it shows nothing
 * of it, and opens the log in dialog over the page instead: logging in shows the page; giving up
 * (`onCancel`) leaves it, such as for the home page. It also does so if the user logs out while
 * on the page. (The API refuses what needs a login in any case; this is what is shown.) The server
 * renders none of it for someone not logged in, and the dialog appears when the page is hydrated.
 *
 * Reading who is logged in may wait, so this goes inside a `<Loading>` (the frame of a page has one).
 */
export function RequireLogin(props: ParentProps<{ onCancel: () => void }>) {
  const { openLogin, closeLogin } = useLoginDialog();
  const allowed = createMemo(() => userIsLoggedIn());
  let asked = false;
  createEffect(allowed, (yes) => {
    if (!yes) {
      asked = true;
      openLogin(() => props.onCancel());
    } else if (asked) {
      // (it was logged in, probably from the dialog, which has closed itself: this is only for the rest)
      asked = false;
      closeLogin();
    }
  });
  // Leaving the page with the dialog still open is the dialog's end too
  onCleanup(() => {
    if (asked) closeLogin();
  });
  return <Show when={allowed()}>{props.children}</Show>;
}
