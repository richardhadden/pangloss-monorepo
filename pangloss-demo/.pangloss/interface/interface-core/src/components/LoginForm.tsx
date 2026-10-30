import { Show } from "solid-js";
import { useComponent } from "../context";
import type { LoginFormProps } from "../types";

const field =
  "h-10 w-full border-[0.5px] border-slate-400/70 bg-white/60 px-3 text-sm outline-none focus:bg-white";
const label = "flex flex-col gap-1 text-xs font-semibold text-slate-700 uppercase";

/** The form to log in with, for a dialog: it says what was entered, and the page does the logging in */
export function LoginForm(props: LoginFormProps) {
  const ErrorMessage = useComponent("ErrorMessage");
  return (
    <form
      class="flex w-full flex-col gap-4 p-6"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        props.onSubmit(String(data.get("username") ?? ""), String(data.get("password") ?? ""));
      }}
    >
      <label class={label}>
        Username
        <input name="username" autocomplete="username" required autofocus class={field} />
      </label>
      <label class={label}>
        Password
        <input
          name="password"
          type="password"
          autocomplete="current-password"
          required
          class={field}
        />
      </label>
      <Show when={props.error !== undefined}>
        <ErrorMessage error={props.error} />
      </Show>
      <button
        type="submit"
        disabled={props.busy}
        class={[
          "h-10 cursor-pointer bg-slate-300/60 text-xs font-semibold text-slate-700 uppercase select-none hover:bg-slate-400/40 active:bg-slate-400/60",
          { "opacity-40": props.busy },
        ]}
      >
        <Show when={props.busy} fallback="Log in">
          Logging in…
        </Show>
      </button>
    </form>
  );
}
