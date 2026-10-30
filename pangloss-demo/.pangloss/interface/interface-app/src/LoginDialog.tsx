import { logIn, useComponent, useLoginDialog } from "@pangloss/interface-core";
import { revalidate } from "@solidjs/router";
import { createSignal, Show } from "solid-js";
import { apiClient } from "./api";
import { sessionQuery } from "./queries";

// The dialog to log in with, over the page it was opened on (so the page stays where it was)
export function LoginDialog() {
  const Modal = useComponent("Modal");
  const LoginForm = useComponent("LoginForm");
  const { loginOpen, closeLogin, cancelLogin } = useLoginDialog();
  const [error, setError] = createSignal<unknown>();
  const [busy, setBusy] = createSignal(false);

  async function submit(username: string, password: string) {
    setBusy(true);
    setError(undefined);
    try {
      await logIn(apiClient(), username, password);
      // (the session is in a cookie now: ask who it is again, and close)
      revalidate(sessionQuery.key);
      closeLogin();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }

  // (Escape or the close button: giving up, which whatever opened the dialog may want to know)
  function giveUp() {
    setError(undefined);
    cancelLogin();
  }

  return (
    <Show when={loginOpen()}>
      <Modal title="Log in" onClose={giveUp}>
        <LoginForm onSubmit={submit} error={error()} busy={busy()} />
      </Modal>
    </Show>
  );
}
