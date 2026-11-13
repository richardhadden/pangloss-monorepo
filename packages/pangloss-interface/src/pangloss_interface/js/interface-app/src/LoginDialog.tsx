import { logIn, useComponent, useLoginDialog, useTranslations } from "@pangloss/interface-core";
import { action, createOptimistic, createSignal, Show } from "solid-js";
import { apiClient } from "./api";
import { revalidateAll } from "./queries";

// The dialog to log in with, over the page it was opened on (so the page stays where it was)
export function LoginDialog() {
  const Modal = useComponent("Modal");
  const LoginForm = useComponent("LoginForm");
  const { t } = useTranslations();
  const { loginOpen, closeLoggedIn, cancelLogin } = useLoginDialog();
  const [error, setError] = createSignal<unknown>();
  // (while the login is being sent: back to false when that is over, whatever the answer)
  const [busy, setBusy] = createOptimistic(false);
  const send = action(function* (username: string, password: string) {
    setBusy(true);
    yield logIn(apiClient(), username, password);
  });

  async function submit(username: string, password: string) {
    setError(undefined);
    try {
      await send(username, password);
    } catch (failure) {
      setError(failure);
      return;
    }
    // (the session is in a cookie now: ask again for who it is, and for what is on show, which
    // may be more than it was; then close. Unless it was opened because a session ran out, whose
    // page stays as it is: what opened it takes it from there)
    if (!closeLoggedIn()) revalidateAll();
  }

  // (Escape or the close button: giving up, which whatever opened the dialog may want to know)
  function giveUp() {
    setError(undefined);
    cancelLogin();
  }

  return (
    <Show when={loginOpen()}>
      <Modal title={t("log_in", "Log in")} onClose={giveUp}>
        <LoginForm onSubmit={submit} error={error()} busy={busy()} />
      </Modal>
    </Show>
  );
}
