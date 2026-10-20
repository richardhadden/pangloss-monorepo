import type { ErrorMessageProps } from "../types";

export function ErrorMessage(props: ErrorMessageProps) {
  return (
    <p role="alert" class="pg-error-message">
      {props.error instanceof Error ? props.error.message : String(props.error)}
    </p>
  );
}
