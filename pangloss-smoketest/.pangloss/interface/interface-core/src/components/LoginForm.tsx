import { Show } from "solid-js";
import { ApiError } from "../api";
import { useComponent, useTranslations } from "../context";
import type { LoginFormProps } from "../types";

const field =
  "h-10 w-full border-[0.5px] border-slate-400/70 bg-white/60 px-3 text-sm outline-none focus:bg-white";
const label =
  "flex flex-col gap-1 text-xs font-semibold text-slate-700 uppercase";

/** The form to log in with, for a dialog: it says what was entered, and the page does the logging in */
export function LoginForm(props: LoginFormProps) {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  return (
    <form
      class="flex w-full flex-col gap-4 p-6"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        props.onSubmit(
          String(data.get("username") ?? ""),
          String(data.get("password") ?? ""),
        );
      }}
    >
      <label class={label}>
        {t("username", "Username")}
        <input
          name="username"
          autocomplete="username"
          required
          autofocus
          class={field}
        />
      </label>
      <label class={label}>
        {t("password", "Password")}
        <input
          name="password"
          type="password"
          autocomplete="current-password"
          required
          class={field}
        />
      </label>
      <Show when={props.error !== undefined}>
        {/* (a wrong username or password is the one answer a person can do something about: say so in words) */}
        <Show
          when={props.error instanceof ApiError && props.error.status === 401}
          fallback={<ErrorMessage error={props.error} />}
        >
          <p role="alert" class="pg-error-message">
            {t(
              "login_failed",
              "That username and password do not match. Check them and try again.",
            )}
          </p>
        </Show>
      </Show>
      <button
        type="submit"
        disabled={props.busy}
        class={[
          "h-10 cursor-pointer bg-slate-300/60 text-xs font-semibold text-slate-700 uppercase select-none hover:bg-slate-400/40 active:bg-slate-400/60",
          { "opacity-40": props.busy },
        ]}
      >
        <Show when={props.busy} fallback={t("log_in", "Log in")}>
          {t("logging_in", "Logging in…")}
        </Show>
      </button>
    </form>
  );
}
