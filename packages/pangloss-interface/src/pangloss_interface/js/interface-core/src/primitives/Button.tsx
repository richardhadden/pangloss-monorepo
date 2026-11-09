import type { ButtonProps } from "../types";
import { buttonClass } from "./buttonClass";

/**
 * A button that stands by itself (not one in the console, a head bar or a chip): its `kind` says what it
 * does and its `size` where it is (`buttonClass`, which a `<button>` or link that needs to be itself uses too).
 * With `label` and no children it is an icon button: give the icon as `icon`.
 */
export function Button(props: ButtonProps) {
  return (
    <button
      type={props.type ?? "button"}
      disabled={props.disabled}
      onClick={props.onClick}
      aria-label={props.label}
      title={props.title ?? props.label}
      class={[buttonClass(props.kind, props.size, props.children === undefined && props.icon !== undefined), props.class]}
    >
      {props.icon}
      {props.children}
    </button>
  );
}
