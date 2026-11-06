import type { ButtonProps } from "../types";

export function Button(props: ButtonProps) {
  return (
    <button
      type={props.type ?? "button"}
      disabled={props.disabled}
      onClick={props.onClick}
      class="pg-button"
    >
      {props.children}
    </button>
  );
}
