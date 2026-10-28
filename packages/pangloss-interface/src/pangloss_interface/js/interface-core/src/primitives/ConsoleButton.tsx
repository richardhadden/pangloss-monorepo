import type { ConsoleButtonProps, ConsoleButtonTone } from "../types";

// (whole class names, so that Tailwind finds them)
const TONES: Record<ConsoleButtonTone, string> = {
  neutral: "hover:bg-slate-400/40 active:bg-slate-400/60",
  entity: "bg-sky-400/25 text-sky-950 hover:bg-sky-400/40 active:bg-sky-400/60",
  document: "bg-green-400/25 text-green-950 hover:bg-green-400/40 active:bg-green-400/60",
  danger: "text-red-800 hover:bg-red-400/30 active:bg-red-400/50",
};

/**
 * A button for the right of the console, as high as the bar, with a rule on its left. It is
 * configured by its props: the icon (the children), the `label` (the name for a screen reader
 * and a tooltip, and shown beside the icon with `text`), the `tone`, whether it is `disabled`,
 * whether it is a toggle (`pressed`), and whether it is a link (`href`) or a button (`onClick`). Without `text` it is a square.
 */
export function ConsoleButton(props: ConsoleButtonProps) {
  const classes = () => [
    "flex h-full shrink-0 items-center justify-center gap-2 border-l-[0.5px] border-slate-400/70 select-none",
    props.text ? "px-4" : "w-12",
    TONES[props.tone ?? "neutral"],
    props.disabled ? "pointer-events-none opacity-40" : "cursor-pointer",
    props.pressed && "bg-slate-400/50",
  ];
  const content = () => (
    <>
      {props.children}
      {props.text && <span>{props.label}</span>}
    </>
  );
  return props.href !== undefined ? (
    <a
      href={props.disabled ? undefined : props.href}
      aria-label={props.label}
      aria-disabled={props.disabled ? "true" : undefined}
      title={props.label}
      class={classes()}
    >
      {content()}
    </a>
  ) : (
    <button
      type="button"
      aria-label={props.label}
      title={props.label}
      disabled={props.disabled}
      aria-pressed={props.pressed === undefined ? undefined : props.pressed ? "true" : "false"}
      onClick={props.onClick}
      class={classes()}
    >
      {content()}
    </button>
  );
}
