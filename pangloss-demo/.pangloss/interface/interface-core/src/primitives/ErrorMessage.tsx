import { Show } from "solid-js";
import type { ErrorMessageProps } from "../types";

export function ErrorMessage(props: ErrorMessageProps) {
  return (
    <p role="alert" class="pg-error-message">
      <Show when={props.error instanceof Error} fallback={String(props.error)}>
        {(props.error as Error).message}
      </Show>
    </p>
  );
}
