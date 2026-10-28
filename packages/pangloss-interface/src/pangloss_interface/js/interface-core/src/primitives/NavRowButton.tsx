import { useNavExpanded } from "../context";
import type { NavRowButtonProps } from "../types";

/**
 * A button of the navigation bar that is as wide as what holds it: a link with `href`,
 * otherwise a button. In a `NavRow` give `inRow`, to fill what the icon cell leaves; in a
 * list it is one line high. `indent` steps the text in from the left, the button staying
 * the same width. Following a link closes the navigation bar.
 */
export function NavRowButton(props: NavRowButtonProps) {
  const { setNavExpanded } = useNavExpanded();
  const classes = () => [
    "flex min-w-0 cursor-pointer items-center gap-2 overflow-hidden whitespace-nowrap pr-3 text-left text-xs text-slate-300 hover:bg-slate-500 active:bg-slate-700",
    props.inRow ? "h-full flex-1" : "py-1.5",
  ];
  const style = () => ({ "padding-left": `${0.75 + (props.indent ?? 0) * 0.75}rem` });
  return props.href !== undefined ? (
    <a
      href={props.href}
      onClick={() => setNavExpanded(false)}
      style={style()}
      class={classes()}
    >
      {props.children}
    </a>
  ) : (
    <button type="button" onClick={props.onClick} style={style()} class={classes()}>
      {props.children}
    </button>
  );
}
