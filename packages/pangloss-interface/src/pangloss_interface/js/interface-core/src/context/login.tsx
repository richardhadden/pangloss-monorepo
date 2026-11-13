import { createContext, createSignal, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";

interface LoginDialog {
  /** Whether the log in dialog is showing */
  loginOpen: Accessor<boolean>;
  /**
   * Open it. `onCancel` is called if it is dismissed without logging in (Escape, the close
   * button), such as to leave a page that needs a login. `onLoggedIn` is called once someone has
   * logged in with it; given, the dialog leaves it to that to read again what is on show (a
   * session that ran out: the page stays as it is)
   */
  openLogin: (onCancel?: () => void, onLoggedIn?: () => void) => void;
  /** Close it, having logged in (or for any reason that is not giving up) */
  closeLogin: () => void;
  /** Close it, someone having logged in with it: whether whoever opened it takes it from there (`onLoggedIn`) */
  closeLoggedIn: () => boolean;
  /** Close it, having given up: `onCancel` is called */
  cancelLogin: () => void;
}

const LoginDialogContext = createContext<LoginDialog>();

/**
 * Holds whether the log in dialog is open, so that anything (the nav bar's button, a page that
 * needs a login) can open it. A context, so that server-side renders do not share it.
 */
export function LoginDialogProvider(props: ParentProps) {
  const [loginOpen, setLoginOpen] = createSignal(false);
  let onCancel: (() => void) | undefined;
  let onLoggedIn: (() => void) | undefined;
  const state: LoginDialog = {
    loginOpen,
    openLogin: (cancel, loggedIn) => {
      onCancel = cancel;
      onLoggedIn = loggedIn;
      setLoginOpen(true);
    },
    closeLogin: () => {
      onCancel = undefined;
      onLoggedIn = undefined;
      setLoginOpen(false);
    },
    closeLoggedIn: () => {
      const loggedIn = onLoggedIn;
      onCancel = undefined;
      onLoggedIn = undefined;
      setLoginOpen(false);
      loggedIn?.();
      return loggedIn !== undefined;
    },
    cancelLogin: () => {
      const cancel = onCancel;
      onCancel = undefined;
      onLoggedIn = undefined;
      setLoginOpen(false);
      cancel?.();
    },
  };
  return <LoginDialogContext value={state}>{props.children}</LoginDialogContext>;
}

export function useLoginDialog(): LoginDialog {
  const state = useContext(LoginDialogContext);
  if (!state) {
    throw new Error("useLoginDialog(): there is no <LoginDialogProvider> above");
  }
  return state;
}
